# La suite de banc watch-triage : un mail correspond-il à une veille, est-il urgent.

bench-watch-triage-description = quels mails reçus correspondent à une veille, lesquels sont urgents, par algorithme de tri (gate, no-gate, hints, batch) et par modèle
bench-watch-triage-no-header = le jeu de données doit commencer par {"{"}"dataset": "watch-triage", "version": <nombre>{"}"}
bench-watch-triage-bad-record = ligne { $line } du jeu : ni une veille (watch, what), ni un mail (case, title)
bench-watch-triage-bad-label = cas { $case } : veille ou étiquette inconnue { $watch } (étiquettes : match, urgent)

bench-watch-triage-matches-f1 = correspondances, F1
bench-watch-triage-matches-precision = correspondances, précision
bench-watch-triage-matches-recall = correspondances, rappel
bench-watch-triage-urgent-precision = urgence, précision
bench-watch-triage-urgent-recall = urgence, rappel
bench-watch-triage-missed = correspondances manquées
bench-watch-triage-dropped-by-keywords = manquées par les mots-clés
bench-watch-triage-false-alarms = fausses alertes
bench-watch-triage-unread-answers = réponses illisibles

bench-watch-triage-missed-list = Correspondances manquées
bench-watch-triage-false-alarms-list = Fausses alertes
bench-watch-triage-not-urgent-list = Urgents annoncés comme non urgents
bench-watch-triage-missed-item = { $case } « { $title } », { $watch } : écarté par { $stage ->
    [keywords] les mots-clés
   *[model] le modèle
}{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
bench-watch-triage-item = { $case } « { $title } », { $watch }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
