from datetime import datetime, timedelta

import pytest

from nestor.core import Capability, ContractError, PersonId, utc_now
from nestor.modules.journal import Journal, LogQuery
from nestor.modules.satellites import (
    IDENTIFY,
    AttemptLimiter,
    Device,
    EnrollmentRefused,
    IdentifyUnavailable,
    Manifest,
    NotPending,
    Pairing,
    PairingMethod,
    PairingRefused,
    PairingStatus,
    Proof,
    SatelliteAdditionCompleted,
    SatelliteAdditionExpired,
    SatelliteEnrollmentRefused,
    SatelliteIdentifyRequested,
    SatellitePaired,
    TooManyAttempts,
    TooManyPending,
    group,
)
from nestor.modules.satellites.types import DeclaredCapability
from nestor.testing.journal import MemoryEventLog

REACHY = Manifest(
    Device("reachy-salon", "reachy-mini", "salon"),
    (
        DeclaredCapability(Capability("audio.capture")),
        DeclaredCapability(Capability("expression.emotion")),
        DeclaredCapability(IDENTIFY),
    ),
    (PairingMethod.SPEECH, PairingMethod.PROVISIONING),
)
SENSOR = Manifest(Device("capteur-entree", "esp32", "entree"), pairing_methods=(PairingMethod.PROVISIONING,))
PROVISIONED = PairingMethod.PROVISIONING
MATHIS = PersonId("mathis")


class Clock:
    def __init__(self) -> None:
        self.now = utc_now()

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def journal() -> Journal:
    return Journal(MemoryEventLog())


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def pairing(journal: Journal, clock: Clock) -> Pairing:
    pairing = Pairing(journal, clock=clock)
    await pairing.start()
    return pairing


def code_of(ticket: object) -> str:
    code = getattr(ticket, "device_code", None)
    assert isinstance(code, str)
    return code


async def _paired(pairing: Pairing, manifest: Manifest = REACHY) -> str:
    ticket = await pairing.request(manifest)
    await pairing.approve(code_of(ticket), by=MATHIS)
    token = pairing.poll(ticket.id).token
    assert token is not None
    return token


async def test_a_device_approved_by_its_code_gets_a_token_once_and_connects_with_it(pairing: Pairing) -> None:
    ticket = await pairing.request(REACHY)
    assert len(code_of(ticket)) == 6 and code_of(ticket).isdigit()
    assert pairing.poll(ticket.id).status is PairingStatus.PENDING
    assert [p.device for p in pairing.pending()] == [REACHY.device]

    satellite = await pairing.approve(code_of(ticket), by=MATHIS)
    first, second = pairing.poll(ticket.id), pairing.poll(ticket.id)

    assert first.status is PairingStatus.APPROVED and first.token
    assert (second.status, second.token) == (PairingStatus.CLAIMED, None), "the token is handed out only once"
    assert pairing.authenticate("reachy-salon", first.token) == satellite
    assert (satellite.room, satellite.capabilities) == ("salon", REACHY.names)
    assert not pairing.pending()


async def test_a_wrong_code_approves_nothing(pairing: Pairing) -> None:
    ticket = await pairing.request(REACHY)
    wrong = f"{(int(code_of(ticket)) + 1) % 10**6:06d}"
    with pytest.raises(PairingRefused):
        await pairing.approve(wrong)
    assert pairing.poll(ticket.id).status is PairingStatus.PENDING
    assert not pairing.satellites()


async def test_a_code_typed_on_another_devices_request_is_refused(pairing: Pairing) -> None:
    kitchen = Manifest(Device("pi-cuisine", "raspberry-pi", "cuisine"), REACHY.capabilities)
    salon, cuisine = await pairing.request(REACHY), await pairing.request(kitchen)
    with pytest.raises(PairingRefused):
        await pairing.approve(code_of(cuisine), pairing_id=salon.id)
    satellite = await pairing.approve(code_of(salon), pairing_id=salon.id)
    assert satellite.id == "reachy-salon" and pairing.poll(cuisine.id).status is PairingStatus.PENDING


async def test_a_pairing_expires_after_ten_minutes(pairing: Pairing, clock: Clock) -> None:
    ticket = await pairing.request(REACHY)
    clock.now += timedelta(minutes=10)
    with pytest.raises(PairingRefused):
        await pairing.approve(code_of(ticket))
    assert pairing.poll(ticket.id).status is PairingStatus.EXPIRED
    assert pairing.poll(ticket.id).status is PairingStatus.EXPIRED, "still expired once forgotten"


async def test_an_approved_token_not_claimed_in_time_is_lost(pairing: Pairing, clock: Clock) -> None:
    ticket = await pairing.request(REACHY)
    await pairing.approve(code_of(ticket))
    clock.now += timedelta(minutes=11)
    assert (pairing.poll(ticket.id).status, pairing.poll(ticket.id).token) == (PairingStatus.EXPIRED, None)


async def test_an_unknown_pairing_reads_as_expired(pairing: Pairing) -> None:
    assert pairing.poll("not-a-pairing").status is PairingStatus.EXPIRED


async def test_a_revoked_satellite_is_refused_even_after_a_restart(pairing: Pairing, journal: Journal) -> None:
    token = await _paired(pairing)
    await pairing.revoke("reachy-salon", by=MATHIS)
    assert pairing.authenticate("reachy-salon", token) is None

    restarted = Pairing(journal)
    await restarted.start()
    assert restarted.authenticate("reachy-salon", token) is None
    with pytest.raises(ContractError):
        await restarted.revoke("reachy-salon")


async def test_paired_satellites_survive_a_restart_and_the_journal_never_holds_a_token(
    pairing: Pairing, journal: Journal
) -> None:
    token = await _paired(pairing)
    restarted = Pairing(journal)
    await restarted.start()
    assert restarted.authenticate("reachy-salon", token) is not None
    records = [entry.record for entry in await journal.log.read(LogQuery())]
    assert records and token not in str(records)


async def test_a_replaced_or_borrowed_token_is_refused(pairing: Pairing) -> None:
    old = await _paired(pairing)
    new = await _paired(pairing)  # paired again: the token is rotated
    assert pairing.authenticate("reachy-salon", old) is None
    assert pairing.authenticate("reachy-salon", new) is not None
    assert pairing.authenticate("enceinte-cuisine", new) is None, "a token only opens its own device"
    assert pairing.authenticate("reachy-salon", "nst2_guessed") is None


async def test_the_approver_can_allow_less_than_the_device_declares(pairing: Pairing, journal: Journal) -> None:
    ticket = await pairing.request(REACHY)
    satellite = await pairing.approve(
        code_of(ticket), capabilities=[Capability("audio.capture"), Capability("motion.arm")]
    )
    assert satellite.capabilities == {Capability("audio.capture")}
    [paired] = await journal.history(SatellitePaired)
    assert paired.capabilities == ("audio.capture",)


async def test_asking_again_replaces_the_earlier_code(pairing: Pairing) -> None:
    first = await pairing.request(REACHY)
    second = await pairing.request(REACHY)
    with pytest.raises(PairingRefused):
        await pairing.approve(code_of(first) if code_of(first) != code_of(second) else "-")
    assert pairing.poll(first.id).status is PairingStatus.EXPIRED
    await pairing.approve(code_of(second))


async def test_too_many_waiting_devices_are_refused(journal: Journal) -> None:
    pairing = Pairing(journal, max_pending=2)
    for i in range(2):
        await pairing.request(Manifest(Device(f"device-{i}", "esp32", "salon")))
    with pytest.raises(PairingRefused):
        await pairing.request(Manifest(Device("device-2", "esp32", "salon")))


async def test_too_many_waiting_devices_are_told_to_come_back_but_an_enrolled_one_still_pairs(
    journal: Journal,
) -> None:
    pairing = Pairing(journal, max_pending=1)
    started = await pairing.start_addition(PROVISIONED)
    await pairing.request(REACHY)
    with pytest.raises(TooManyPending):
        await pairing.request(Manifest(Device("other", "esp32", "salon")))
    ticket = await pairing.request(SENSOR, enrollment_code=started.code, method=PROVISIONED)
    assert ticket.status is PairingStatus.APPROVED


# Enrollment codes, made by a person adding a satellite.


async def test_a_device_with_an_enrollment_code_is_paired_at_once_where_the_addition_says(
    pairing: Pairing, journal: Journal
) -> None:
    started = await pairing.start_addition(
        PROVISIONED, by=MATHIS, name="Capteur de l'entrée", room="couloir", capabilities=[IDENTIFY]
    )
    assert started.code is not None and len(started.code) == 8
    ticket = await pairing.request(SENSOR, enrollment_code=group(started.code).lower(), method=PROVISIONED)
    assert (ticket.status, ticket.device_code) == (PairingStatus.APPROVED, None), "no device code to present"

    state = pairing.poll(ticket.id)
    assert state.status is PairingStatus.APPROVED and state.token
    satellite = pairing.authenticate("capteur-entree", state.token)
    assert satellite is not None
    assert (satellite.room, satellite.name, satellite.capabilities) == ("couloir", "Capteur de l'entrée", frozenset())
    [paired] = await journal.history(SatellitePaired)
    assert (paired.proof, paired.method, paired.approved_by) == (Proof.ENROLLMENT_CODE, PROVISIONED, MATHIS)
    assert paired.addition_id == started.addition.id
    assert not pairing.additions(), "the addition is over"


async def test_an_enrollment_code_reads_back_whatever_the_case_dashes_and_lookalikes(pairing: Pairing) -> None:
    started = await pairing.start_addition(PROVISIONED)
    assert started.code is not None
    typed = " ".join(started.code).replace("0", "o").replace("1", "l").lower()
    assert (await pairing.request(SENSOR, enrollment_code=typed, method=PROVISIONED)).status is PairingStatus.APPROVED


async def test_an_enrollment_code_pairs_one_device_only(pairing: Pairing, journal: Journal) -> None:
    started = await pairing.start_addition(PROVISIONED)
    await pairing.request(SENSOR, enrollment_code=started.code, method=PROVISIONED)
    with pytest.raises(EnrollmentRefused) as refused:
        await pairing.request(REACHY, enrollment_code=started.code, method=PROVISIONED)
    assert refused.value.reason == "used"
    assert [s.id for s in pairing.satellites()] == ["capteur-entree"]
    [event] = await journal.history(SatelliteEnrollmentRefused)
    assert (event.device_id, event.reason, event.addition_id) == ("reachy-salon", "used", started.addition.id)


@pytest.mark.parametrize("reason", ["unknown", "expired", "cancelled"])
async def test_a_dead_enrollment_code_is_refused_and_says_why(pairing: Pairing, clock: Clock, reason: str) -> None:
    started = await pairing.start_addition(PROVISIONED, ttl_s=60)
    code = started.code if reason != "unknown" else "K7QF2M9X"
    if reason == "expired":
        clock.now += timedelta(seconds=60)
    if reason == "cancelled":
        await pairing.cancel_addition(started.addition.id, by=MATHIS)
    with pytest.raises(EnrollmentRefused) as refused:
        await pairing.request(SENSOR, enrollment_code=code, method=PROVISIONED)
    assert refused.value.reason == reason and not pairing.satellites()


async def test_an_expired_addition_is_journaled_once(pairing: Pairing, journal: Journal, clock: Clock) -> None:
    await pairing.start_addition(PairingMethod.QR, ttl_s=60)
    clock.now += timedelta(minutes=2)
    assert await pairing.expire_additions() == []
    assert await pairing.expire_additions() == []
    assert len(await journal.history(SatelliteAdditionExpired)) == 1


async def test_an_enrollment_code_comes_with_an_enrollment_method_the_device_declares(pairing: Pairing) -> None:
    started = await pairing.start_addition(PROVISIONED)
    for method in (None, PairingMethod.QR, PairingMethod.DISPLAY):
        with pytest.raises(ContractError):
            await pairing.request(SENSOR, enrollment_code=started.code, method=method)
    assert (await pairing.request(SENSOR, enrollment_code=started.code, method=PROVISIONED)).status.value == "approved"


async def test_an_addition_lasts_between_a_minute_and_a_week_and_cannot_pile_up(journal: Journal) -> None:
    pairing = Pairing(journal, max_additions=1)
    for ttl in (59, 7 * 24 * 3600 + 1):
        with pytest.raises(ContractError):
            await pairing.start_addition(PROVISIONED, ttl_s=ttl)
    with pytest.raises(ContractError):
        await pairing.start_addition(PROVISIONED, name="x" * 65)
    with pytest.raises(ContractError):
        await pairing.start_addition(PROVISIONED, room="Salon")
    await pairing.start_addition(PROVISIONED)
    with pytest.raises(PairingRefused):
        await pairing.start_addition(PROVISIONED)


async def test_additions_in_progress_survive_a_restart_and_the_journal_never_holds_a_code(
    pairing: Pairing, journal: Journal
) -> None:
    kept = await pairing.start_addition(PROVISIONED, room="cuisine")
    cancelled = await pairing.start_addition(PROVISIONED)
    await pairing.cancel_addition(cancelled.addition.id)
    restarted = Pairing(journal)
    await restarted.start()
    assert [a.id for a in restarted.additions()] == [kept.addition.id]
    ticket = await restarted.request(SENSOR, enrollment_code=kept.code, method=PROVISIONED)
    assert ticket.status is PairingStatus.APPROVED
    with pytest.raises(EnrollmentRefused):
        await restarted.request(REACHY, enrollment_code=cancelled.code, method=PROVISIONED)
    records = str([entry.record for entry in await journal.log.read(LogQuery())])
    assert kept.code is not None and kept.code not in records and str(cancelled.code) not in records


async def test_a_cancelled_or_unknown_addition_cannot_be_cancelled(pairing: Pairing) -> None:
    started = await pairing.start_addition(PROVISIONED)
    await pairing.cancel_addition(started.addition.id)
    for addition in (started.addition.id, "nope"):
        with pytest.raises(ContractError):
            await pairing.cancel_addition(addition)
    assert (await pairing.addition(started.addition.id)) is not None and await pairing.addition("nope") is None


# Two proofs racing for one pending device.


async def test_a_pending_device_can_be_handed_an_enrollment_code_and_its_device_code_is_then_refused(
    pairing: Pairing,
) -> None:
    ticket = await pairing.request(REACHY)
    started = await pairing.start_addition(PairingMethod.PROVISIONING, room="cuisine")
    state = await pairing.enroll(ticket.id, str(started.code), method=PROVISIONED)
    assert state.status is PairingStatus.APPROVED
    with pytest.raises(PairingRefused):
        await pairing.approve(code_of(ticket), pairing_id=ticket.id)
    claimed = pairing.poll(ticket.id)
    assert claimed.token and claimed.satellite is not None and claimed.satellite.room == "cuisine"


async def test_when_the_device_code_wins_the_enrollment_code_stays_usable(pairing: Pairing) -> None:
    ticket = await pairing.request(REACHY)
    started = await pairing.start_addition(PROVISIONED)
    await pairing.approve(code_of(ticket), pairing_id=ticket.id)
    with pytest.raises(NotPending):
        await pairing.enroll(ticket.id, str(started.code), method=PROVISIONED)
    assert pairing.poll(ticket.id).token, "the device keeps polling and gets its token"
    assert (await pairing.request(SENSOR, enrollment_code=started.code, method=PROVISIONED)).status.value == "approved"


async def test_an_enrollment_for_an_unknown_pairing_is_not_pending(pairing: Pairing) -> None:
    with pytest.raises(NotPending):
        await pairing.enroll("nope", "K7QF2M9X", method=PROVISIONED)


async def test_typing_a_device_code_for_an_addition_applies_it_and_completes_it(
    pairing: Pairing, journal: Journal
) -> None:
    started = await pairing.start_addition(PairingMethod.SPEECH, name="Reachy", room="bureau", by=MATHIS)
    assert started.code is None, "a device code addition makes no code"
    ticket = await pairing.request(REACHY)
    satellite = await pairing.approve(code_of(ticket), pairing_id=ticket.id, addition_id=started.addition.id)
    assert (satellite.room, satellite.name) == ("bureau", "Reachy")
    [paired] = await journal.history(SatellitePaired)
    assert (paired.proof, paired.method) == (Proof.DEVICE_CODE, PairingMethod.SPEECH)
    [completed] = await journal.history(SatelliteAdditionCompleted)
    assert completed.device_id == "reachy-salon"
    with pytest.raises(PairingRefused) as over:
        await pairing.approve(code_of(await pairing.request(REACHY)), addition_id=started.addition.id)
    assert over.value.reason == "addition_over"


async def test_an_addition_narrows_what_the_approver_grants(pairing: Pairing) -> None:
    started = await pairing.start_addition(PairingMethod.SPEECH, capabilities=[Capability("audio.capture")])
    ticket = await pairing.request(REACHY)
    satellite = await pairing.approve(code_of(ticket), addition_id=started.addition.id)
    assert satellite.capabilities == {Capability("audio.capture")}


async def test_a_device_code_approval_refuses_an_enrollment_method(pairing: Pairing) -> None:
    ticket = await pairing.request(REACHY)
    with pytest.raises(ContractError):
        await pairing.approve(code_of(ticket), method=PairingMethod.QR)
    enrolled = await pairing.start_addition(PairingMethod.QR)
    with pytest.raises(ContractError):
        await pairing.approve(code_of(ticket), addition_id=enrolled.addition.id)


# Rate limits.


async def test_wrong_codes_from_one_address_are_limited_then_forgiven(journal: Journal, clock: Clock) -> None:
    pairing = Pairing(journal, clock=clock, limiter=AttemptLimiter(per_source=2, overall=10, window_s=60))
    started = await pairing.start_addition(PROVISIONED)
    for _ in range(2):
        with pytest.raises(EnrollmentRefused):
            await pairing.request(SENSOR, enrollment_code="ZZZZZZZZ", method=PROVISIONED, source="10.0.0.9")
    with pytest.raises(TooManyAttempts) as limited:
        await pairing.request(SENSOR, enrollment_code=started.code, method=PROVISIONED, source="10.0.0.9")
    assert 1 <= limited.value.retry_after_s <= 60, "even the right code waits: the limit reveals nothing"
    other = await pairing.request(REACHY, enrollment_code=started.code, method=PROVISIONED, source="10.0.0.7")
    assert other.status is PairingStatus.APPROVED, "another address is not limited"
    clock.now += timedelta(seconds=61)
    with pytest.raises(EnrollmentRefused):
        await pairing.request(SENSOR, enrollment_code="ZZZZZZZZ", method=PROVISIONED, source="10.0.0.9")


async def test_wrong_codes_from_everywhere_are_limited_overall(journal: Journal) -> None:
    pairing = Pairing(journal, limiter=AttemptLimiter(per_source=5, overall=3))
    for i in range(3):
        with pytest.raises(EnrollmentRefused):
            await pairing.request(SENSOR, enrollment_code="ZZZZZZZZ", method=PROVISIONED, source=f"10.0.0.{i}")
    with pytest.raises(TooManyAttempts):
        await pairing.enroll("any", "ZZZZZZZZ", method=PROVISIONED, source="10.0.0.99")


# Identify.


async def test_a_pending_device_hears_identify_once_at_its_next_poll(pairing: Pairing, journal: Journal) -> None:
    ticket = await pairing.request(REACHY)
    await pairing.identify_pending(ticket.id, by=MATHIS)
    assert pairing.poll(ticket.id).identify is True
    assert pairing.poll(ticket.id).identify is False
    [asked] = await journal.history(SatelliteIdentifyRequested)
    assert (asked.device_id, asked.pairing_id, asked.requested_by) == ("reachy-salon", ticket.id, MATHIS)


async def test_identify_is_refused_to_a_device_that_cannot_or_does_not_wait(pairing: Pairing) -> None:
    quiet = await pairing.request(Manifest(Device("micro", "esp32", "salon")))
    with pytest.raises(IdentifyUnavailable) as unsupported:
        await pairing.identify_pending(quiet.id)
    with pytest.raises(IdentifyUnavailable) as unknown:
        await pairing.identify_pending("nope")
    assert (unsupported.value.reason, unknown.value.reason) == ("unsupported", "unknown")


async def test_a_paired_device_is_asked_to_identify_through_its_link_while_connected(pairing: Pairing) -> None:
    await _paired(pairing)
    with pytest.raises(IdentifyUnavailable) as offline:
        await pairing.identify("reachy-salon")
    assert offline.value.reason == "offline"
    asked: list[str] = []
    with pairing.online("reachy-salon", lambda: asked.append("reachy-salon")):
        await pairing.identify("reachy-salon", by=MATHIS)
    assert asked == ["reachy-salon"]
    with pytest.raises(IdentifyUnavailable):
        await pairing.identify("reachy-salon")


async def test_identify_is_refused_to_a_satellite_not_allowed_it_or_unknown(pairing: Pairing) -> None:
    ticket = await pairing.request(REACHY)
    await pairing.approve(code_of(ticket), capabilities=[Capability("audio.capture")])
    with pairing.online("reachy-salon", lambda: None), pytest.raises(IdentifyUnavailable) as unsupported:
        await pairing.identify("reachy-salon")
    with pytest.raises(IdentifyUnavailable) as unknown:
        await pairing.identify("nope")
    assert (unsupported.value.reason, unknown.value.reason) == ("unsupported", "unknown")


# Versions.


async def test_satellites_paired_with_protocol_1_must_pair_again(journal: Journal) -> None:
    from nestor.modules.journal import Entry

    record = SatellitePaired(
        source="satellites", pairing_id="p", device=SENSOR.device, capabilities=(), token_hash="h",
        protocol="nestor.satellite/2", proof=Proof.DEVICE_CODE,
    ).to_record()  # fmt: skip
    record["version"] = 1
    payload = record["payload"]
    assert isinstance(payload, dict)
    for key in ("protocol", "proof", "method", "addition_id", "name"):
        payload.pop(key, None)
    upgraded = SatellitePaired.from_record(Entry(position=1, record=record).record)
    assert isinstance(upgraded, SatellitePaired)
    assert (upgraded.protocol, upgraded.proof) == ("nestor.satellite/1", Proof.DEVICE_CODE)
    await journal.publish(upgraded)
    restarted = Pairing(journal)
    await restarted.start()
    assert restarted.satellites() == []
