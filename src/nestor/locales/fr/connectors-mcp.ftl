# Le connecteur MCP distant : son nom, sa description, ses champs et le guide affiché avant d'en connecter un.

connector-mcp-title = Serveur MCP
connector-mcp-description = Tout service qui publie un serveur MCP distant (GitHub, Linear, Notion…) : ses outils, pour le compte que vous connectez.
connector-mcp-field-url = Adresse du serveur
connector-mcp-field-token = Jeton d'accès
connector-mcp-field-client_id = Identifiant du client OAuth
connector-mcp-field-client_secret = Secret du client OAuth
connector-mcp-setup =
    Nestor demande au serveur comment l'autoriser : la plupart vous envoient sur le service pour approuver l'accès, puis vous ramènent ici.
    Donnez un jeton d'accès seulement si le service en délivre un pour cela (un jeton d'accès personnel GitHub).
    Donnez un client OAuth seulement si le serveur n'en enregistre aucun pour Nestor : créez-en un sur le service, avec l'adresse de redirection affichée.

# Pourquoi un serveur n'a pas pu être connecté.
connector-mcp-not-an-address = « { $url } » n'est pas l'adresse d'un serveur.
connector-mcp-authorization = L'autorisation auprès du serveur a échoué. Réessayez, ou donnez un jeton d'accès.
connector-mcp-metadata-unavailable = Les informations d'autorisation du serveur sont indisponibles pour l'instant. Réessayez plus tard.
connector-mcp-metadata-elsewhere = Les informations d'autorisation du serveur renvoient à un autre serveur ({ $named }) : Nestor ne les suit pas.
connector-mcp-auth-methods = Le serveur d'autorisation n'accepte que des authentifications de client que Nestor ne gère pas ({ $methods }).
mcp-unreachable = { $server } ne répond pas.
mcp-refused = { $server } a refusé les identifiants donnés.
mcp-answered = { $server } a répondu par une erreur (HTTP { $status }).
