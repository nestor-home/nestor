"""The admin web interface: plug services in, see why the assistant spoke, manage tasks, watches, memories.

A layer above the runtime: it is built on an assembled `Nestor` and served next to it by
`AdminServer`. Pages are server-rendered French HTML; every one needs the household password.
"""

from nestor.admin.app import create_app
from nestor.admin.auth import hash_password, verify_password
from nestor.admin.server import AdminServer
from nestor.admin.settings import AdminSettings

__all__ = ["AdminServer", "AdminSettings", "create_app", "hash_password", "verify_password"]
