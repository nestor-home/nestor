# `nestor usage`: what Nestor's calls to models cost, read from the data folder.

usage-help = What Nestor's calls to models cost, by model, person, use or any other dimension.
usage-period-help = The period: today, 7d, 30d (the default), month or 90d.
usage-by-help = What to break the spending down by.
usage-total = { $period ->
    [today] Today
    [week] Last 7 days
    [month] This month
    [quarter] Last 90 days
   *[other] Last 30 days
}: { $spent }, { $calls } { $calls ->
    [one] call
   *[other] calls
}{ $unknown ->
    [0] {""}
   *[other] , { $unknown } of unknown cost
}.
usage-month = This month: { $spent } so far, heading for { $projected }.
usage-by = By { usage-dimension }:
usage-line = { $spent }  { $calls } { $calls ->
    [one] call
   *[other] calls
}{ $unknown ->
    [0] {""}
   *[other] , { $unknown } of unknown cost
}
