# The routing bench suite: does the agent hand a request to the right executor, use its own tool, or answer by itself.

bench-routing-description = whether the agent hands a request to the right executor, uses the right tool of its own, or answers by itself, per model
bench-routing-no-header = the dataset must start with {"{"}"dataset": "routing", "version": <number>{"}"}
bench-routing-bad-record = dataset line { $line }: a case needs case, said and expected (a list of tiers of routes: tool:<name>, delegate:<executor> or none)

bench-routing-accuracy = right routes
bench-routing-missed = not handed over when it should have been
bench-routing-needless = handed over when it should not have been
bench-routing-wrong-executor = handed to the wrong executor
bench-routing-failed = failed turns

bench-routing-missed-list = Not handed over
bench-routing-needless-list = Handed over needlessly
bench-routing-wrong-executor-list = Handed to the wrong executor
bench-routing-other-list = Another tool, or none where one was right
bench-routing-item = { $case } “{ $said }” → { $route }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
