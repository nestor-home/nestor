# La suite de banc routing : l'agent confie-t-il une demande au bon exécutant, prend-il le bon outil, ou répond-il lui-même.

bench-routing-description = si l'agent confie une demande au bon exécutant, prend le bon outil ou répond lui-même, par modèle
bench-routing-no-header = le jeu de données doit commencer par {"{"}"dataset": "routing", "version": <nombre>{"}"}
bench-routing-bad-record = ligne { $line } du jeu : un cas demande case, said et expected (une liste de paliers de routes : tool:<nom>, delegate:<exécutant> ou none)

bench-routing-accuracy = bonnes routes
bench-routing-missed = pas confié alors qu'il fallait
bench-routing-needless = confié alors qu'il ne fallait pas
bench-routing-wrong-executor = confié au mauvais exécutant
bench-routing-failed = tours en échec

bench-routing-missed-list = Pas confié
bench-routing-needless-list = Confié sans raison
bench-routing-wrong-executor-list = Confié au mauvais exécutant
bench-routing-other-list = Un autre outil, ou aucun là où il en fallait un
bench-routing-item = { $case } « { $said } » → { $route }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
