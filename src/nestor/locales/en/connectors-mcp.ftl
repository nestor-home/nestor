# The remote MCP connector: its name, description, fields and the guide shown before connecting one.

connector-mcp-title = MCP server
connector-mcp-description = Any service that publishes a remote MCP server (GitHub, Linear, Notion…): its tools, for the account you connect.
connector-mcp-field-url = Server address
connector-mcp-field-token = Access token
connector-mcp-field-client_id = OAuth client ID
connector-mcp-field-client_secret = OAuth client secret
connector-mcp-setup =
    Nestor asks the server how to authorise it: most send you to the service to approve access, then back here.
    Give an access token only when the service issues one for this (a GitHub personal access token).
    Give an OAuth client only when the server registers none for Nestor: create one at the service, with the redirect address shown.

# Why a server could not be connected.
connector-mcp-not-an-address = “{ $url }” is not the address of a server.
connector-mcp-authorization = The server's authorization failed. Try again, or give an access token.
connector-mcp-metadata-unavailable = The server's authorization details are unavailable for now. Try again later.
connector-mcp-metadata-elsewhere = The server's authorization details point to another server ({ $named }): Nestor does not follow them.
connector-mcp-auth-methods = The server's authorization server only takes client authentications Nestor does not support ({ $methods }).
mcp-unreachable = { $server } does not answer.
mcp-refused = { $server } refused the credentials given.
mcp-answered = { $server } answered with an error (HTTP { $status }).
