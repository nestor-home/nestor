## Configuration: the configuration file edited by section, its secrets, its history, the restart.

cfg-title = Configuration
cfg-intro = Checked before it is written, applied at the next restart.
cfg-nav = Parts of the configuration
cfg-group-agent = The agent
cfg-group-parts = Components
cfg-group-instance = Instance
cfg-group-vault = Vault and versions
cfg-unknown-page = This part of the configuration does not exist.
cfg-modified = modified

## Forms
cfg-advanced = { $count ->
    [one] Advanced · 1 setting
   *[other] Advanced · { $count } settings
}
cfg-default = Default ({ $value })
cfg-list-default = Empty: { $value } by default.
cfg-list-empty = No items.
cfg-add-item = Add
cfg-add-entry = Add an entry
cfg-item-n = item { $n }
cfg-item-of = { $field }, item { $n }
cfg-map-key = { $field }, name { $n }
cfg-map-value = { $field }, value of { $key }
cfg-move-up = Move { $item } up
cfg-move-down = Move { $item } down
cfg-remove-item = Remove { $item }
cfg-edit-item = Edit { $item }
cfg-json-invalid = Invalid JSON: fix it, or the previous value stays.
cfg-secret-set = set · { $preview }
cfg-secret-unset = not set
cfg-secret-reference = reference { $reference }
cfg-secret-replace = Replace
cfg-secret-replace-label = Replace { $field }
cfg-secret-keep = Keep current
cfg-secret-placeholder = new value

## Pages
cfg-people = People
cfg-people-empty = Nobody in the household yet.
cfg-add-person = Add a person
cfg-remove-person-title = Remove { $name } from the household?
cfg-remove-person-text = The person leaves the file at the next save; their accounts and memories stay in the database.
cfg-add-component = Add…
cfg-add-kind = Add: { $kind }
cfg-choose-kind = Choose…
cfg-pick-title = { $slot }: add
cfg-pick-text = The plugins installed on this instance. The form comes next.
cfg-required-fields = { $count ->
    [0] nothing required
    [one] 1 required setting
   *[other] { $count } required settings
}
cfg-slot-unset = Nothing configured.
cfg-slot-none = No components.
cfg-slot-required = At least one is needed to start.
cfg-slot-optional = Optional.
cfg-no-plugin = No plugin of this kind is installed.
cfg-no-plugin-hint = Install one in Nestor's environment, then restart.
cfg-kind-missing = The plugin “{ $kind }” is not installed: this component cannot start.
cfg-kind-missing-short = not installed
cfg-remove = Remove
cfg-remove-title = Remove { $name }?
cfg-remove-text = The component leaves the file at the next save. Its secrets stay in the vault.
cfg-sheet-note = Changes go into the draft: nothing is written before “Save”.
cfg-done = Done
cfg-cancel-add = Cancel adding

## Saving
cfg-save-region = Unsaved changes
cfg-checking = checking…
cfg-problems = { $count ->
    [one] 1 problem
   *[other] { $count } problems
}
cfg-changes = { $count ->
    [one] 1 change
   *[other] { $count } changes
}
cfg-changes-title = Changes
cfg-changes-text = What saving will write to the file. Secrets are never shown.
cfg-change-added = added
cfg-change-removed = removed
cfg-change-changed = changed
cfg-change-becomes = becomes
cfg-change-secret = secret changed
cfg-no-change = No changes.
cfg-discard = Discard changes
cfg-discard-title = Discard the changes?
cfg-discard-text = The draft goes back to the file as written.
cfg-discard-confirm = Discard
cfg-save = Save
cfg-saving = Saving…
cfg-saved = Noted: I'll apply it at the next restart.
cfg-leave-title = Leave without saving?
cfg-leave-text = The configuration changes will be lost.
cfg-leave-stay = Stay
cfg-leave-go = Leave

## Restarting
cfg-restart-required = Restart required
cfg-pending = { $count ->
    [0] the configuration changed
    [one] 1 pending change
   *[other] { $count } pending changes
}
cfg-pending-show = see what is pending
cfg-restart = Restart…
cfg-restart-ask = An administrator needs to restart the instance.
cfg-restart-title = Restart { $agent }?
cfg-restart-text = { $agent } stops cleanly and starts again with the same command, usually in a few seconds.
cfg-restart-channels = Channels close: a conversation under way is cut.
cfg-restart-tasks = Remote tasks keep running; following them resumes after.
cfg-restart-apply = { $count ->
    [one] The saved change applies.
   *[other] The saved changes apply.
}
cfg-restart-now = Restart now
cfg-restarting = Restarting, back in a moment.
cfg-restarting-hint = The page resumes by itself.
cfg-restarting-slow = This is taking longer than usual: check the service's log if nothing comes back.
cfg-restart-done = I'm back: the configuration is applied.

cfg-restart-signed-out = I'm back, configuration applied. Sign in again to continue.

## Secrets
cfg-secrets = Secrets
cfg-secrets-intro = Encrypted, outside the file, which refers to them as ${"{"}secret:name{"}"}. Never shown again.
cfg-secrets-list = Vault
cfg-secrets-empty = No secrets.
cfg-secrets-empty-hint = A secret typed into a form is put here when saving.
cfg-secret-new = New secret
cfg-secret-define = Set
cfg-secret-used-by = Used by
cfg-secret-unused = Used nowhere.
cfg-secret-replace-title = Replace { $name }
cfg-secret-form-text = The value is encrypted and never shown again, only a preview.
cfg-secret-name = Name
cfg-secret-name-hint = For example tools.home.token; the file refers to it as ${"{"}secret:name{"}"}.
cfg-secret-value = Value
cfg-secret-save = Save
cfg-secret-saved = Secret { $name } saved.
cfg-secret-delete = Delete
cfg-secret-delete-label = Delete { $name }
cfg-secret-delete-title = Delete { $name }?
cfg-secret-delete-text = The value is erased from the vault; nothing can bring it back.
cfg-secret-in-use-text = The configuration still refers to it: once deleted, those settings cannot start until they change.
cfg-secret-delete-anyway = Delete anyway
cfg-secret-deleted = Secret { $name } deleted.

## History
cfg-history = History
cfg-history-intro = Every save keeps the previous version.
cfg-history-versions = Earlier versions
cfg-history-empty = No earlier versions.
cfg-history-empty-hint = The first appears at the first save from the admin.
cfg-history-size = { $size } bytes
cfg-history-version = Version of { $day } at { $time }
cfg-history-would = { $count ->
    [one] Restoring would change 1 setting:
   *[other] Restoring would change { $count } settings:
}
cfg-history-same = Same as the current file.
cfg-history-invalid = This version can no longer be used as it is:
cfg-restore = Restore
cfg-restore-title = Restore this version?
cfg-restore-text = The current file goes to the history; the chosen version applies at the next restart.
cfg-restore-dirty = Save or discard your current changes first.
cfg-restored = Version restored: a restart will apply it.
