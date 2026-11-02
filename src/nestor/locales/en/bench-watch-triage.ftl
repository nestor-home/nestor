# The watch-triage bench suite: does a mail match a watch, and is it urgent.

bench-watch-triage-description = which incoming mails match a watch, and which are urgent, per triage algorithm (batch, per-watch) and model
bench-watch-triage-no-header = the dataset must start with {"{"}"dataset": "watch-triage", "version": <number>{"}"}
bench-watch-triage-bad-record = dataset line { $line }: neither a watch (watch, what) nor a mail (case, title)
bench-watch-triage-bad-label = case { $case }: unknown watch or label { $watch } (labels: match, urgent)

bench-watch-triage-matches-f1 = matches, F1
bench-watch-triage-matches-precision = matches, precision
bench-watch-triage-matches-recall = matches, recall
bench-watch-triage-urgent-precision = urgent, precision
bench-watch-triage-urgent-recall = urgent, recall
bench-watch-triage-missed = missed matches
bench-watch-triage-false-alarms = false alarms
bench-watch-triage-unsorted = left unsorted

bench-watch-triage-missed-list = Missed matches
bench-watch-triage-false-alarms-list = False alarms
bench-watch-triage-not-urgent-list = Urgent, announced as not urgent
bench-watch-triage-item = { $case } “{ $title }”, { $watch }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
