# The alert-triage bench suite: does a mail match an alert.

bench-alert-triage-description = which incoming mails match an alert, per triage algorithm (batch, per-alert) and model
bench-alert-triage-no-header = the dataset must start with {"{"}"dataset": "alert-triage", "version": <number>{"}"}
bench-alert-triage-bad-record = dataset line { $line }: neither an alert (alert, condition) nor a mail (case, title)
bench-alert-triage-bad-label = case { $case }: unknown alert { $alert } in expected

bench-alert-triage-matches-f1 = matches, F1
bench-alert-triage-matches-precision = matches, precision
bench-alert-triage-matches-recall = matches, recall
bench-alert-triage-missed = missed matches
bench-alert-triage-false-alarms = false alarms
bench-alert-triage-unsorted = unsorted

bench-alert-triage-missed-list = Missed matches
bench-alert-triage-false-alarms-list = False alarms
bench-alert-triage-item = { $case } “{ $title }”, { $alert }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
