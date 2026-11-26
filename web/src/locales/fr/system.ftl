## Système : ce que l'instance a assemblé au démarrage, et l'état de chaque pièce.

sys-title = Système
sys-unwell = { $count ->
    [one] 1 composant à surveiller
   *[other] { $count } composants à surveiller
}
sys-all-well = tout va bien
sys-slot-model = Modèles
sys-slot-executor = Exécutants
sys-slot-channel = Canaux
sys-slot-home = Maison
sys-slot-tools = Outils
sys-slot-inbound = Sources entrantes
sys-slot-connector = Connecteurs
sys-slot-satellite = Satellites
sys-health-ok = ok
sys-health-degraded = dégradé
sys-health-down = en panne
sys-health-unknown = inconnu

## Mises à jour : une version plus récente de Nestor, ce qui a changé et comment l'installer.

upd-available = Nouvelle version
upd-available-version = Mise à jour disponible : { $version }
upd-title = Nestor { $version } est là
upd-description = Notes de version et mise à jour.
upd-behind = { $count ->
    [one] une version de retard
   *[other] { $count } versions de retard
}
upd-install = Installer la { $version }
upd-install-title = Installer Nestor { $version } ?
upd-install-description = Nestor installe la nouvelle version, vérifie votre configuration, puis redémarre. En cas d'échec, il reste sur la { $running }.
upd-install-confirm = Installer et redémarrer
upd-install-hint = Redémarrage après l'installation.
upd-installing = Installation de la { $version }…
upd-failed = La { $version } ne s'est pas installée. Nestor reste sur la { $running }.
upd-breaking = Cette version change les données ou la configuration : relisez les notes avant de mettre à jour.
upd-outdated = { $count ->
    [one] Ce satellite ne pourra plus se connecter : mettez-le à jour sur l’appareil, après le serveur.
   *[other] Ces { $count } satellites ne pourront plus se connecter : mettez-les à jour sur chaque appareil, après le serveur.
}
upd-release = Version { $version }
upd-notes = Notes de version
upd-kind-breaking = Ruptures
upd-kind-feature = Nouveautés
upd-kind-fix = Corrections
upd-kind-other = Autres
upd-how = Mettre à jour
upd-how-container = Dans le dossier de compose.yaml :
upd-how-uv-tool = Sur la machine de Nestor :
upd-how-pip = Sur la machine de Nestor :
upd-how-editable = Nestor tourne depuis un checkout : mettez-le à jour avec git.
upd-then-restart = Puis redémarrez Nestor.
upd-then-ask = Puis demandez à un administrateur de redémarrer Nestor.
upd-command = la commande
sys-fallback = secours : { $model }

sys-executors = Les outils de Nestor pour les exécutants
sys-executors-intro = Pendant une tâche, les exécutants joignent Nestor à { $url } : leur brief, ce que la personne a déjà dit, leurs questions, leurs fichiers. Chacun appelle avec sa propre clé.
sys-executors-off = Les exécutants ne peuvent pas joindre Nestor : donnez une public_url à l'admin et définissez NESTOR_SECRET_KEY, puis redémarrez.
sys-executor-tools = { $tools ->
    [passed] Nestor lui passe ses outils à chaque tâche
    [configured] Sa propre configuration déclare les outils de Nestor
   *[none] Travaille sans les outils de Nestor
}
sys-executor-key-made = Clé créée
sys-executor-key-used = dernier usage
sys-executor-key-unused = pas encore utilisée
sys-executor-no-key = Aucune clé
sys-executor-key-make = Créer une clé
sys-executor-key-renew = Renouveler
sys-executor-key-revoke = Révoquer
sys-executor-make-title = Créer une clé pour { $name } ?
sys-executor-make-body = { $tools ->
    [passed] Nestor la passe à { $name } à chaque tâche.
   *[other] Elle n'est montrée qu'une fois, pour la coller dans la configuration de { $name }.
}
sys-executor-renew-title = Renouveler la clé de { $name } ?
sys-executor-renew-body = La clé actuelle cesse aussitôt de fonctionner. { $tools ->
    [passed] Nestor passe la nouvelle à { $name } à sa prochaine tâche.
   *[other] Collez la nouvelle dans la configuration de { $name }.
}
sys-executor-revoke-title = Révoquer la clé de { $name } ?
sys-executor-revoke-body = { $name } ne joint plus les outils de Nestor, ni les tâches qu'il a en cours.
sys-executor-key-title = La clé de { $name }
sys-executor-key-once = Montrée seulement maintenant : Nestor la garde chiffrée et ne la montre plus jamais.
sys-executor-key-label = la clé
sys-executor-passed = Nestor la passe à { $name } à chaque tâche : rien à coller.
sys-executor-profile = Ajoutez ceci à la configuration de { $name } (le config.yaml d'un profil Hermes), puis mettez nestor_mcp: true sur cet exécutant dans la configuration de Nestor.
sys-executor-setup-label = ce qu'il faut ajouter
sys-parts = { $count ->
    [one] 1 composant
   *[other] { $count } composants
}
sys-attention = À regarder
sys-instance = Cette instance
sys-slot-voice = Voix
sys-fix-down = Rien ne passe par lui pour l'instant. Vérifiez que le service derrière répond et que ses réglages sont bons.
sys-fix-degraded = Il fonctionne en partie : ce qu'il signale dit ce qui manque.
sys-configure = Configurer
sys-docs = Documentation
sys-fact-state = état
sys-fact-service = service
sys-fact-type = type
sys-fact-fallback = secours
sys-fact-adapter = adaptateur
sys-fact-version = version
sys-fact-can = sait
sys-runs = Fait tourner { $agent }.
sys-restart-waiting = { $count ->
    [0] Un redémarrage est attendu.
    [one] 1 changement attend un redémarrage.
   *[other] { $count } changements attendent un redémarrage.
}
sys-restart = Redémarrer…
sys-restart-title = Redémarrer { $agent } ?
sys-restart-text = Il s'arrête proprement et repart en quelques secondes. Une conversation en cours est coupée, les tâches déléguées continuent, et chacun se reconnecte.
sys-restart-now = Redémarrer maintenant
upd-available-running = La { $latest } est sortie. Cette instance tourne sur la { $running }.
