# Nestor satellite protocol, `nestor.satellite/2`

Status: current. Supersedes `nestor.satellite/1`, which cores no longer accept.

A **satellite** is a device that pairs with a Nestor **core**, declares what it can do, streams audio,
reports observations and carries out the core's intents. This document is the standard: SDKs and
drivers in any language implement it, and the core's black-box conformance suite
(`nestor.adapters.channels.voice.satellites.conformance`) checks them against it.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are to be read as in RFC 2119.

The message classes of `nestor.modules.satellites.wire` are the source of truth for shapes: the JSON
Schemas they generate are published in `src/nestor/modules/satellites/schemas/` (`nestor satellites
schemas`) under `https://nestor.mathislambert.fr/schemas/satellite/2/`. SDKs copy them and test what
they send against them.

## 1. Overview

```text
device                                  core                                 household member
  │ POST /satellites/pairings ────────▶ pending + device code            ◀── starts an addition (optional)
  │ presents the device code (screen, voice, log)
  │                                                       ◀──────────────── types the device code
  │                           or, whichever comes first
  │ POST …/{pairing_id}/enrollment ───▶ approved                             (enrollment code made in the admin)
  │ GET  /satellites/pairings/{id} ───▶ approved + token (once)
  │ POST /satellites/{device_id}/offer (Bearer token, WebRTC SDP)
  │ data channel `nestor`: hello → welcome, intents ⇄ acks, observations
```

A device configured with an enrollment code sends it with its first request and is approved at once.

## 2. Pairing methods

The proof that a person meant to pair a device travels in either direction:

- a **device code** goes from the device to the person, who types it in the admin;
- an **enrollment code** goes from the admin to the device, which presents it to the core.

The device declares the methods it supports; the person picks one. The methods are:

| Method | Proof | The person… |
| --- | --- | --- |
| `device_code.display` | device code | reads the code on the device's screen and types it in the admin |
| `device_code.speech` | device code | hears the device say its code and types it in the admin |
| `enrollment.input` | enrollment code | types the enrollment code on the device |
| `enrollment.provisioning` | enrollment code | sets the pairing URI or code in the device's configuration (flag, environment, file) |
| `enrollment.qr` | enrollment code | shows the pairing URI's QR code to the device's camera |

Identify (section 6) is not a method: it helps tell devices apart and is declared as the capability
`device.identify`.

### 2.1 Negotiation

- **N1.** A manifest MUST list the methods the device supports in `pairing_methods`, at least one,
  without repetition. A device MUST NOT declare a method it cannot carry out.
- **N2.** The core recommends one method, the first the device supports in this order:
  `device_code.display`, `device_code.speech`, `enrollment.qr`, `enrollment.input`,
  `enrollment.provisioning`. For a device that has not contacted the core yet, every method is
  offered. The admin highlights the recommended method and keeps the others available.
- **N3.** The device never imposes a method. Whatever the person picks, the device MUST accept both
  proofs until one is accepted (section 3.3).

## 3. Pairing

### 3.1 Endpoints

All bodies are JSON (`Content-Type: application/json`).

| Request | Body | Answer |
| --- | --- | --- |
| `POST /satellites/pairings` | `pairing.request` | `201` `pairing.ticket` |
| `POST /satellites/pairings/{pairing_id}/enrollment` | `pairing.enrollment` | `200` `pairing.state` |
| `GET /satellites/pairings/{pairing_id}` | | `200` `pairing.state` |

```json
POST /satellites/pairings
{"manifest": {"protocol": "nestor.satellite/2",
              "device": {"id": "capteur-entree", "model": "esp32", "room": "entree"},
              "capabilities": [{"name": "device.identify"}],
              "pairing_methods": ["enrollment.provisioning", "enrollment.qr"]},
 "enrollment_code": "K7QF2M9X", "method": "enrollment.provisioning"}

201 {"pairing_id": "…", "status": "approved", "expires_at": "2026-10-30T12:10:00+00:00"}
201 {"pairing_id": "…", "status": "pending", "expires_at": "…", "device_code": "042917"}   (without a code)

GET /satellites/pairings/{pairing_id}
200 {"status": "pending", "identify": true}
200 {"status": "approved", "token": "nst2_…", "device_id": "capteur-entree", "room": "entree",
     "capabilities": ["device.identify"]}
```

Errors answer `pairing.error`: `{"error": code, "detail": text, "reason"?: …, "retry_after_s"?: …}`.

| `error` | Status | Meaning |
| --- | --- | --- |
| `invalid_request` | 422 | the body does not follow its schema |
| `protocol_unsupported` | 422 | the manifest names another version of this protocol |
| `too_many_pending` | 429 | too many devices wait for a proof; `Retry-After` and `retry_after_s` say when to try again |
| `too_many_attempts` | 429 | too many wrong enrollment codes; `Retry-After` and `retry_after_s` say when to try again |
| `enrollment_refused` | 403 | the enrollment code pairs nothing; `reason` is `unknown`, `expired`, `used` or `cancelled` |
| `not_pending` | 409 | the pairing no longer waits for a proof: the other proof won, or it expired |

`detail` is English for logs. A device that shows or says an error to people MUST translate it from
`error` and `reason`, never show `detail`.

### 3.2 States of a pairing

```text
             device code typed in the admin
           ┌───────────────────────────────┐
request ──▶ pending                         ├──▶ approved ──(first poll: token)──▶ claimed
  │        └───────────────────────────────┘        │
  │          enrollment code accepted               │ deadline passes, token unclaimed
  │                                                 ▼
  └── with an enrollment code ──▶ approved      expired ◀── deadline passes while pending,
                                                             or the device asks again (superseded)
```

- A pending pairing lasts 10 minutes. An unknown, superseded or forgotten `pairing_id` reads as
  `expired`, so polling reveals nothing.
- The token is handed out with the first `approved` answer only; later polls read `claimed`.

### 3.3 Device rules

- **P1.** A device MUST support `enrollment.provisioning`: it reads a pairing URI from the environment
  variable `NESTOR_PAIRING_URI`, or an enrollment code from `NESTOR_PAIRING_CODE` with the core's
  address given separately, and SHOULD accept both from a command-line flag and its configuration
  file.
- **P2.** With no enrollment code, a device MUST request a pairing and present its device code through
  every output it has: on a screen (`device_code.display`), aloud (`device_code.speech`: digits one
  by one, said twice, in the device's language), and always in its log. A device with neither screen
  nor voice MUST log the device code and say, in the log, that an enrollment code is the way to pair
  it. It then polls the pairing about once a second until it is approved or expires; when it
  expires, it requests again.
- **P3.** A device with an enrollment code MUST send it with its request, with the method it received
  it by, and MUST NOT present a device code unless that code is refused.
- **P4.** A pending device MUST accept an enrollment code at any time (typed, scanned, configured) and
  send it to `POST …/{pairing_id}/enrollment`. Whichever proof is accepted first wins:
  - if the device code was typed first, the enrollment answers `not_pending` and the enrollment code
    is **not** spent: the device keeps polling and gets its token;
  - if the enrollment code was accepted first, the device code typed afterwards is refused.
  On `approved`, the device stops presenting its device code.
- **P5.** An enrollment code refused with `enrollment_refused` MUST NOT be presented again. The device
  MUST say so in its log (and on its outputs, translated), then fall back to a device code (P2) so a
  person can still pair it.
- **P6.** On `429`, a device MUST wait at least `Retry-After` seconds before trying again.
- **P7.** Enrollment codes MUST be normalised before they are sent (section 4.2); a device MAY send
  them as typed, the core normalises too.
- **P8.** A device MUST keep its token secret (readable by its owner only on a file system) and forget
  it when the core refuses it (`401` on an offer), then pair again.

### 3.4 Core rules

- **C1.** The core accepts only `nestor.satellite/2`. A manifest naming another
  `nestor.satellite/<n>` is refused with `protocol_unsupported`.
- **C2.** An enrollment code pairs one device: it is spent as soon as it is accepted, before anything
  else can observe it, so two devices racing with it get one approval and one `enrollment_refused`
  (`used`).
- **C3.** A proof is accepted only while its pairing is `pending`; the first one accepted moves it to
  `approved` at once. An enrollment code refused because the pairing is no longer pending is not
  spent.
- **C4.** The token is 256 random bits, prefixed `nst2_`; only its SHA-256 is kept.
- **C5.** Asking again with the same device id replaces the earlier pending request.
- **C6.** The journal records every step: `satellite.pairing.requested` (with the declared methods),
  `satellite.addition.started|completed|cancelled|expired`, `satellite.enrollment.refused` (with its
  reason and address), `satellite.paired` (with the proof, the method and the addition),
  `satellite.identify.requested`, `satellite.revoked`. Never a code or a token in clear.

### 3.5 Additions

A person adds a satellite from the admin by starting an **addition**: the method chosen, and
optionally a name, a room and the capabilities to allow at most. It lasts 15 minutes by default (1
minute to 7 days).

- With an enrollment method, the addition makes the enrollment code, returned once with its pairing
  URI. The device that presents it is paired at once, named, in the addition's room, with the
  capabilities it declared narrowed to the addition's.
- With a device code method, the addition waits for a device: the admin lists the pending devices,
  the person tells them apart (identify), types the code the right one presents, and the addition's
  name, room and capabilities apply.

An addition ends when its device is paired (`completed`), when a person cancels it, or when it
expires. At most 32 are in progress at once. An addition pairs one device: the core claims it in one
step, so two people typing codes for it at the same instant pair one device, and the other is told
the addition is over.

## 4. Codes and URI

### 4.1 Device code

Six decimal digits (`042917`), random, unique among pending pairings. Digits read well aloud and on
any screen.

### 4.2 Enrollment code

- Eight symbols of Crockford's base32 alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ`: 40 random bits.
- Shown grouped by four: `K7QF-2M9X`.
- Normalisation, before any comparison: remove spaces and dashes, upper-case, then map `O` → `0`,
  `I` and `L` → `1`. A result that is not 8 symbols of the alphabet is no code (`U` is never one).
- Canonical form: the normalised 8 symbols, without the dash.

### 4.3 Pairing URI

```text
nestor+http://nestor.local:7860/?code=K7QF2M9X
nestor+https://nestor.example.org/satellites-proxy/?code=K7QF2M9X
```

- The scheme is `nestor+` followed by the scheme of the core's base URL (`http` or `https`); host,
  port and path are the core's base URL. Removing `nestor+` and the query gives the base URL.
- `code` is the enrollment code, canonical form.
- Why this form: the core's address and the code travel together, so a headless device needs nothing
  else; the transport (TLS or not) is explicit; any URL parser reads it; the prefix tells a scanner or
  a configuration loader what it holds, as `git+https` does.
- The admin returns the URI; a front renders its QR code itself.

## 5. Manifest

```json
{"protocol": "nestor.satellite/2",
 "device": {"id": "salon", "model": "reachy-mini", "room": "salon", "brand": "pollen-robotics"},
 "sdk": {"name": "nestor-satellite-python", "version": "0.2.0"},
 "capabilities": [{"name": "audio.capture"}, {"name": "audio.playback"}, {"name": "device.identify"}],
 "pairing_methods": ["device_code.speech", "enrollment.provisioning"]}
```

`id` and `room` are lowercase slugs (`^[a-z0-9][a-z0-9_-]{0,63}$`). Capabilities are `family.feature`
names, at most 32, each declared once. Known capabilities: `audio.capture`, `audio.playback`,
`audio.speech_activity`, `vision.person_detection`, `expression.emotion`, `motion.head`,
`device.identify`. The manifest is sent when pairing and in `hello`.

## 6. Identify

- **I1.** A device declaring `device.identify` MUST, on a pending poll answer carrying
  `"identify": true`, make itself noticed for a few seconds with the outputs it has (blink, wiggle,
  chime, flash its screen), and keep polling.
- **I2.** Once paired and allowed `device.identify`, it MUST acknowledge `intent.identify` like any
  intent, and make itself noticed the same way.
- **I3.** The core sends identify only to a device that declared it (pending) or was allowed it
  (paired). The admin refuses it otherwise, and for a paired device that is not connected.
- Identify only helps a person tell devices apart. It proves nothing: any device can blink when told
  to, so it never replaces a code.

## 7. Realtime link

- **W1.** With its token, the device offers WebRTC: `POST /satellites/{device_id}/offer` with
  `Authorization: Bearer <token>` and `{"sdp", "type"}`; the core answers `{"sdp", "type", "pc_id"}`.
  ICE candidates follow with `PATCH` on the same path. A wrong token answers `401`; another device's
  `pc_id`, `403`.
- **W2.** On the data channel `nestor`, every message is `{"type", "id", "at", "payload"}`. The device
  MUST send `hello` (its manifest, with the paired device id) first; the core answers `welcome` (the
  paired room and the allowed capabilities). The device MUST acknowledge each `intent.*` with `ack`
  within a second, and MUST only report observations it was allowed. Unknown message types from the
  core are ignored.
- **W3.** Audio: Opus over WebRTC, the core's voice to the device, the microphone (with
  `audio.capture`) to the core.
- **W4.** After a hang-up or a lost link, the device reconnects with the same token, with a growing
  delay.

## 8. Security considerations

- **Entropy.** An enrollment code has 40 bits (about 1.1 × 10¹² values). With at most 32 codes in
  progress and at most 5 wrong codes per minute and address (20 from all addresses), the 300 guesses
  that fit in a 15-minute lifetime hit one about once in 10⁸; finding one takes about 1,600 years of
  guessing on average. A device code has 20 bits but is only typed by a signed-in person, on a pending
  pairing they picked (`pairing_id`), within 10 minutes.
- **Lifetime.** Enrollment codes last 15 minutes by default, 7 days at most; device codes 10 minutes.
- **Single use.** An accepted enrollment code is spent before the answer is written (C2).
- **Rate limits.** Wrong enrollment codes are counted per client address and overall over a sliding
  minute. Past either limit, every attempt, right or wrong, is refused with `429` until the window
  frees a slot, so a limited client learns nothing.
- **Hashing.** Only SHA-256 hashes of codes and tokens are stored, and journaled. A presented code is
  compared with every known hash in constant time. 40 bits can be brute-forced offline from a leaked
  hash, so the hash is only worth something while the code lives: keep lifetimes short.
- **Transport.** Codes and tokens cross the network in clear over `http`; use `https` (a
  `nestor+https` URI) outside a trusted home network.
- **What identify does not prove.** Identify shows which device answers, not that it is the one the
  person holds: never pair on identify alone.
- **Consent.** Pairing gives a device only the capabilities a person allowed, never more than it
  declared.

## 9. Conformance

`check_satellite(driver)` launches the driver once per scenario: a Python coroutine function taking a
`Launch`, or a command where `{url}` is the core's URL and `{state}` a fresh folder for its token. The
enrollment code is given in `NESTOR_PAIRING_URI`.

| Check | Rules |
| --- | --- |
| declares enrollment.provisioning | N1, P1 |
| asks to pair; claims its token once its device code is typed | P2 |
| keeps polling after a pending identify (when it declares `device.identify`) | I1 |
| connects with its token; sends a hello first; introduces itself as the paired device | W1, W2 |
| acknowledges each intent within 1 s (`intent.identify` when allowed) | W2, I2 |
| every message follows the schema | W2 |
| receives the core's audio; sends its microphone audio | W3 |
| reconnects with the same token after a hang-up | W4 |
| pairs with the enrollment code of `NESTOR_PAIRING_URI`, no code typed | P1, P3 |
| falls back to a device code after its enrollment code is refused (wrong, expired, used) | P5 |
| presents a refused enrollment code only once (wrong, expired, used) | P5 |
| waits for Retry-After when rate-limited; pairs once the limit lifts | P6 |

The core's own rules (C1 to C6, the race of P4, I3, the limits) are proven by its tests
(`tests/modules/satellites/`, `tests/adapters/channels/voice/satellites/test_gateway.py`).

## 10. Changelog

- **2 (30/10/2026).** Pairing in both directions: device codes (shown, spoken or logged) and
  enrollment codes (typed, provisioned, scanned) made by a person adding a satellite from the admin,
  with the pairing URI. `pairing_methods` in the manifest. Identify (`device.identify`,
  `intent.identify`, `identify` in poll answers). New pairing endpoints (`/satellites/pairings`), JSON
  Schemas for every pairing body, errors with codes. Tokens prefixed `nst2_`.
  No compatibility with version 1: cores refuse its manifests, and satellites paired under version 1
  no longer authenticate. Update each device, then pair it again.
- **1.** Device code pairing, realtime link over WebRTC.
