"""What a call cost: what the provider said, else its units priced by the configuration, else by the public catalogue;
nothing for a model of the household's own; else unknown, never zero."""

from collections.abc import Mapping

from nestor.core import Usage
from nestor.modules.usage.ports import PriceCatalogue
from nestor.modules.usage.types import ZERO, Consumer, CostBasis, Priced, Rates


class PriceBook:
    def __init__(self, configured: Mapping[str, Rates], catalogue: PriceCatalogue | None = None) -> None:
        """`configured`: the prices the configuration sets, by consumer key."""
        self._configured, self._catalogue = dict(configured), catalogue

    @property
    def catalogue(self) -> bool:
        """Whether the public price list is read."""
        return self._catalogue is not None

    def price(self, consumer: Consumer, usage: Usage) -> Priced:
        """What a call cost, `usage.served` being the model that answered."""
        if usage.cost is not None:
            return Priced(usage.cost, CostBasis.REPORTED)
        if not usage.units:
            return Priced(ZERO, CostBasis.NOTHING)
        if consumer.local:
            return Priced(ZERO, CostBasis.FREE)
        rates = self.rates(consumer, usage.served)
        cost = rates.cost(usage.units) if rates else None
        if rates is None or cost is None:
            return Priced(None, CostBasis.UNKNOWN)
        return Priced(cost, CostBasis.FREE if cost == ZERO else CostBasis.PRICED, rates.source)

    def rates(self, consumer: Consumer, served: str | None = None) -> Rates | None:
        """The price a consumer's calls are valued at when its provider says no cost: none for a model of the
        household's own, the configuration's, else the catalogue's for the model that answered, else for the one
        asked."""
        if consumer.local:
            return None
        if (configured := self._configured.get(consumer.key)) is not None:
            return configured
        if self._catalogue is None:
            return None
        names = dict.fromkeys(n for n in (served, consumer.model) if n)  # in order, once each
        return next((r for n in names if (r := self._catalogue.rates(consumer.provider, n))), None)
