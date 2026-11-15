"""Routing: whether the agent hands a request to the right executor, uses its own tool, or answers by itself."""

from nestor.bench.suites.routing.suite import Routing

suite = Routing()

__all__ = ["Routing", "suite"]
