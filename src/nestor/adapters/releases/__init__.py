"""Nestor's release feed over HTTP, and installing a release where Nestor runs from Python."""

from nestor.adapters.releases.http_feed import HttpReleaseFeed
from nestor.adapters.releases.pip_installer import PipInstaller

__all__ = ["HttpReleaseFeed", "PipInstaller"]
