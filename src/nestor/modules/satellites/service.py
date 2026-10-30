"""Pairing (`nestor.satellite/2`): a device gets a token once a person proved they meant to pair it.

The proof travels whichever way the device can carry it, and the person picks the method:

    device                                core                               household member
      │ request(manifest) ─────────────▶ ticket: pending, device code
      │ shows / says the device code                          ◀───────── approve(device code)
      │                         or
      │ enroll(id, enrollment code) ───▶ approved                          (code made in the admin)
      │ poll(id) → approved + token (once)
      │ connects with the token ───────▶ authenticate(device id, token)

A device configured with an enrollment code sends it with its request and is approved at once. A
pending device accepts both proofs: the first one accepted wins, the other is refused and an
enrollment code refused that way stays usable. A person may ask a pending device to identify itself
through its next poll, or a paired one through its link: that only helps tell devices apart.

Default deny: a device that is not paired, was revoked, or paired with an older protocol never
authenticates. Pending pairings live in memory (a restart asks devices to request again); paired
satellites and the additions in progress are rebuilt from the journal, where only hashes are written.
"""

import contextlib
import hmac
import secrets
from collections import deque
from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from nestor.core import Capability, Component, ContractError, PersonId, new_id, utc_now
from nestor.modules.journal import Journal
from nestor.modules.satellites.codes import hash_code, new_device_code, new_enrollment_code, normalize_enrollment_code
from nestor.modules.satellites.events import (
    SatelliteAdditionCancelled,
    SatelliteAdditionCompleted,
    SatelliteAdditionExpired,
    SatelliteAdditionStarted,
    SatelliteEnrollmentRefused,
    SatelliteIdentifyRequested,
    SatellitePaired,
    SatellitePairingRequested,
    SatelliteRevoked,
)
from nestor.modules.satellites.types import (
    IDENTIFY,
    MAX_NAME,
    PROTOCOL,
    Addition,
    AdditionStatus,
    Device,
    Manifest,
    PairingMethod,
    PairingState,
    PairingStatus,
    PairingTicket,
    PendingPairing,
    Proof,
    Satellite,
    StartedAddition,
    check_room,
)

TOKEN_PREFIX = "nst2_"
MIN_ADDITION_TTL_S = 60.0
MAX_ADDITION_TTL_S = 7 * 24 * 3600.0
_REFUSALS = {AdditionStatus.COMPLETED: "used", AdditionStatus.EXPIRED: "expired", AdditionStatus.CANCELLED: "cancelled"}

type Identify = Callable[[], None]


class PairingRefused(ContractError):
    """A pairing step cannot be accepted. `reason` says why, for programs."""

    reason = "refused"

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason or type(self).reason


class TooManyPending(PairingRefused):
    reason = "too_many_pending"


class NotPending(PairingRefused):
    """The pairing is no longer waiting for a proof: approved by the other one, expired or unknown."""

    reason = "not_pending"


class EnrollmentRefused(PairingRefused):
    """The enrollment code pairs nothing: `reason` is unknown, expired, used or cancelled."""

    reason = "unknown"


class TooManyAttempts(PairingRefused):
    reason = "too_many_attempts"

    def __init__(self, retry_after_s: float) -> None:
        super().__init__(f"too many wrong enrollment codes: try again in {retry_after_s:.0f} s")
        self.retry_after_s = retry_after_s


class IdentifyUnavailable(ContractError):
    """The device cannot be asked to identify itself: `reason` is unknown, unsupported or offline."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(slots=True)
class AttemptLimiter:
    """Wrong enrollment codes allowed per window: `per_source` from one address, `overall` from all of
    them. Past either, every attempt is refused until the window frees a slot."""

    per_source: int = 5
    overall: int = 20
    window_s: float = 60.0
    _failures: deque[tuple[datetime, str]] = field(default_factory=deque)

    def check(self, source: str, now: datetime) -> None:
        horizon = now - timedelta(seconds=self.window_s)
        while self._failures and self._failures[0][0] <= horizon:
            self._failures.popleft()
        mine = [at for at, who in self._failures if who == source]
        if len(mine) >= self.per_source:
            raise TooManyAttempts(self._wait(mine[0], now))
        if len(self._failures) >= self.overall:
            raise TooManyAttempts(self._wait(self._failures[0][0], now))

    def failed(self, source: str, now: datetime) -> None:
        self._failures.append((now, source))

    def _wait(self, oldest: datetime, now: datetime) -> float:
        return max(1.0, self.window_s - (now - oldest).total_seconds())


@dataclass(slots=True)
class _Request:
    ticket: PairingTicket
    manifest: Manifest
    status: PairingStatus = PairingStatus.PENDING
    token: str | None = None
    satellite: Satellite | None = None
    identify: bool = False


def hash_token(token: str) -> str:
    return hash_code(token)


class Pairing(Component):
    name = "satellites"

    def __init__(
        self,
        journal: Journal,
        *,
        device_code_ttl_s: float = 600.0,
        addition_ttl_s: float = 900.0,
        max_pending: int = 16,
        max_additions: int = 32,
        limiter: AttemptLimiter | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.journal = journal
        self._ttl = timedelta(seconds=device_code_ttl_s)
        self.addition_ttl_s = addition_ttl_s
        self._max_pending = max_pending
        self._max_additions = max_additions
        self._limiter = limiter or AttemptLimiter()
        self._clock = clock
        self._requests: dict[str, _Request] = {}
        self._satellites: dict[str, Satellite] = {}
        self._additions: dict[str, Addition] = {}
        self._online: dict[str, Identify] = {}

    async def start(self) -> None:
        """Rebuild the paired satellites (the latest pairing of each device made with this protocol,
        unless revoked since) and the additions in progress."""
        history = await self.journal.history(
            SatellitePaired,
            SatelliteRevoked,
            SatelliteAdditionStarted,
            SatelliteAdditionCompleted,
            SatelliteAdditionExpired,
            SatelliteAdditionCancelled,
        )
        for event in history:  # log order
            match event:
                case SatellitePaired() if event.protocol == PROTOCOL:
                    self._satellites[event.device.id] = _satellite(event)
                case SatellitePaired() | SatelliteRevoked():
                    self._satellites.pop(event.device.id if isinstance(event, SatellitePaired) else event.device_id,
                                         None)  # fmt: skip
                case SatelliteAdditionStarted():
                    self._additions[event.addition_id] = _addition(event)
                case SatelliteAdditionCompleted():
                    self._finish(event.addition_id, AdditionStatus.COMPLETED, device_id=event.device_id)
                case SatelliteAdditionExpired():
                    self._finish(event.addition_id, AdditionStatus.EXPIRED)
                case SatelliteAdditionCancelled():
                    self._finish(event.addition_id, AdditionStatus.CANCELLED)

    def satellites(self) -> list[Satellite]:
        return sorted(self._satellites.values(), key=lambda s: s.id)

    def pending(self) -> list[PendingPairing]:
        self._expire()
        return [
            PendingPairing(id=r.ticket.id, device=r.manifest.device, capabilities=r.manifest.names,
                           methods=r.manifest.pairing_methods, expires_at=r.ticket.expires_at, sdk=r.manifest.sdk)
            for r in self._requests.values()
            if r.status is PairingStatus.PENDING
        ]  # fmt: skip

    # The device's side.

    async def request(
        self,
        manifest: Manifest,
        *,
        enrollment_code: str | None = None,
        method: PairingMethod | None = None,
        source: str = "unknown",
    ) -> PairingTicket:
        """A device asks to pair; asking again replaces its earlier pending request. With an enrollment
        code (received through `method`), it is approved at once; otherwise it gets a device code to
        present, and stays pending until a proof arrives."""
        self._expire()
        waiting = [r for r in self._requests.values() if r.status is PairingStatus.PENDING]
        if enrollment_code is None and len(waiting) >= self._max_pending:
            raise TooManyPending("too many pairings are waiting for approval")
        addition = await self._redeem(enrollment_code, manifest, method, source) if enrollment_code else None
        for key, earlier in list(self._requests.items()):
            if earlier.manifest.device.id == manifest.device.id and earlier.status is PairingStatus.PENDING:
                del self._requests[key]
        codes = {r.ticket.device_code for r in self._requests.values()}
        code = next(c for c in iter(new_device_code, None) if c not in codes)
        ticket = PairingTicket(
            id=new_id(), status=PairingStatus.PENDING, device_code=code, expires_at=self._clock() + self._ttl
        )
        request = self._requests[ticket.id] = _Request(ticket, manifest)
        if addition is not None:
            request.status = PairingStatus.APPROVED  # its proof is in: no device code may approve it
        await self.journal.publish(
            SatellitePairingRequested(
                source=self.name,
                pairing_id=ticket.id,
                device=manifest.device,
                capabilities=tuple(sorted(manifest.names)),
                expires_at=ticket.expires_at,
                methods=manifest.pairing_methods,
            )
        )
        if addition is None:
            return ticket
        await self._approve_enrolled(request, addition, method)
        return replace(ticket, status=PairingStatus.APPROVED, device_code=None)

    async def enroll(
        self, pairing_id: str, enrollment_code: str, *, method: PairingMethod, source: str = "unknown"
    ) -> PairingState:
        """The proof of a pending device, received after it asked (typed, scanned or configured late).
        Refused without spending the code when the pairing is no longer pending: the device code won."""
        self._expire()
        self._limiter.check(source, self._clock())
        request = self._requests.get(pairing_id)
        if request is None or request.status is not PairingStatus.PENDING:
            raise NotPending("this pairing is no longer waiting for a proof")
        addition = await self._redeem(enrollment_code, request.manifest, method, source, pending=request)
        await self._approve_enrolled(request, addition, method)
        return PairingState(status=PairingStatus.APPROVED, satellite=request.satellite)

    def poll(self, pairing_id: str) -> PairingState:
        """Where a pairing stands; the token comes with the first answer after approval, never again.
        An unknown id reads as expired, so polling reveals nothing."""
        self._expire()
        request = self._requests.get(pairing_id)
        if request is None:
            return PairingState(status=PairingStatus.EXPIRED)
        identify, request.identify = request.identify, False
        if request.status is PairingStatus.APPROVED:
            token, request.token, request.status = request.token, None, PairingStatus.CLAIMED
            return PairingState(status=PairingStatus.APPROVED, token=token, satellite=request.satellite)
        return PairingState(status=request.status, satellite=request.satellite, identify=identify)

    # The household's side.

    async def approve(
        self,
        code: str,
        *,
        by: PersonId | None = None,
        capabilities: Iterable[Capability] | None = None,
        pairing_id: str | None = None,
        method: PairingMethod | None = None,
        addition_id: str | None = None,
    ) -> Satellite:
        """Confirm the device code a device presents. `capabilities` narrows what it may do (all it
        declared by default); `method` says how the person got the code. With `pairing_id` (the request
        the person typed the code on), a code presented by another device is refused. With
        `addition_id`, the addition the person started gives its method, name, room and capabilities."""
        await self._expire_additions()  # the last await before the claim: two approvals cannot interleave past it
        self._expire()
        addition = None
        if addition_id is not None:
            addition = self._additions.get(addition_id)
            if addition is None or addition.status is not AdditionStatus.ACTIVE:
                raise _addition_over()
            method = addition.method
        if method is not None and method.proof is not Proof.DEVICE_CODE:
            raise ContractError(f"{method} does not pair with a device code")
        request = next(
            (r for r in self._requests.values() if r.status is PairingStatus.PENDING and r.ticket.device_code == code),
            None,
        )
        if request is not None and pairing_id is not None and request.ticket.id != pairing_id:
            request = None
        if request is None:
            raise PairingRefused("no device is waiting with this code (wrong or expired)", reason="wrong_code")
        allowed = request.manifest.names if capabilities is None else request.manifest.names & set(capabilities)
        if addition is not None:
            addition = self._claim(addition, request.manifest.device.id)
            if addition.capabilities is not None:
                allowed = allowed & addition.capabilities
        request.status = PairingStatus.APPROVED  # taken now: an enrollment code sent meanwhile is refused
        return await self._pair(request, allowed, Proof.DEVICE_CODE, method, by=by, addition=addition)

    async def start_addition(
        self,
        method: PairingMethod,
        *,
        by: PersonId | None = None,
        name: str | None = None,
        room: str | None = None,
        capabilities: Iterable[Capability] | None = None,
        ttl_s: float | None = None,
    ) -> StartedAddition:
        """A person starts adding a satellite. An enrollment method makes a single-use code, returned
        in clear this once; a device code method waits for the code a device presents."""
        await self._expire_additions()
        ttl = self.addition_ttl_s if ttl_s is None else ttl_s
        if not MIN_ADDITION_TTL_S <= ttl <= MAX_ADDITION_TTL_S:
            raise ContractError(f"an addition lasts {MIN_ADDITION_TTL_S:.0f} s to {MAX_ADDITION_TTL_S:.0f} s")
        if name is not None and not 0 < len(name) <= MAX_NAME:
            raise ContractError(f"a name is 1 to {MAX_NAME} characters")
        if len(self.additions()) >= self._max_additions:
            raise PairingRefused("too many additions are in progress: cancel one", reason="too_many_additions")
        code = None
        if method.proof is Proof.ENROLLMENT_CODE:
            hashes = {a.code_hash for a in self._additions.values()}
            code = next(c for c in iter(new_enrollment_code, None) if hash_code(c) not in hashes)
        event = SatelliteAdditionStarted(
            source=self.name,
            addition_id=new_id(),
            method=method,
            expires_at=self._clock() + timedelta(seconds=ttl),
            code_hash=hash_code(code) if code is not None else None,
            name=name,
            room=check_room(room) if room is not None else None,
            capabilities=tuple(sorted(set(capabilities))) if capabilities is not None else None,
            created_by=by,
        )
        await self.journal.publish(event)
        addition = self._additions[event.addition_id] = _addition(event)
        return StartedAddition(addition=addition, code=code)

    def additions(self) -> list[Addition]:
        """The additions still in progress, the soonest to expire first."""
        now = self._clock()
        active = [a for a in self._additions.values() if a.status is AdditionStatus.ACTIVE and a.expires_at > now]
        return sorted(active, key=lambda a: a.expires_at)

    async def addition(self, addition_id: str) -> Addition | None:
        """One addition, in progress or over (its expiry journaled first if it just ran out)."""
        await self._expire_additions()
        return self._additions.get(addition_id)

    async def expire_additions(self) -> list[Addition]:
        """Journal the additions that ran out since last asked; returns those in progress."""
        await self._expire_additions()
        return self.additions()

    async def cancel_addition(self, addition_id: str, *, by: PersonId | None = None) -> None:
        await self._expire_additions()
        addition = self._additions.get(addition_id)
        if addition is None or addition.status is not AdditionStatus.ACTIVE:
            raise ContractError(f"no addition {addition_id!r} in progress")
        self._finish(addition_id, AdditionStatus.CANCELLED)
        await self.journal.publish(SatelliteAdditionCancelled(source=self.name, addition_id=addition_id,
                                                              cancelled_by=by))  # fmt: skip

    async def identify_pending(self, pairing_id: str, *, by: PersonId | None = None) -> None:
        """Ask a pending device to make itself noticed; it hears it at its next poll."""
        self._expire()
        request = self._requests.get(pairing_id)
        if request is None or request.status is not PairingStatus.PENDING:
            raise IdentifyUnavailable("no device is waiting with this pairing", reason="unknown")
        if IDENTIFY not in request.manifest.names:
            raise IdentifyUnavailable("this device cannot identify itself", reason="unsupported")
        request.identify = True
        await self.journal.publish(SatelliteIdentifyRequested(source=self.name, device_id=request.manifest.device.id,
                                                              pairing_id=pairing_id, requested_by=by))  # fmt: skip

    async def identify(self, device_id: str, *, by: PersonId | None = None) -> None:
        """Ask a paired, connected device to make itself noticed, if it was allowed to."""
        satellite = self._satellites.get(device_id)
        if satellite is None:
            raise IdentifyUnavailable(f"no paired satellite {device_id!r}", reason="unknown")
        if IDENTIFY not in satellite.capabilities:
            raise IdentifyUnavailable("this satellite cannot identify itself", reason="unsupported")
        send = self._online.get(device_id)
        if send is None:
            raise IdentifyUnavailable("this satellite is not connected", reason="offline")
        send()
        await self.journal.publish(SatelliteIdentifyRequested(source=self.name, device_id=device_id,
                                                              requested_by=by))  # fmt: skip

    @contextlib.contextmanager
    def online(self, device_id: str, identify: Identify) -> Generator[None]:
        """While a host holds a paired device's link: how to ask it to identify itself."""
        self._online[device_id] = identify
        try:
            yield
        finally:
            if self._online.get(device_id) is identify:
                del self._online[device_id]

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

    # Inside.

    async def _redeem(
        self,
        text: str,
        manifest: Manifest,
        method: PairingMethod | None,
        source: str,
        *,
        pending: _Request | None = None,
    ) -> Addition:
        """The addition in progress this enrollment code belongs to, spent at once; a wrong code counts
        against `source`. Every known hash is compared, in constant time. From the check of `pending`
        to the code being spent nothing awaits, so a device code typed meanwhile cannot win too."""
        if method is None or method.proof is not Proof.ENROLLMENT_CODE or method not in manifest.pairing_methods:
            raise ContractError("an enrollment code comes with the enrollment method, among those the device declares")
        now = self._clock()
        self._limiter.check(source, now)
        await self._expire_additions()
        code = normalize_enrollment_code(text)
        presented = hash_code(code) if code is not None else ""
        found = None
        for addition in self._additions.values():
            if addition.code_hash is not None and hmac.compare_digest(addition.code_hash, presented):
                found = addition
        if pending is not None and pending.status is not PairingStatus.PENDING:
            raise NotPending("this pairing is no longer waiting for a proof")
        if found is not None and found.status is AdditionStatus.ACTIVE:
            return self._claim(found, manifest.device.id)
        self._limiter.failed(source, now)
        reason = _REFUSALS[found.status] if found is not None else "unknown"
        await self.journal.publish(
            SatelliteEnrollmentRefused(source=self.name, device_id=manifest.device.id, reason=reason,
                                       addition_id=found.id if found else None, address=source)
        )  # fmt: skip
        raise EnrollmentRefused("this enrollment code pairs nothing", reason=reason)

    async def _approve_enrolled(self, request: _Request, addition: Addition, method: PairingMethod | None) -> None:
        request.status = PairingStatus.APPROVED  # taken now: a device code typed meanwhile is refused
        names = request.manifest.names
        allowed = names if addition.capabilities is None else names & addition.capabilities
        await self._pair(request, allowed, Proof.ENROLLMENT_CODE, method, by=addition.created_by, addition=addition)

    async def _pair(
        self,
        request: _Request,
        allowed: frozenset[Capability] | set[Capability],
        proof: Proof,
        method: PairingMethod | None,
        *,
        by: PersonId | None,
        addition: Addition | None = None,
    ) -> Satellite:
        device = request.manifest.device
        if addition is not None and addition.room is not None:
            device = Device(device.id, device.model, addition.room, device.brand)
        if addition is not None:  # claimed by the caller, before anything awaited
            completed = SatelliteAdditionCompleted(
                source=self.name, addition_id=addition.id, pairing_id=request.ticket.id, device_id=device.id
            )
            await self.journal.publish(completed)
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        sdk = request.manifest.sdk
        event = SatellitePaired(
            source=self.name,
            pairing_id=request.ticket.id,
            device=device,
            capabilities=tuple(sorted(allowed)),
            token_hash=hash_token(token),
            protocol=PROTOCOL,
            proof=proof,
            method=method,
            addition_id=addition.id if addition else None,
            name=addition.name if addition else None,
            approved_by=by,
            sdk=sdk.name if sdk else None,
            sdk_version=sdk.version if sdk else None,
        )
        await self.journal.publish(event)
        satellite = self._satellites[device.id] = _satellite(event)
        request.token, request.satellite = token, satellite
        return satellite

    def _claim(self, addition: Addition, device_id: str) -> Addition:
        """Take an addition in progress for one device: the only way one completes, checked and marked
        in a single step that never awaits. Of two proofs racing for it, exactly one gets it; the other
        is told it is over, and nothing of it reaches the journal."""
        current = self._additions.get(addition.id)
        if current is None or current.status is not AdditionStatus.ACTIVE:
            raise _addition_over()
        self._additions[addition.id] = replace(current, status=AdditionStatus.COMPLETED, device_id=device_id)
        return current

    def _finish(self, addition_id: str, status: AdditionStatus, *, device_id: str | None = None) -> None:
        if addition := self._additions.get(addition_id):
            self._additions[addition_id] = replace(addition, status=status, device_id=device_id)

    async def _expire_additions(self) -> None:
        now = self._clock()
        for addition in list(self._additions.values()):
            if addition.status is AdditionStatus.ACTIVE and addition.expires_at <= now:
                self._finish(addition.id, AdditionStatus.EXPIRED)
                await self.journal.publish(SatelliteAdditionExpired(source=self.name, addition_id=addition.id))

    def _expire(self) -> None:
        """Past their deadline, pending requests expire and unclaimed tokens are forgotten."""
        now = self._clock()
        for key, request in list(self._requests.items()):
            if request.ticket.expires_at <= now:
                if request.status is PairingStatus.EXPIRED:
                    del self._requests[key]  # reported once, then forgotten
                else:
                    request.status, request.token = PairingStatus.EXPIRED, None


def _addition_over() -> PairingRefused:
    return PairingRefused("this addition is over (paired, cancelled or expired)", reason="addition_over")


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
        name=event.name,
    )


def _addition(event: SatelliteAdditionStarted) -> Addition:
    return Addition(
        id=event.addition_id,
        method=event.method,
        created_at=event.at,
        expires_at=event.expires_at,
        code_hash=event.code_hash,
        name=event.name,
        room=event.room,
        capabilities=frozenset(event.capabilities) if event.capabilities is not None else None,
        created_by=event.created_by,
    )
