"""Pairing: a device asks, a household member confirms its code, the device gets a token once.

    device                              core                               household member
      │ request(manifest) ───────────▶ ticket (pairing id, 6-digit code)
      │ shows the code                                                    reads it on the device
      │ poll(id) → pending                                  ◀──────────── approve(code)
      │ poll(id) → approved + token (once)
      │ connects with the token ─────▶ authenticate(device id, token)

Default deny: a device that is not paired, or was revoked, never authenticates. Pending pairings
live in memory (a restart asks devices to request again); paired satellites are rebuilt from the
journal, where only token hashes are written.
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from nestor.core import Capability, Component, ContractError, PersonId, new_id, utc_now
from nestor.modules.journal import Journal
from nestor.modules.satellites.events import SatellitePaired, SatellitePairingRequested, SatelliteRevoked
from nestor.modules.satellites.types import (
    Manifest,
    PairingState,
    PairingStatus,
    PairingTicket,
    PendingPairing,
    Satellite,
)

TOKEN_PREFIX = "nst1_"


class PairingRefused(ContractError):
    """A pairing cannot be accepted: too many waiting, or a code that matches nothing."""


@dataclass(slots=True)
class _Request:
    ticket: PairingTicket
    manifest: Manifest
    status: PairingStatus = PairingStatus.PENDING
    token: str | None = None
    satellite: Satellite | None = None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Pairing(Component):
    name = "satellites"

    def __init__(
        self,
        journal: Journal,
        *,
        code_ttl_s: float = 600.0,
        max_pending: int = 16,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.journal = journal
        self._ttl = timedelta(seconds=code_ttl_s)
        self._max_pending = max_pending
        self._clock = clock
        self._requests: dict[str, _Request] = {}
        self._satellites: dict[str, Satellite] = {}

    async def start(self) -> None:
        """Rebuild the paired satellites: the latest pairing of each device, unless revoked since."""
        history = await self.journal.history(SatellitePaired, SatelliteRevoked)
        for event in history:  # log order
            if isinstance(event, SatellitePaired):
                self._satellites[event.device.id] = _satellite(event)
            else:
                self._satellites.pop(event.device_id, None)

    def satellites(self) -> list[Satellite]:
        return sorted(self._satellites.values(), key=lambda s: s.id)

    def pending(self) -> list[PendingPairing]:
        self._expire()
        return [
            PendingPairing(id=r.ticket.id, device=r.manifest.device, capabilities=r.manifest.names,
                           expires_at=r.ticket.expires_at, sdk=r.manifest.sdk)
            for r in self._requests.values()
            if r.status is PairingStatus.PENDING
        ]  # fmt: skip

    async def request(self, manifest: Manifest) -> PairingTicket:
        """A device asks to pair; asking again replaces its earlier request."""
        self._expire()
        for key, earlier in list(self._requests.items()):
            if earlier.manifest.device.id == manifest.device.id and earlier.status is PairingStatus.PENDING:
                del self._requests[key]
        if sum(r.status is PairingStatus.PENDING for r in self._requests.values()) >= self._max_pending:
            raise PairingRefused("too many pairings are waiting for approval")
        codes = {r.ticket.code for r in self._requests.values()}
        code = next(c for c in iter(lambda: f"{secrets.randbelow(10**6):06d}", None) if c not in codes)
        ticket = PairingTicket(id=new_id(), code=code, expires_at=self._clock() + self._ttl)
        self._requests[ticket.id] = _Request(ticket, manifest)
        await self.journal.publish(
            SatellitePairingRequested(
                source=self.name,
                pairing_id=ticket.id,
                device=manifest.device,
                capabilities=tuple(sorted(manifest.names)),
                expires_at=ticket.expires_at,
            )
        )
        return ticket

    def poll(self, pairing_id: str) -> PairingState:
        """Where a pairing stands; the token comes with the first answer after approval, never again.
        An unknown id reads as expired, so polling reveals nothing."""
        self._expire()
        request = self._requests.get(pairing_id)
        if request is None:
            return PairingState(status=PairingStatus.EXPIRED)
        if request.status is PairingStatus.APPROVED:
            token, request.token, request.status = request.token, None, PairingStatus.CLAIMED
            return PairingState(status=PairingStatus.APPROVED, token=token, satellite=request.satellite)
        return PairingState(status=request.status, satellite=request.satellite)

    async def approve(
        self,
        code: str,
        *,
        by: PersonId | None = None,
        capabilities: Iterable[Capability] | None = None,
        pairing_id: str | None = None,
    ) -> Satellite:
        """Confirm the code a device shows. `capabilities` narrows what it may do (all it declared by
        default); pairing a device again replaces its previous token. With `pairing_id` (the request the
        person typed the code on), a code shown by another device is refused."""
        self._expire()
        request = next(
            (r for r in self._requests.values() if r.status is PairingStatus.PENDING and r.ticket.code == code), None
        )
        if request is not None and pairing_id is not None and request.ticket.id != pairing_id:
            request = None
        if request is None:
            raise PairingRefused("no device is waiting with this code (wrong or expired)")
        allowed = request.manifest.names if capabilities is None else request.manifest.names & set(capabilities)
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        event = SatellitePaired(
            source=self.name,
            pairing_id=request.ticket.id,
            device=request.manifest.device,
            capabilities=tuple(sorted(allowed)),
            token_hash=hash_token(token),
            approved_by=by,
            sdk=request.manifest.sdk.name if request.manifest.sdk else None,
            sdk_version=request.manifest.sdk.version if request.manifest.sdk else None,
        )
        await self.journal.publish(event)
        satellite = self._satellites[event.device.id] = _satellite(event)
        request.status, request.token, request.satellite = PairingStatus.APPROVED, token, satellite
        return satellite

    def authenticate(self, device_id: str, token: str) -> Satellite | None:
        """The satellite this token belongs to; `None` for any unpaired, revoked or replaced token."""
        satellite = self._satellites.get(device_id)
        if satellite is None or not hmac.compare_digest(satellite.token_hash, hash_token(token)):
            return None
        return satellite

    async def revoke(self, device_id: str, *, by: PersonId | None = None) -> None:
        if device_id not in self._satellites:
            raise ContractError(f"no paired satellite {device_id!r}")
        await self.journal.publish(SatelliteRevoked(source=self.name, device_id=device_id, revoked_by=by))
        del self._satellites[device_id]

    def _expire(self) -> None:
        """Past their deadline, pending requests expire and unclaimed tokens are forgotten."""
        now = self._clock()
        for key, request in list(self._requests.items()):
            if request.ticket.expires_at <= now:
                if request.status is PairingStatus.EXPIRED:
                    del self._requests[key]  # reported once, then forgotten
                else:
                    request.status, request.token = PairingStatus.EXPIRED, None


def _satellite(event: SatellitePaired) -> Satellite:
    return Satellite(
        id=event.device.id,
        model=event.device.model,
        room=event.device.room,
        capabilities=frozenset(event.capabilities),
        token_hash=event.token_hash,
        paired_at=event.at,
        brand=event.device.brand,
        sdk=event.sdk,
        sdk_version=event.sdk_version,
    )
