# Modifier la configuration depuis l'administration : problèmes, sections, emplacements, titres des champs.

config-error-missing = { $path } : obligatoire.
config-error-extra = { $path } : réglage inconnu.
config-error-invalid = { $path } : { $detail }
config-error-unknown-kind = { $path } : aucun greffon « { $detail } » n'est installé.
config-error-reference = { $path } : la variable d'environnement { $detail } n'est pas définie.
config-error-secret = { $path } : le secret { $detail } n'est pas défini.

config-section-persona = Personnage
config-section-household = Foyer
config-section-initiative = Initiative
config-section-admin = Administration
config-section-data_dir = Données

config-slot-model = Modèle de langage
config-slot-triage_model = Modèle de tri
config-slot-channels = Canaux
config-slot-executors = Exécutants
config-slot-tools = Outils
config-slot-inbound = Sources entrantes
config-slot-presence = Présence
config-slot-connectors = Connecteurs

config-field-name = Nom
config-field-kind = Type
config-field-id = Identifiant
config-field-host = Hôte
config-field-port = Port
config-field-url = Adresse
config-field-base_url = Adresse de l'API
config-field-api_key = Clé d'API
config-field-token = Jeton
config-field-model = Modèle
config-field-room = Pièce
config-field-style = Style d'écriture
config-field-timeout_s = Délai (secondes)
config-field-data_dir = Dossier des données
config-core-data_dir-help = Là où vivent la base de données, le coffre et l'historique de la configuration.
config-persona-character = Caractère
config-persona-character-help = Qui est l'assistant et comment il parle, avec ses propres mots.
config-persona-locale = Langue
config-persona-locale-help = La langue du foyer (BCP 47, ex. fr-FR) : phrases fixes et langue par défaut de l'administration.
config-persona-language = Langue nommée au modèle
config-persona-timezone = Fuseau horaire
config-household-accounts = Comptes sur les canaux
config-household-accounts-help = Comment chaque canal connaît cette personne : telegram:123456789, voice:*.
config-household-reach = Où lui écrire
config-initiative-quiet_hours = Heures calmes
config-initiative-quiet_hours-help = Par exemple 22:30-07:30 : rien n'est dit à voix haute, sauf urgence.
config-initiative-main_room = Pièce principale
config-initiative-follow_up_after_s = Relance écrite après (secondes)
config-admin-public_url = Adresse publique
config-admin-public_url-help = Comment les navigateurs du foyer joignent l'administration, ex. https://nestor.example.org.
config-admin-relay_url = Relais OAuth
