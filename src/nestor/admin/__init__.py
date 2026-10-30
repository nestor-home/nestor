"""The admin: accounts sign in to a JSON API (`/api/v1`) that the web front of `web/` is built on.

A layer above the runtime: it is built on an assembled `Nestor` and served next to it by `AdminServer`.
"""

from nestor.admin.api.v1 import api_app, openapi_text
from nestor.admin.app import create_app
from nestor.admin.auth import read_token, token_path
from nestor.admin.server import AdminServer
from nestor.admin.settings import AdminSettings

__all__ = ["AdminServer", "AdminSettings", "api_app", "create_app", "openapi_text", "read_token", "token_path"]
