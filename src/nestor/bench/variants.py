"""Variants: the configuration under test, written as a fragment of `nestor.yaml`.

    triage_model:                 # any key of nestor.yaml, validated as it would be there
      kind: openai-compatible
      base_url: https://openrouter.ai/api/v1
      api_key: ${OPENROUTER_API_KEY}
      model: mistralai/mistral-small-3.2
    persona: {language: French}
    bench:                        # the only key of its own: the variant's name and the suite's knobs
      name: gate-mistral-small
      algorithm: gate

The fragment is laid over the defaults of a minimal configuration, so a whole `nestor.yaml` is a variant
too. `${NAME}` and `${secret:name}` resolve as in a configuration (the `.env` next to the variant file).
What a run records of it has every secret masked.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from nestor.bench.errors import BenchError
from nestor.bench.ports import Knobs, Suite
from nestor.core.i18n import Locale, Localizer, Message
from nestor.modules.cognition import ConversationModel
from nestor.runtime.config import AdapterConfig, NestorConfig, environment, validate_config
from nestor.runtime.plugins import Family, Registry, Services

DEFAULTS: dict[str, Any] = {
    "persona": {"name": "Nestor", "character": ""},
    "household": [{"id": "bench", "name": "Bench"}],
    "channels": [{"kind": "bench"}],  # never built: a configuration needs one
}


@dataclass(frozen=True, slots=True, kw_only=True)
class Variant[K: Knobs]:
    name: str
    source: Path
    knobs: K
    config: NestorConfig
    models: Mapping[str, ConversationModel]  # by configuration key, built but not started
    described: Mapping[str, Mapping[str, Any]]  # each model's kind and settings, secrets masked

    def record(self) -> dict[str, Any]:
        """What a run keeps of the variant: no secret, no value it did not set."""
        return {
            "source": str(self.source),
            "models": {role: dict(d) for role, d in self.described.items()},
            "persona": {"locale": self.config.persona.locale, "language": self.config.persona.language},
            "bench": self.knobs.model_dump(mode="json"),
        }


def load_variant[K: Knobs](
    path: Path, suite: Suite[Any, K], registry: Registry, localizer: Localizer, environ: dict[str, str] | None = None
) -> Variant[K]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raise BenchError(Message.of("bench-variant-unreadable", path=str(path))) from None
    if not isinstance(raw, dict):
        raise BenchError(Message.of("bench-variant-unreadable", path=str(path)))
    fragment = dict(raw)
    try:
        knobs = suite.knobs.model_validate(fragment.pop("bench", None) or {})
    except ValidationError as error:
        raise BenchError(Message.of("bench-variant-invalid", path=str(path), problems=_explain(error))) from None
    if "model" not in fragment:  # a variant naming only the model under test: it is the main one as well
        chosen = next((fragment[role] for role in suite.models if role in fragment), None)
        if chosen is None:
            raise BenchError(Message.of("bench-variant-no-model", path=str(path), keys=", ".join(suite.models)))
        fragment["model"] = chosen
    merged = DEFAULTS | {k: _over(DEFAULTS.get(k), v) for k, v in fragment.items()}
    config = validate_config(merged, environ if environ is not None else environment(path), origin=str(path))
    services = Services(data_dir=config.data_dir, localizer=localizer, locale=Locale(config.persona.locale))
    models: dict[str, ConversationModel] = {}
    described: dict[str, Mapping[str, Any]] = {}
    for role in suite.models:
        adapter: AdapterConfig = getattr(config, role, None) or config.model
        plugin = registry.get(Family.MODEL, adapter.kind)
        model = plugin.create(adapter.settings(), role, services)
        if not isinstance(model, ConversationModel):
            raise BenchError(Message.of("bench-variant-not-a-model", path=str(path), kind=adapter.kind))
        models[role] = model
        described[role] = {
            "kind": adapter.kind,
            **plugin.settings.model_validate(adapter.settings()).model_dump(mode="json"),
        }
    return Variant(
        name=knobs.name or path.stem,
        source=path,
        knobs=knobs,
        config=config,
        models=models,
        described=described,
    )


def _over(default: Any, value: Any) -> Any:
    """A section of the fragment over the default one: a mapping completes it, anything else replaces it."""
    return {**default, **value} if isinstance(default, dict) and isinstance(value, dict) else value


def _explain(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'value'}: {e['msg']}" for e in error.errors())
