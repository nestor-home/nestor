# The notifications bench suite: does the agent stay silent when there is nothing to tell, and only then.

bench-notifications-description = whether the agent tells a notification or stays silent with its reason, per model
bench-notifications-no-header = the dataset must start with {"{"}"dataset": "notifications", "version": <number>{"}"}
bench-notifications-bad-record = dataset line { $line }: a case needs case, a source (task, alert, message, tool, confirmation), text and expected (tell or silent)

bench-notifications-accuracy = right decisions
bench-notifications-unsaid = silent when it had to tell
bench-notifications-noise = told when there was nothing to tell
bench-notifications-silences-with-reason = silences with a reason
bench-notifications-marker-sent = silence marker sent
bench-notifications-failed = failed deliveries

bench-notifications-unsaid-list = Silent when it had to tell
bench-notifications-noise-list = Told when there was nothing to tell
bench-notifications-item = { $case } { $text }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
