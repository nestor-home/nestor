"""Usage: what Nestor's calls to models consume and cost, on whose behalf and why.

Every model of `models` counts its calls (`metered`); what an adapter reports (`nestor.core.report`) is priced by the
`PriceBook` (the provider's word, the configuration's price, the public catalogue, nothing for a local model) and
attributed by what the work said of itself (`attributed`). Each call is a `usage.recorded` in the journal; the ledger
(`UsageStore`, kept and read by `Ledger`) is a projection of them, read by the admin and the CLI over a `Period` of
the household's clock.
"""

from nestor.modules.usage.attribution import attribute, attributed, attribution
from nestor.modules.usage.events import UsageRecorded
from nestor.modules.usage.ledger import Ledger, Summary
from nestor.modules.usage.meter import Meter
from nestor.modules.usage.metered import Counted, metered
from nestor.modules.usage.ports import Line, PriceCatalogue, UsageStore
from nestor.modules.usage.prices import PriceBook
from nestor.modules.usage.types import (
    PRICED_PER,
    ZERO,
    Attribution,
    Beat,
    CallPurpose,
    Consumer,
    CostBasis,
    Dimension,
    Group,
    Interval,
    Outcome,
    Period,
    Point,
    Priced,
    Rates,
    Span,
    Totals,
    UsageFilter,
    shown,
)

__all__ = [
    "PRICED_PER",
    "ZERO",
    "Attribution",
    "Beat",
    "CallPurpose",
    "Consumer",
    "CostBasis",
    "Counted",
    "Dimension",
    "Group",
    "Interval",
    "Ledger",
    "Line",
    "Meter",
    "Outcome",
    "Period",
    "Point",
    "PriceBook",
    "PriceCatalogue",
    "Priced",
    "Rates",
    "Span",
    "Summary",
    "Totals",
    "UsageFilter",
    "UsageRecorded",
    "UsageStore",
    "attribute",
    "attributed",
    "attribution",
    "metered",
    "shown",
]
