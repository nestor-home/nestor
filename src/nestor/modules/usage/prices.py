"""What a call cost: what the provider said, else its units priced by the configuration, else by the public catalogue;
nothing for a model of the household's own; else unknown, never zero."""

from collections.abc import Mapping

from nestor.core import Usage
from nestor.modules.usage.ports import PriceCatalogue
from nestor.modules.usage.types import Consumer, CostBasis, Priced, Rates

REPORTED, LOCAL = "reported", "local"


class PriceBook:
    def __init__(self, configured: Mapping[str, Rates], catalogue: PriceCatalogue | None = None) -> None:
        """`configured`: the prices the configuration sets, by consumer key."""
        self._configured, self._catalogue = dict(configured), catalogue

    def price(self, consumer: Consumer, usage: Usage) -> Priced:
        if usage.cost is not None:
            return Priced(usage.cost, CostBasis.REPORTED, REPORTED)
        if consumer.local:
            return Priced(None, CostBasis.FREE, LOCAL)
        rates = self.rates(consumer, usage.served)
        cost = rates.cost(usage.units) if rates else None
        if rates is None or cost is None:
            return Priced(None, CostBasis.UNKNOWN, None)
        return Priced(cost, CostBasis.FREE if cost.nusd == 0 else CostBasis.PRICED, rates.source)

    def rates(self, consumer: Consumer, served: str | None = None) -> Rates | None:
        """The price a consumer's calls are valued at when its provider says no cost: the configuration's, else the
        catalogue's for the model that answered, else for the one asked."""
        if (configured := self._configured.get(consumer.key)) is not None:
            return configured
        if self._catalogue is None:
            return None
        names = dict.fromkeys(n for n in (served, consumer.model) if n)  # in order, once each
        return next((r for n in names if (r := self._catalogue.rates(consumer.provider, n))), None)
