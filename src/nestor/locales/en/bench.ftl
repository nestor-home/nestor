# Benchmarks (`nestor bench`): the command, its errors, the tables and the HTML report.

## The command.

bench-help = measure parts of Nestor on a dataset and compare configurations
bench-list-help = the installed suites
bench-run-help = run a suite against one or more variants
bench-run-description = Run every case of a suite against every variant, at every repetition. A variant is a fragment of nestor.yaml (the model under test…) with the suite's knobs under `bench:`. Each model call is measured and recorded in the cache, so --replay can score the run again without calling a provider.
bench-suite-help = the suite to run (see `nestor bench list`)
bench-variant-help = a variant file; repeat the option to compare several
bench-repeat-help = how many times to run each case (default: 1)
bench-cases-help = a dataset of your own, in the suite's JSONL format (default: the suite's)
bench-replay-help = answer from the recorded replies only: no provider is called
bench-seed-help = the seed of the cases' order and of the cache keys (default: 0)
bench-concurrency-help = cases in flight at once (default: 4; 1 for the steadiest latencies)
bench-results-help = where runs are written (default: bench-results)
bench-cache-help = where model replies are recorded (default: .bench-cache)
bench-compare-help = compare runs side by side, in the terminal and as an HTML page
bench-runs-help = a run's folder, or its results.json
bench-out-help = the HTML page to write (default: next to the first run)
bench-report-help = one run's table and findings, and its HTML report written again

bench-list-line = { $suite }: { $description }
bench-running = { $suite }: { $cases } cases × { $variants ->
    [one] 1 variant
   *[other] { $variants } variants
} × { $repeat ->
    [one] 1 repetition
   *[other] { $repeat } repetitions
}{ $replayed ->
    [yes] , replayed from the cache
   *[no] {""}
}
bench-wrote = wrote { $path }
bench-failed = nestor bench: { $reason }

## Errors.

bench-unknown-suite = no suite named { $suite } (installed: { $known })
bench-dataset-unreadable = cannot read the dataset { $path }
bench-dataset-invalid-line = { $path }, line { $line }: not a JSON object
bench-variant-unreadable = { $path } is not a YAML mapping (a fragment of nestor.yaml)
bench-variant-invalid = { $path }, section bench: { $problems }
bench-variant-not-a-model = { $path }: { $kind } does not build a conversation model
bench-no-recording = no recorded reply for case { $case } ({ $role }): run it once without --replay
bench-cache-unreadable = the cache file { $path } is damaged: delete it
bench-results-unreadable = { $path } is not a bench run (no readable results.json)
bench-same-variant-name = two variants have the same name ({ $names }): set bench.name in one of them

## Tables and report.

bench-table-header = { $suite } · dataset { $dataset } (v{ $version }, { $cases } cases) · { $repeat ->
    [one] 1 repetition
   *[other] { $repeat } repetitions
} · seed { $seed }
bench-column-metric = metric
bench-table-best = { $mark } best of the row
bench-different-datasets = warning: these runs did not use the same dataset
bench-table-run = { $variant }: answered by { $served }{ $replayed ->
    [yes] , replayed
   *[no] {""}
}
bench-report-title = Bench report
bench-report-metrics = Metrics
bench-report-best = The best value of each row is highlighted.
bench-report-charts = Charts
bench-report-runs = Runs
bench-report-findings = Cases to read
bench-report-no-findings = Nothing to read: no case went wrong.
bench-report-replayed = replayed
bench-column-variant = variant
bench-column-served = answered by
bench-column-config = configuration
bench-column-dataset = dataset
bench-column-repeat = repetitions / seed
bench-column-version = Nestor
bench-column-started = started

## Metrics every run has.

bench-metric-calls-per-case = model calls per case
bench-metric-case-latency-p50 = case latency, median
bench-metric-case-latency-p95 = case latency, p95
bench-metric-call-latency-p50 = call latency, median
bench-metric-call-latency-p95 = call latency, p95
bench-metric-input-tokens-per-case = input tokens per case
bench-metric-output-tokens-per-case = output tokens per case
bench-metric-cost-per-1000-cases = cost per 1000 cases
bench-metric-provider-errors = provider errors
