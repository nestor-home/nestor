# La suite de banc notifications : l'agent se tait-il quand il n'a rien à dire, et seulement alors.

bench-notifications-description = si l'agent transmet une notification ou se tait avec sa raison, par modèle
bench-notifications-no-header = le jeu de données doit commencer par {"{"}"dataset": "notifications", "version": <nombre>{"}"}
bench-notifications-bad-record = ligne { $line } du jeu : un cas demande case, une source (task, alert, message, tool, confirmation), text et expected (tell ou silent)

bench-notifications-accuracy = bonnes décisions
bench-notifications-unsaid = tu alors qu'il fallait dire
bench-notifications-noise = dit alors qu'il n'y avait rien à dire
bench-notifications-silences-with-reason = silences avec une raison
bench-notifications-marker-sent = marqueur de silence envoyé
bench-notifications-failed = livraisons en échec

bench-notifications-unsaid-list = Tu alors qu'il fallait dire
bench-notifications-noise-list = Dit alors qu'il n'y avait rien à dire
bench-notifications-item = { $case } { $text }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
