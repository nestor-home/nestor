# `nestor usage` : ce que coûtent les appels de Nestor aux modèles, lu dans le dossier de données.

usage-help = Ce que coûtent les appels de Nestor aux modèles, par modèle, personne, usage ou toute autre dimension.
usage-days-help = Combien de jours en arrière (30 par défaut).
usage-by-help = Selon quoi répartir la dépense.
usage-total = { $days } derniers jours : { $spent }, { $calls } { $calls ->
    [one] appel
   *[other] appels
}{ $unknown ->
    [0] {""}
   *[other] , dont { $unknown } de coût inconnu
}.
usage-month = Ce mois-ci : { $spent } jusqu’ici, en route vers { $projected }.
usage-by = Par { usage-dimension } :
usage-line = { $spent }  { $calls } { $calls ->
    [one] appel
   *[other] appels
}{ $unknown ->
    [0] {""}
   *[other] , dont { $unknown } de coût inconnu
}
