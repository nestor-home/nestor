# The memory-recall bench suite: do the memories a turn needs reach its instructions.

bench-memory-recall-description = which memories reach a turn's instructions, and how many useless ones with them, per retrieval strategy
bench-memory-recall-no-header = the dataset must start with {"{"}"dataset": "memory-recall", "version": <number>{"}"}
bench-memory-recall-bad-record = line { $line } of the dataset: neither a memory (memory, text), an episode (episode, summary) nor a case (case, said, kind: direct, paraphrase, contradiction, premise, other-person, episode, private or none)
bench-memory-recall-unknown = case { $case }: unknown memory { $memory }

bench-memory-recall-recall = recall
bench-memory-recall-recall-direct = recall, shared words
bench-memory-recall-recall-paraphrase = recall, paraphrases
bench-memory-recall-recall-contradiction = recall, a memory overriding another
bench-memory-recall-recall-premise = recall, what is said contradicts a memory
bench-memory-recall-recall-other-person = recall, the same subject about someone else
bench-memory-recall-recall-episode = recall, a past conversation of whoever speaks
bench-memory-recall-complete = turns that get all their memories
bench-memory-recall-injected-per-case = memories injected per turn
bench-memory-recall-stale-injected = stale memories injected, per contradiction
bench-memory-recall-misleading-injected = someone else's memories injected, per case
bench-memory-recall-others-conversations-injected = someone else's conversations injected (must stay at 0)
bench-memory-recall-noise-when-nothing-matters = memories injected when none matters

bench-memory-recall-missed-list = Memories missed
bench-memory-recall-item = { $case } “{ $said }”: { $memory }{ $of ->
    [1] {""}
   *[other] {" "}({ $times }/{ $of })
}
