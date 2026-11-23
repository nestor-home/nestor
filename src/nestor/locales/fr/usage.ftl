# `nestor usage` : ce que coûtent les appels de Nestor aux modèles, lu dans le dossier de données.

usage-help = Ce que coûtent les appels de Nestor aux modèles, par modèle, personne, usage ou toute autre dimension.
usage-period-help = La période : today, 7d, 30d (par défaut), month ou 90d.
usage-by-help = Selon quoi répartir la dépense.
usage-total = { $period ->
    [today] Aujourd’hui
    [week] 7 derniers jours
    [month] Ce mois-ci
    [quarter] 90 derniers jours
   *[other] 30 derniers jours
} : { USD($spent) }, { $calls } { $calls ->
    [one] appel
   *[other] appels
}{ $unknown ->
    [0] {""}
   *[other] , dont { $unknown } de coût inconnu
}.
usage-month = Ce mois-ci : { USD($spent) } jusqu’ici, en route vers { USD($projected) }.
usage-by = Par { usage-dimension } :
usage-line = { USD($spent) }  { $calls } { $calls ->
    [one] appel
   *[other] appels
}{ $unknown ->
    [0] {""}
   *[other] , dont { $unknown } de coût inconnu
}
