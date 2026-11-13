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

role-owner-hint = Tout, y compris les comptes et les rôles.
role-admin-hint = Connexions, satellites et supervision, sans les comptes.
role-member-hint = Son journal, ses connexions et ses souvenirs.


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
error-not-found = Introuvable.
error-status = Nestor a répondu par une erreur ({ $status }).
error-unexpected = Erreur inattendue.

forbidden-title = Section réservée
forbidden-text = Votre rôle n'y donne pas accès. Le propriétaire peut le changer dans Comptes.
not-found-title = Cette page n'existe pas
not-found-text = Le lien est peut-être ancien ou mal copié.
not-found-back = Revenir à l'accueil
household-everyone-capital = Tout le foyer
breadcrumbs = Fil d'Ariane
person-picker-empty = Aucune personne de ce nom.
action-show-choices = Afficher les choix
role-guest-hint = Son journal seulement.

# Les marques génériques, nommées par des mots plutôt que par une marque (src/lib/brands.tsx).
brand-satellites = Satellites
brand-web-page = Page web
brand-voice = Voix
brand-openai-compatible = API compatible OpenAI
brand-sdk = SDK { $language }
origin-a-conversation = une conversation
