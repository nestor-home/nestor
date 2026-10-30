"""A Nestor assembled with doubles, its admin, and a browser talking to it in the same event loop."""

import re
import urllib.parse
from dataclasses import replace
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx

from nestor.admin import AdminSettings, create_app, hash_password
from nestor.modules.connectors import AuthKind, SecretField
from nestor.runtime import AdapterSettings, Family, Nestor, Plugin, Registry
from nestor.runtime.config import parse_config
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import FakeRemote, ScriptedModel, ScriptedRemoteExecutor
from nestor.testing.connectors import FakeProvider, ScriptedConnector
from nestor.testing.home import StaticPresence

PASSWORD = "correct horse battery"
PASSWORD_HASH = hash_password(PASSWORD)
SECRET_KEY = "s" * 43
CLIENT_SECRET = "gocspx-household-client-secret"
SETUP = "1. Créez un projet dans la console du fournisseur.\n2. Ajoutez un client OAuth « application Web »."
CONFIG = """
data_dir: {data_dir}
persona: {{name: Richie, character: Tu es Richie., timezone: Europe/Paris}}
household:
  - {{id: mathis, name: Mathis, accounts: ["memory:user"], reach: "memory:main"}}
  - {{id: mathilde, name: Mathilde}}
model: {{kind: scripted}}
executors: [{{kind: remote, name: hermes}}]
channels: [{{kind: memory, name: telegram}}]
presence: {{kind: static}}
admin: {admin}
"""


class NoSettings(AdapterSettings):
    pass


class Harness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        public_url: str | None = None,
        connectors: bool = True,
        confirms_stop: bool = True,
        replies: tuple[str, ...] = (),
    ) -> None:
        self.confirms_stop, self.replies = confirms_stop, replies
        self.provider = FakeProvider()
        self.mail = ScriptedConnector()
        self.mail.info = replace(self.mail.info, title="Messagerie", setup=SETUP)
        self.imap = ScriptedConnector("imap", auth=AuthKind.SECRET, account="mathilde@free.fr")
        self.imap.info = replace(
            self.imap.info,
            title="Boîte IMAP",
            fields=(SecretField(name="server", label="Serveur", secret=False), *self.imap.info.fields),
        )
        self.remote = FakeRemote()
        self.presence = StaticPresence().set("mathis", home=True, room="salon")
        admin = {"password_hash": PASSWORD_HASH, "port": 0, **({"public_url": public_url} if public_url else {})}
        text = CONFIG.format(data_dir=tmp_path, admin=admin)
        if not connectors:
            text += "connectors: []\n"
        self.nestor = Nestor(
            parse_config(text, {}),
            self.registry(),
            environ={"NESTOR_SECRET_KEY": SECRET_KEY},
            token_endpoint=self.provider,
        )
        self.settings = AdminSettings(password_hash=PASSWORD_HASH, public_url=public_url)
        self.app = create_app(self.nestor, self.settings)
        self.base_url = public_url or "http://admin.test"
        self.browser = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=self.base_url)
        self.csrf = ""
        self.pages: list[str] = []  # every page served, to check that no secret is ever rendered

    def registry(self) -> Registry:
        return Registry(
            [
                Plugin(Family.MODEL, "scripted", NoSettings, lambda s, n, x: ScriptedModel(*self.replies)),
                Plugin(Family.CHANNEL, "memory", NoSettings, lambda s, name, x: InMemoryChannel(name)),
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
            ]
        )

    async def __aenter__(self) -> Self:
        await self.nestor.__aenter__()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.browser.aclose()
        await self.nestor.__aexit__(exc_type, exc, tb)

    # -- browsing ---------------------------------------------------------------------------------------

    async def get(self, path: str, **params: str) -> httpx.Response:
        response = await self.browser.get(path, params=params)
        self._seen(response)
        return response

    async def post(
        self, path: str, data: dict[str, str | list[str]] | None = None, *, csrf: bool = True
    ) -> httpx.Response:
        body = {"csrf": self.csrf, **(data or {})} if csrf else dict(data or {})
        response = await self.browser.post(path, data=body)
        self._seen(response)
        return response

    async def login(self, password: str = PASSWORD) -> httpx.Response:
        await self.get("/login")
        response = await self.post("/login", {"password": password})
        if response.status_code == 303:
            await self.get("/journal")  # the logged-in session has its own CSRF token
        return response

    def _seen(self, response: httpx.Response) -> None:
        self.pages.append(f"{response.headers.get('location', '')}\n{response.text}")
        if found := re.search(r'name="csrf" value="([^"]+)"', response.text):
            self.csrf = found.group(1)

    # -- what the provider's consent page does -------------------------------------------------------

    def consent(self, authorize_url: str) -> dict[str, str]:
        """Approve at the provider: the query it sends back to `redirect_uri` (code and state)."""
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(authorize_url).query))
        connections = self.nestor.connections
        assert connections is not None
        issued = query["state"].split(".")[0]
        verifier = connections._pending[issued].verifier  # what only Nestor knows, checked by the provider
        return {"state": query["state"], "code": self.provider.authorize(query["client_id"], verifier)}
