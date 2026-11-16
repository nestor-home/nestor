"""What Nestor's HTTP servers share (the admin, its MCP server, the inbound webhooks): reading a body within a limit,
and handing out a file that must never run where it is served."""

from nestor.http.bodies import read_body
from nestor.http.files import file_response

__all__ = ["file_response", "read_body"]
