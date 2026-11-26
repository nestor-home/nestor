# La suite de banc memory-recall : les souvenirs utiles à un tour arrivent-ils dans son prompt.

bench-memory-recall-description = quels souvenirs arrivent dans le prompt d'un tour, et combien d'inutiles avec eux, par stratégie de récupération
bench-memory-recall-no-header = le jeu de données doit commencer par {"{"}"dataset": "memory-recall", "version": <nombre>{"}"}
bench-memory-recall-bad-record = ligne { $line } du jeu : ni un souvenir (memory, text), ni un épisode (episode, summary), ni un cas (case, said, kind : direct, paraphrase, contradiction, premise, other-person, episode, place, duplicate, obsolete, note, private ou none), ni une note d'exécutant (note, task, requester, text)
bench-memory-recall-unknown = cas { $case } : souvenir inconnu { $memory }

bench-memory-recall-recall = rappel
bench-memory-recall-recall-direct = rappel, mots partagés
bench-memory-recall-recall-paraphrase = rappel, paraphrases
bench-memory-recall-recall-contradiction = rappel, souvenir qui en remplace un autre
bench-memory-recall-recall-premise = rappel, ce qui est dit contredit un souvenir
bench-memory-recall-recall-other-person = rappel, même sujet chez quelqu'un d'autre
bench-memory-recall-recall-episode = rappel, conversation passée de la personne
bench-memory-recall-recall-place = rappel, projet ou thème nommé
bench-memory-recall-recall-duplicate = rappel, fait gardé deux fois
bench-memory-recall-recall-obsolete = rappel, à côté d'un souvenir dont la tâche ou l'alerte est finie
bench-memory-recall-recall-note = rappel, à côté des notes d'une tâche
bench-memory-recall-complete = tours qui reçoivent tous leurs souvenirs
bench-memory-recall-injected-per-case = souvenirs injectés par tour
bench-memory-recall-stale-injected = souvenirs périmés injectés, par contradiction
bench-memory-recall-misleading-injected = souvenirs d'une autre personne injectés, par cas
bench-memory-recall-others-conversations-injected = conversations d'une autre personne injectées (doit rester à 0)
bench-memory-recall-noise-when-nothing-matters = souvenirs injectés quand aucun ne sert
bench-memory-recall-duplicates-injected = anciennes copies d'un fait injectées, par cas de doublon
bench-memory-recall-obsolete-injected = souvenirs d'une tâche ou d'une alerte finie injectés, par tour
bench-memory-recall-notes-injected = notes d'exécutant injectées comme souvenirs (doit rester à 0)

bench-memory-recall-missed-list = Souvenirs manqués
bench-memory-recall-item = { $case } « { $said } » : { $memory }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
