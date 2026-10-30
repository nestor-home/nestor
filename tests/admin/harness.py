"""A Nestor assembled with doubles, its admin, and browsers calling its API in the same event loop."""

import asyncio
import json
import urllib.parse
from collections.abc import MutableMapping, Sequence
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import Field, SecretStr

from nestor.admin import AdminSettings, create_app
from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.accounts import Account, Role
from nestor.modules.channels import Medium
from nestor.modules.cognition.tools import Tool, ToolProvider
from nestor.modules.connectors import AuthKind, SecretField
from nestor.runtime import AdapterSettings, Family, Nestor, Plugin, Registry
from nestor.runtime.config import parse_config
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import FakeRemote, ScriptedModel, ScriptedRemoteExecutor
from nestor.testing.connectors import FakeProvider, ScriptedConnector
from nestor.testing.home import StaticPresence

PASSWORD = "correct horse battery"
OWNER = "mathis"  # the owner's login, opened with every harness
SECRET_KEY = "s" * 43
CLIENT_SECRET = "gocspx-household-client-secret"
CONFIG = """# The test household's assistant (this comment must survive an edit from the admin).
data_dir: {data_dir}
persona: {{name: Richie, character: Tu es Richie., timezone: Europe/Paris}}
household:
  - {{id: mathis, name: Mathis, accounts: ["memory:user"], reach: "memory:main"}}
  - {{id: mathilde, name: Mathilde}}
  - {{id: lucie, name: Lucie}}
model: {{kind: scripted}}
executors: [{{kind: remote, name: hermes}}]
channels: [{{kind: memory, name: telegram}}]
presence: {{kind: static}}
admin: {admin}
"""


class NoSettings(AdapterSettings):
    pass


class Units(StrEnum):
    METRIC = "metric"
    IMPERIAL = "imperial"


class WeatherAccount(AdapterSettings):
    login: str
    password: SecretStr


class WeatherSettings(AdapterSettings):
    """A third-party plugin's settings: a secret, an optional one, secret headers, a nested secret, a
    choice, an advanced field."""

    api_key: SecretStr
    city: str
    token: SecretStr | None = None
    headers: dict[str, SecretStr] = Field(default_factory=dict)
    units: Units = Units.METRIC
    account: WeatherAccount | None = None
    retries: int = Field(default=2, json_schema_extra={"advanced": True})


class Speaker(InMemoryChannel):
    """A satellite heard in the salon: a spoken channel the courier can speak through."""

    medium = Medium.SPOKEN
    room = "salon"


class Weather(ToolProvider):
    name = "weather"

    def tools(self) -> Sequence[Tool]:
        return ()


class Api:
    """A browser using the API: its own cookies, the CSRF token `GET /me` gave it on every unsafe request."""

    def __init__(self, harness: "Harness") -> None:
        self.harness = harness
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=harness.app),
            base_url=harness.base_url,
            headers={"Origin": harness.base_url},  # what a browser sends on every POST from the admin's pages
        )
        self.csrf = ""

    async def sign_in(self, login: str, password: str = PASSWORD) -> httpx.Response:
        response = await self.post("/api/v1/session", {"login": login, "password": password})
        if response.status_code == 200:
            self.csrf = response.json()["csrf_token"]
        return response

    async def get(self, path: str, **params: Any) -> httpx.Response:
        return self._seen(await self.client.get(path, params=params))

    async def post(self, path: str, body: object = None) -> httpx.Response:
        return await self.send("POST", path, body)

    async def put(self, path: str, body: object = None) -> httpx.Response:
        return await self.send("PUT", path, body)

    async def patch(self, path: str, body: object = None) -> httpx.Response:
        return await self.send("PATCH", path, body)

    async def delete(self, path: str) -> httpx.Response:
        return await self.send("DELETE", path)

    async def send(self, method: str, path: str, body: object = None, **headers: str) -> httpx.Response:
        sent = {"X-CSRF-Token": self.csrf, **headers} if self.csrf else headers
        response = await self.client.request(method, path, json=body, headers=sent)
        return self._seen(response)

    def _seen(self, response: httpx.Response) -> httpx.Response:
        self.harness.seen.append(f"{response.headers}\n{response.text}")
        return response


class Harness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        public_url: str | None = None,
        connectors: bool = True,
        confirms_stop: bool = True,
        replies: tuple[str, ...] = (),
        front_dir: Path | None = None,
        heartbeat_s: float = 15.0,
        quiet_hours: str | None = None,
        speaker: bool = False,
    ) -> None:
        self.confirms_stop, self.replies = confirms_stop, replies
        self.provider = FakeProvider()
        self.mail = ScriptedConnector()
        self.mail.info = replace(
            self.mail.info, title=Message.of("harness-mailbox-title"), setup=Message.of("harness-mailbox-setup")
        )
        self.imap = ScriptedConnector("imap", auth=AuthKind.SECRET, account="mathilde@free.fr")
        self.imap.info = replace(
            self.imap.info,
            title=Message.of("harness-imap-title"),
            fields=(
                SecretField(name="server", label=Message.of("harness-imap-field-server"), secret=False),
                *self.imap.info.fields,
            ),
        )
        self.remote = FakeRemote()
        self.presence = StaticPresence().set("mathis", home=True, room="salon")
        admin = {"port": 0, **({"public_url": public_url} if public_url else {})}
        text = CONFIG.format(data_dir=tmp_path, admin=admin)
        if not connectors:
            text += "connectors: []\n"
        if quiet_hours:
            text += f"initiative: {{quiet_hours: '{quiet_hours}'}}\n"
        if speaker:
            text = text.replace(
                "channels: [{kind: memory, name: telegram}]",
                "channels: [{kind: memory, name: telegram}, {kind: speaker, name: voice}]",
            )
        self.config_path = tmp_path / "harness.yaml"  # what the admin edits
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(text)
        self.nestor = Nestor(
            parse_config(text, {}),
            self.registry(),
            environ={"NESTOR_SECRET_KEY": SECRET_KEY, "WEATHER_CITY": "Paris"},
            token_endpoint=self.provider,
            source=self.config_path,
        )
        self.settings = AdminSettings(
            public_url=public_url, front_dir=front_dir or tmp_path / "no-front", heartbeat_s=heartbeat_s
        )
        self.app = create_app(self.nestor, self.settings)
        self.base_url = public_url or "http://admin.test"
        self.browser = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=self.base_url)
        self.seen: list[str] = []  # every API response, likewise
        self._apis: list[Api] = []
        self.owner: Account | None = None

    def registry(self) -> Registry:
        return Registry(
            [
                Plugin(Family.MODEL, "scripted", NoSettings, lambda s, n, x: ScriptedModel(*self.replies)),
                Plugin(Family.CHANNEL, "memory", NoSettings, lambda s, name, x: InMemoryChannel(name)),
                Plugin(Family.CHANNEL, "speaker", NoSettings, lambda s, name, x: Speaker(name)),
                Plugin(
                    Family.EXECUTOR,
                    "remote",
                    NoSettings,
                    lambda s, n, x: ScriptedRemoteExecutor(
                        self.remote, duration_s=None, confirms_stop=self.confirms_stop
                    ),
                ),
                Plugin(Family.PRESENCE, "static", NoSettings, lambda s, n, x: self.presence),
                Plugin(Family.CONNECTOR, "mailbox", NoSettings, lambda s, n, x: self.mail),
                Plugin(Family.CONNECTOR, "imap", NoSettings, lambda s, n, x: self.imap),
                Plugin(Family.TOOLS, "weather", WeatherSettings, lambda s, n, x: Weather()),
            ]
        )

    async def __aenter__(self) -> Self:
        await self.nestor.__aenter__()
        self.owner = await self.account(OWNER, Role.OWNER, "mathis")
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        for api in self._apis:
            await api.client.aclose()
        await self.browser.aclose()
        await self.nestor.__aexit__(exc_type, exc, tb)

    # -- accounts ---------------------------------------------------------------------------------------

    async def account(self, login: str, role: Role, person: str | None = None) -> Account:
        return await self.nestor.accounts.create(
            login=login, password=PASSWORD, role=role, person=PersonId(person) if person else None
        )

    async def api(self, login: str | None = OWNER) -> Api:
        """A new browser on the API, signed in as `login` (anonymous with `None`)."""
        api = Api(self)
        self._apis.append(api)
        if login is not None:
            response = await api.sign_in(login)
            assert response.status_code == 200, response.text
        return api

    # -- what the provider's consent page does -------------------------------------------------------

    async def come_back(self, **params: str) -> httpx.Response:
        """The browser sent back by the provider: without the session cookie, which is SameSite=Strict and
        so not sent on a cross-site navigation."""
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=self.base_url) as browser:
            response = await browser.get("/connections/callback", params=params)
        self.seen.append(f"{response.headers}\n{response.text}")
        return response

    def consent(self, authorize_url: str) -> dict[str, str]:
        """Approve at the provider: the query it sends back to `redirect_uri` (code and state)."""
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(authorize_url).query))
        connections = self.nestor.connections
        assert connections is not None
        issued = query["state"].split(".")[0]
        verifier = connections._pending[issued].verifier  # what only Nestor knows, checked by the provider
        return {"state": query["state"], "code": self.provider.authorize(query["client_id"], verifier)}


class EventStream:
    """A live journal stream read the way a browser's `EventSource` does, straight on the ASGI app (an
    HTTP client would wait for the response to end, and this one never does)."""

    def __init__(self, api: Api, path: str = "/api/v1/journal/stream", **headers: str) -> None:
        self.api, self.path, self.headers = api, path, headers
        self.status = 0
        self._buffer = ""
        self._frames: asyncio.Queue[str] = asyncio.Queue()
        self._leave = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.ended = asyncio.Event()

    async def __aenter__(self) -> Self:
        path, _, query = self.path.partition("?")
        cookies = "; ".join(f"{k}={v}" for k, v in self.api.client.cookies.items())
        headers = [(b"host", b"admin.test"), (b"cookie", cookies.encode())]
        headers += [(k.lower().replace("_", "-").encode(), v.encode()) for k, v in self.headers.items()]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("admin.test", 80),
        }
        requested = False

        async def receive() -> dict[str, Any]:
            nonlocal requested
            if not requested:
                requested = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await self._leave.wait()
            return {"type": "http.disconnect"}

        async def send(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                self.status = message["status"]
            elif message["type"] == "http.response.body":
                self._buffer += message.get("body", b"").decode()
                while "\n\n" in self._buffer:
                    frame, self._buffer = self._buffer.split("\n\n", 1)
                    self._frames.put_nowait(frame)

        async def run() -> None:
            try:
                await self.api.harness.app(scope, receive, send)
            finally:
                self.ended.set()

        self._task = asyncio.create_task(run())
        return self

    async def frame(self, timeout_s: float = 2.0) -> str:
        return await asyncio.wait_for(self._frames.get(), timeout_s)

    async def event(self, timeout_s: float = 2.0) -> tuple[str, dict[str, Any]]:
        """The next journal event (its id and item), skipping heartbeats, the retry hint and activity."""
        while True:
            frame = await self.frame(timeout_s)
            fields = dict(line.split(": ", 1) for line in frame.splitlines() if not line.startswith(":"))
            if fields.get("event") == "item":
                return fields["id"], json.loads(fields["data"])

    async def activity(self, timeout_s: float = 2.0) -> dict[str, Any]:
        """The next activity event, skipping entries and heartbeats."""
        while True:
            frame = await self.frame(timeout_s)
            fields = dict(line.split(": ", 1) for line in frame.splitlines() if not line.startswith(":"))
            if fields.get("event") == "activity":
                assert "id" not in fields, "an activity event must not move the stream's resumption point"
                return json.loads(fields["data"])

    async def __aexit__(self, *exc: object) -> None:
        self._leave.set()
        if self._task is not None:
            await asyncio.wait_for(self._task, 2)
