## Alerts: what the assistant does later, regularly, or when something happens.

alert-empty-hint = Ask { $assistant }: “remind me tomorrow at 9 to call the plumber”, “tell me when the parcel arrives”, “tell me once the stock is under 135”.
alert-for = for { $name }
alert-kind = { $kind ->
    [mail] mail
    [feed] feeds
    [page] web pages
   *[other] { $kind }
}
alert-once-at = Once, { $when }
alert-every-day = every day
alert-on-kinds = When { $kinds } arrive
alert-rang-count = { $count ->
    [one] Rang once
   *[other] Rang { $count } times
}
alert-never-rang = Has not rung yet
alert-unknown = This alert does not exist or has ended.
alert-cancelled-notice = Cancelled: it will not ring again.
alert-created = created { $when }
alert-until = until { $when }
alert-cancel = Cancel the alert
alert-cancel-action = Cancel the alert…
alert-cancel-title = Cancel this alert?
alert-cancel-description = “{ $what }” will not ring again.
alert-trigger = Rings
alert-condition = Only if:
alert-frequency-term = Frequency
alert-urgent = Urgent: told at once, even in quiet hours
alert-so-far = So far
alert-rings = Why it rang
alert-rings-empty = It has not rung yet.
alert-found = What it went through
alert-found-empty = Nothing yet.
alert-asked-in = Asked in
