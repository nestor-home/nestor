## Communs à tous les écrans : temps, comptes, rôles, états, actions et erreurs génériques.

time-today = aujourd'hui { $time }
time-yesterday = hier { $time }
time-day = { $day } { $time }
time-just-now = à l'instant
day-today = aujourd'hui
day-yesterday = hier
remaining = { $minutes } min { $seconds } s
duration-ms = { $ms } ms
duration-s = { $seconds } s
duration-min = { $minutes } min { $seconds }
duration-h = { $hours } h { $minutes }

household-everyone = tout le foyer
household-nobody = personne

role-owner = propriétaire
role-admin = administrateur
role-member = membre
role-owner-hint = Tout, y compris les comptes et les rôles.
role-admin-hint = Connexions, satellites et supervision ; pas les comptes.
role-member-hint = Son journal, ses connexions et ses souvenirs.

connection-status-connected = connectée
connection-status-needs-reauth = à réautoriser
connection-status-error = erreur
risk-read = lecture
risk-write = écriture
risk-sensitive = sensible
auth-oauth2 = OAuth
auth-secret = identifiants
auth-none = aucune
task-status-running = en cours
task-status-completed = terminée
task-status-failed = en échec
task-status-cancelled = annulée

action-cancel = Annuler
action-save = Enregistrer
action-saving = Enregistrement…
action-retry = Réessayer
action-close = Fermer
action-copy = copier
action-copied = copié
action-copy-label = Copier { $what }
action-choose = Choisir…
action-see = Voir
loading = Chargement…
empty-generic = Rien pour l'instant.

error-network = Nestor ne répond pas. Vérifiez qu'il tourne, puis réessayez.
error-unauthenticated = Votre session a expiré : reconnectez-vous.
error-forbidden = Votre rôle ne permet pas cette action.
error-not-found = Introuvable : cet élément n'existe pas ou plus.
error-status = Nestor a répondu par une erreur ({ $status }).
error-unexpected = Une erreur inattendue s'est produite.

forbidden-title = Section réservée
forbidden-text = Votre rôle ne donne pas accès à cette partie de l'administration. Le propriétaire du foyer peut changer votre rôle depuis Comptes.
not-found-title = Cette page n'existe pas
not-found-text = L'adresse est peut-être ancienne ou mal recopiée.
not-found-back = Revenir à aujourd'hui
household-everyone-capital = Tout le foyer
breadcrumbs = Fil d'Ariane
person-picker-empty = Personne de ce nom.
action-show-choices = Afficher les choix
role-guest = invité
role-guest-hint = Son journal seulement.
