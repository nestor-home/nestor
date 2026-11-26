## Souvenirs : ce que l'assistant retient.

mem-title = Souvenirs
mem-empty = Aucun souvenir pour l'instant.
mem-empty-hint = Je retiens ce qu'on me demande, et ce que j'apprends en conversation.
mem-empty-search = Aucun souvenir ne correspond.
mem-search = Rechercher
mem-search-placeholder = handball, chaudière…
mem-search-submit = Chercher
mem-about = Qui il concerne
mem-about-everyone = Tout le monde
mem-told-by = dit par { $name }
mem-learnt-where = Où il a été appris
mem-correct = Corriger…
mem-correct-title = Corriger le souvenir
mem-correct-description = L'ancienne version reste dans le journal.
mem-corrected = Souvenir corrigé.
mem-forget = Oublier…
mem-forget-title = Oublier ce souvenir ?
mem-forget-confirm = Oublier
mem-forget-text = « { $text } » ne sera plus utilisé.
mem-forgotten = Souvenir oublié.
mem-text = Texte du souvenir
mem-save-hint = ⌘↵ pour enregistrer
mem-lede = Ce que { $assistant } retient du foyer : ce qu'on lui a demandé de retenir, et ce qu'il a appris en conversation.
mem-search-open = Rechercher…
mem-search-title = Rechercher dans les souvenirs
mem-search-for = Souvenirs qui correspondent à « { $q } »
mem-search-clear = Effacer la recherche
mem-open-person = Ouvrir la page de { $name }
mem-kind = Souvenir
mem-told-by-label = Dit par
mem-learnt-in = Appris sur
mem-kept-since = Retenu depuis
mem-changed = Corrigé
mem-place = Rangé dans
mem-shelf-home = Maison
mem-shelf-household = Foyer
mem-shelf-kind = { $shelf ->
    [projects] projet
    [topics] sujet
   *[other] { $shelf }
}
mem-place-option = { $shelf ->
    [projects] { $name } (projet)
    [topics] { $name } (sujet)
   *[other] { $name }
}
mem-tied = Gardé jusqu'à
mem-tied-to = { $kind ->
    [task] la fin de sa tâche
    [alert] la fin de sa veille
   *[other] la fin de { $kind }
}
mem-move = Déplacer…
mem-move-title = Déplacer le souvenir
mem-move-where = Où le ranger
mem-move-new-project = Nouveau projet…
mem-move-new-topic = Nouveau sujet…
mem-move-name = Nom
mem-move-name-placeholder = travaux du toit, jardin…
mem-move-submit = Déplacer
mem-moved = Souvenir déplacé.
mem-tidied = Rangés dernièrement
mem-tidied-empty = Rien de rangé dernièrement.
mem-tidied-empty-hint = Chaque nuit, je fusionne les doublons et mets de côté ce qui ne tient plus. Un souvenir lié à une tâche part quand elle se termine.
mem-retired = { $reason ->
    [merged] Fusionné avec un autre souvenir
    [stale] Mis de côté, périmé
   *[ended] { $tie ->
        [alert] Mis de côté : sa veille est finie
       *[task] Mis de côté : sa tâche est finie
    }
}
mem-retired-into = Fusionné dans « { $text } »
