# `nestor usage`: what Nestor's calls to models cost, read from the data folder.

usage-help = What Nestor's calls to models cost, by model, person, use or any other dimension.
usage-days-help = How many days back (30 by default).
usage-by-help = What to break the spending down by.
usage-total = Last { $days } days: { $spent }, { $calls } { $calls ->
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
