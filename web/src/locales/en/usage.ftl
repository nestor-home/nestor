## Costs: what the calls to models cost, at a glance and down to the call.

usage-title = Costs
usage-glance = The period at a glance
usage-range = Period
usage-range-today = Today
usage-range-7d = 7 days
usage-range-30d = 30 days
usage-range-month = This month
usage-range-90d = 90 days
usage-split = Split by
usage-filter-remove = Remove the filter { $value }
usage-filter-clear = Clear all

usage-spent-today = Spent today
usage-spent-7d = Spent over 7 days
usage-spent-30d = Spent over 30 days
usage-spent-month = Spent this month
usage-spent-90d = Spent over 90 days
usage-vs-before = vs { $spent } the period before
usage-no-before = Nothing spent the period before
usage-month-end = End of month
usage-month-so-far = { $spent } so far
usage-per-conversation = Per conversation
usage-conversations = { $count ->
    [one] { $count } conversation
   *[other] { $count } conversations
}
usage-calls = Calls
usage-calls-count = { $count ->
    [one] { $count } call
   *[other] { $count } calls
}
usage-unknown-calls = { $count ->
    [one] { $count } of unknown cost
   *[other] { $count } of unknown cost
}
usage-all-known = Every cost known
usage-cache = Read from cache
usage-input-tokens = of { $tokens } input tokens

usage-over-time = Over time
usage-other = { $count ->
    [one] 1 other
   *[other] { $count } others
}
usage-who = Who
usage-models = Models
usage-what = What for
usage-when = When
usage-channels = Channels
usage-more = { $count } more
usage-less = Fewer
usage-empty = No call over this period.
usage-own-work = { $assistant } on its own
usage-no-channel = In the background

usage-sources = Where the figures come from
usage-show-them = Show them

usage-prices = Prices
usage-price-missing = No price known: set one in the model's configuration
usage-source-reported = Billed by the provider, call by call
usage-source-local = Free, on the house's own machine
usage-source-config = Your price, from the configuration
usage-source-catalogue = Public price list of { $date }
usage-rate-input_tokens = { $price } / M input
usage-rate-cached_input_tokens = { $price } / M cached
usage-rate-cache_write_tokens = { $price } / M cache writes
usage-rate-output_tokens = { $price } / M output
usage-rate-characters = { $price } / M characters
usage-rate-audio_seconds = { $price } / min heard
usage-rate-images = { $price } / picture
usage-rate-requests = { $price } / call

usage-calls-title = Calls
usage-calls-more = Show more
usage-call-kind = Call to { $consumer }
usage-call-cost = Cost
usage-call-journal = Open in the journal
usage-call-who = For
usage-call-where = Where
usage-medium-spoken = spoken
usage-medium-written = written
usage-call-model = Model
usage-call-provider = Provider
usage-call-outcome = Outcome
usage-call-origin = Started by
usage-call-units = Consumed
