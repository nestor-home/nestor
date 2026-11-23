"""Usage: what Nestor's calls to models and executors consume and cost, on whose behalf and why.

Every model of `models` counts its calls (`metered`); what an adapter reports (`nestor.core.report`) is priced by the
`PriceBook` (the provider's word, the configuration's price, the public catalogue, nothing for a local model) and
attributed by what the work said of itself (`attributed`). Each call is a `usage.recorded` in the journal; the ledger
(`UsageStore`, kept by `Ledger`) is a projection of them, which `Spending` reads for the admin and the CLI.
"""

from nestor.modules.usage.attribution import attribute, attributed, attribution
from nestor.modules.usage.events import UsageRecorded
from nestor.modules.usage.ledger import Ledger, Summary
from nestor.modules.usage.meter import Call, Meter
from nestor.modules.usage.metered import Counted, metered
from nestor.modules.usage.ports import PriceCatalogue, UsageStore
from nestor.modules.usage.prices import PriceBook
from nestor.modules.usage.types import (
    PRICED_PER,
    Attribution,
    CallPurpose,
    Consumer,
    ConsumerKind,
    CostBasis,
    Dimension,
    Group,
    Interval,
    Line,
    Outcome,
    Point,
    Priced,
    Rates,
    Totals,
    UsageFilter,
    shown,
)

__all__ = [
    "PRICED_PER",
    "Attribution",
    "Call",
    "CallPurpose",
    "Consumer",
    "ConsumerKind",
    "CostBasis",
    "Counted",
    "Dimension",
    "Group",
    "Interval",
    "Ledger",
    "Line",
    "Meter",
    "Outcome",
    "Point",
    "PriceBook",
    "PriceCatalogue",
    "Priced",
    "Rates",
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
