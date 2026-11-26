# La suite de banc alert-triage : un mail correspond-il à une alerte.

bench-alert-triage-description = quels mails reçus correspondent à une alerte, par algorithme de tri (batch, per-alert) et par modèle
bench-alert-triage-no-header = le jeu de données doit commencer par {"{"}"dataset": "alert-triage", "version": <nombre>{"}"}
bench-alert-triage-bad-record = ligne { $line } du jeu : ni une alerte (alert, condition), ni un mail (case, title)
bench-alert-triage-bad-label = cas { $case } : alerte inconnue { $alert } dans expected

bench-alert-triage-matches-f1 = correspondances, F1
bench-alert-triage-matches-precision = correspondances, précision
bench-alert-triage-matches-recall = correspondances, rappel
bench-alert-triage-missed = correspondances manquées
bench-alert-triage-false-alarms = fausses alertes
bench-alert-triage-unsorted = non triés

bench-alert-triage-missed-list = Correspondances manquées
bench-alert-triage-false-alarms-list = Fausses alertes
bench-alert-triage-item = { $case } « { $title } », { $alert }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
