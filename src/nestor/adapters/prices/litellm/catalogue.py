"""The catalogue: the price list kept on disk and in memory, refreshed in the background."""

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from nestor.adapters.common.http import USER_AGENT
from nestor.core import Unit, utc_now
from nestor.modules.usage import PriceCatalogue, Rates

log = logging.getLogger("nestor.prices")
DEFAULT_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
MAX_BYTES = 30_000_000  # the list weighs a few megabytes
FIRST_S = 60.0  # after starting without a copy: the household's first minute is not spent on this
REFRESH_S = 24 * 3600.0
RETRY_S = 3600.0  # after a failed refresh

# what each of its fields prices, per one unit
_FIELDS: Mapping[str, Unit] = {
    "input_cost_per_token": Unit.INPUT_TOKENS,
    "output_cost_per_token": Unit.OUTPUT_TOKENS,
    "cache_read_input_token_cost": Unit.CACHED_INPUT_TOKENS,
    "cache_creation_input_token_cost": Unit.CACHE_WRITE_TOKENS,
    "input_cost_per_second": Unit.AUDIO_SECONDS,
    "input_cost_per_character": Unit.CHARACTERS,
    "output_cost_per_image": Unit.IMAGES,
}
# Nestor's name for who bills a model → the names the list files it under
_PROVIDERS: Mapping[str, tuple[str, ...]] = {
    "anthropic": ("anthropic",),
    "openai": ("openai", "text-completion-openai"),
    "gemini": ("gemini",),
    "mistral": ("mistral",),
    "groq": ("groq",),
    "openrouter": ("openrouter",),
    "vercel": ("vercel_ai_gateway",),
    "elevenlabs": ("elevenlabs",),
}


class LiteLLMCatalogue(PriceCatalogue):
    name = "litellm-prices"

    def __init__(
        self,
        path: Path,
        *,
        url: str = DEFAULT_URL,
        client: httpx.AsyncClient | None = None,
        first_s: float = FIRST_S,
        refresh_s: float = REFRESH_S,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """`path`: where the last copy is kept, so that prices are known at once after a restart, offline too."""
        self.path, self.url = path, url
        self._client, self._own_client = client, client is None
        self._first_s, self._refresh_s, self._clock = first_s, refresh_s, clock
        self._prices: dict[tuple[str, str], Rates] = {}  # (list's provider, model) → rates
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        copied = None
        with contextlib.suppress(OSError, ValueError):
            copied = await asyncio.to_thread(self._read_copy)
        if copied is not None:
            data, at = copied
            self._prices = _rates(data, at)
        self._worker = asyncio.create_task(self._keep_fresh(copied[1] if copied else None), name=self.name)

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None
        if self._own_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def rates(self, provider: str, model: str) -> Rates | None:
        for listed in _PROVIDERS.get(provider, ()):
            bare = model.removeprefix(f"{listed}/")
            if (found := self._prices.get((listed, bare))) is not None:
                return found
        return None

    async def refresh(self) -> None:
        """Download the list, keep its copy, and price by it from now on. A failure keeps the last good one."""
        assert self._client is not None, "start the catalogue first"
        body = bytearray()
        async with self._client.stream("GET", self.url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    raise ValueError(f"{self.url}: over {MAX_BYTES} bytes, not a price list")
        data = json.loads(body)
        at = self._clock()
        prices = _rates(data, at)
        if not prices:
            raise ValueError(f"{self.url}: no price in it")
        await asyncio.to_thread(self._write_copy, bytes(body))
        self._prices = prices
        log.info("model prices refreshed: %d models", len(prices))

    async def _keep_fresh(self, copied_at: datetime | None) -> None:
        age = (self._clock() - copied_at).total_seconds() if copied_at else None
        wait = self._first_s if age is None else max(self._refresh_s - age, 0.0)
        while True:
            await asyncio.sleep(wait)
            try:
                await self.refresh()
                wait = self._refresh_s
            except (httpx.HTTPError, OSError, ValueError) as error:
                log.warning("model prices not refreshed (%s): %s", type(error).__name__, error)
                wait = RETRY_S

    def _read_copy(self) -> tuple[Any, datetime]:
        at = datetime.fromtimestamp(self.path.stat().st_mtime, UTC)
        return json.loads(self.path.read_bytes()), at

    def _write_copy(self, body: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_suffix(".partial")
        partial.write_bytes(body)
        os.replace(partial, self.path)


def _rates(data: object, at: datetime) -> dict[tuple[str, str], Rates]:
    """The list's prices by (provider, model): the name it files them under, without the provider's prefix."""
    source = f"catalogue:{at.date().isoformat()}"
    prices: dict[tuple[str, str], Rates] = {}
    for name, entry in data.items() if isinstance(data, dict) else ():
        if not isinstance(entry, dict) or not isinstance(provider := entry.get("litellm_provider"), str):
            continue
        per_unit: dict[Unit, Decimal] = {}
        for field, unit in _FIELDS.items():
            value = entry.get(field)
            if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
                with contextlib.suppress(InvalidOperation):
                    per_unit[unit] = Decimal(str(value))
        if per_unit:
            prices[(provider, str(name).removeprefix(f"{provider}/"))] = Rates(per_unit, source)
    return prices
