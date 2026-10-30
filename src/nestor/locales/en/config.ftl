# Editing the configuration from the admin: problems, sections, slots and the fields' titles.
# A field's title is `config-<group>-<field>`, else the generic `config-field-<field>`; its help is
# `config-<group>-<field>-help`. Plugins ship the titles of their own settings (`config-<family>-<kind>-…`).

config-error-missing = { $path }: required.
config-error-extra = { $path }: unknown setting.
config-error-invalid = { $path }: { $detail }
config-error-unknown-kind = { $path }: no plugin “{ $detail }” is installed.
config-error-reference = { $path }: the environment variable { $detail } is not set.
config-error-secret = { $path }: the secret { $detail } is not set.

config-section-persona = Persona
config-section-household = Household
config-section-initiative = Initiative
config-section-admin = Admin
config-section-data_dir = Data

config-slot-model = Language model
config-slot-triage_model = Triage model
config-slot-channels = Channels
config-slot-executors = Executors
config-slot-tools = Tools
config-slot-inbound = Inbound sources
config-slot-presence = Presence
config-slot-connectors = Connectors

config-field-name = Name
config-field-kind = Kind
config-field-id = Identifier
config-field-host = Host
config-field-port = Port
config-field-url = Address
config-field-base_url = Address of the API
config-field-api_key = API key
config-field-token = Token
config-field-model = Model
config-field-room = Room
config-field-style = Writing style
config-field-timeout_s = Timeout (seconds)
config-field-data_dir = Data folder
config-core-data_dir-help = Where the database, the vault and the configuration history live.
config-persona-character = Character
config-persona-character-help = Who the assistant is and how it speaks, in its own words.
config-persona-locale = Language
config-persona-locale-help = The household's language (BCP 47, e.g. fr-FR): fixed phrases and the admin's default.
config-persona-language = Language named to the model
config-persona-timezone = Time zone
config-household-accounts = Accounts on channels
config-household-accounts-help = How each channel knows this person: telegram:123456789, voice:*.
config-household-reach = Where to write to them
config-initiative-quiet_hours = Quiet hours
config-initiative-quiet_hours-help = For example 22:30-07:30: nothing is said aloud then, unless urgent.
config-initiative-main_room = Main room
config-initiative-follow_up_after_s = Written follow-up after (seconds)
config-admin-public_url = Public address
config-admin-public_url-help = How the household's browsers reach the admin, e.g. https://nestor.example.org.
config-admin-relay_url = OAuth relay
