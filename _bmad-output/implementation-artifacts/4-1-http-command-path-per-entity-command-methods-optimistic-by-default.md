# Story 4.1: HTTP command path + per-entity command methods (optimistic by default)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a library user,
I want `await turnout.throw()`, `await turnout.close()`, `await light.on()` / `off()`, `await memory.set_value(...)`, and `await route.activate()` — each returning when JMRI has acknowledged the command (no false-positive physical-confirmation claims),
So that I can write scripts that actively control my layout, knowing exactly what the library does and does not promise.

## Scope notes

- **First user-facing write path.** Epics 1–3 read JMRI and listen to events; this is the first story that sends commands. Story 4.2 layers `wait_for_jmri_state=True` on top; this story is **optimistic only** (return on JMRI HTTP ack, no WS confirmation).
- **Eight files in src/, modest in size.** New `command()` method on `HTTPClient`; new outbound-code maps in `_codes.py`; new command-issuing method on `Client` (and matching `ClientHandle` Protocol entry); new methods on `Turnout`, `Light`, `Memory`, `Route` entity classes. `LayoutEntityNotControllable` already exists in `exceptions.py` — no exception-hierarchy changes.
- **Read-only entities stay read-only at compile time.** No `set_state`/`set_value`/`activate` on `Sensor`, `Block`, `SignalHead`, `SignalMast` in v1. The architecture sec. Internal Layering is explicit: these are read-only entities.
- **NFR3 is a real, measurable target.** Median library overhead per command must be < 20 ms beyond JMRI's HTTP response. The microbenchmark belongs in the integration suite (skipped in CI; runs locally).
- **NCE open-loop limitation applies equally on simulator and live hardware.** Mikey's physical NCE layout has no feedback sensors wired; the simulator behaves identically. When pyjmri commands a turnout, JMRI's internal table updates, but whether JMRI emits a WS state-change event for that command depends on JMRI's per-type feedback-mode configuration, not on simulator-vs-hardware. Epic 3 evidence: sensor commands echo via WS; turnout commands do not (on Mikey's profiles, on both sim and the real layout). This matters for Story 4.2 (which awaits the event). In **this** story commands are optimistic — we only verify JMRI acked the HTTP, not the WS event. The integration test probes state via a subsequent read (`get_state()`) rather than a WS waiter, and where re-read doesn't reflect the commanded state (turnouts on this layout family), the test logs a WARN and continues; the HTTP ack itself is this story's contract.
- **Live-JMRI spike comes first** (Epic 3 retro action C2). Before locking the request shape in `_codes.py`, the dev agent must hit a running JMRI simulator and confirm: HTTP method (POST vs PUT), endpoint path, request body shape, response shape, and which integer codes JMRI accepts for each commandable type. Existing `tests/integration/test_reconnect_resilience.py:56-79` is a *partial* witness (sensor and turnout POST shapes), but the turnout state-code constants in that file appear inverted relative to `_codes.py` (it uses `THROWN=2, CLOSED=4` while `_codes.py` has `CLOSED=2, THROWN=4`). This worked because turnout WS echoes do not arrive on Mikey's JMRI configuration, so the wrong constant never produced a test failure. The spike must resolve which set of codes JMRI actually accepts for outbound commands.
- **`_DISPATCH_PARSERS` opaque-string deferred work item is out of scope here.** Epic 3 retro § Carry-forward deferred work and `deferred-work.md` flag the `primary_attr` opaque string in `client.py:635-652`. Story 4.1 doesn't have to fix it — command dispatch is by entity type only and does not touch this table. Leave the fix to Epic 6 / Growth.

## Acceptance Criteria

### AC1 — `HTTPClient.command(...)` is the only place wire payloads are built

**Given** the existing `_transport.HTTPClient` from Story 2.1
**When** an HTTP command path is added — a single new method `HTTPClient.command(entity_type: str, name: str, payload: dict[str, Any]) -> None`
**Then** the method issues `POST /json/v5/<entity_type>/<urlquoted-name>` with body `{"type": entity_type, "data": {"name": name, **payload}}`
**And** the method awaits JMRI's HTTP response and returns when JMRI has acknowledged with a 2xx status (200 typical; 204 also accepted)
**And** any non-2xx raises either `JMRIProtocolError` (default) or a more specific error from AC7 (`LayoutEntityNotControllable` / `LayoutEntityNotFound`) when the response body matches the JMRI error envelope
**And** the method catches and translates `httpx.*` exceptions exactly as `HTTPClient.get` does (`ConnectError`/`TransportError` → `JMRIConnectionError`; `TimeoutException` → `JMRIRequestTimeout`)
**And** the method logs the outbound at `DEBUG` on `pyjmri.transport` with `extra={"method": "POST", "path": ..., "status": ...}`
**And** no other module constructs an outbound command body — entities call only via the `ClientHandle` Protocol

### AC2 — `Turnout` gains `throw()`, `close()`, `set_state(state)`

**Given** the `Turnout` class from Story 2.3 (read-only) and `TurnoutState` enum
**When** three new methods are added — `Turnout.set_state(state: TurnoutState)`, `Turnout.throw()` (alias for `set_state(TurnoutState.THROWN)`), `Turnout.close()` (alias for `set_state(TurnoutState.CLOSED)`)
**Then** each invokes the HTTP command path via `ClientHandle.command(entity_type, name, payload)` and returns once JMRI acknowledges (FR17)
**And** `set_state` only accepts the two commandable values (`THROWN`, `CLOSED`); passing `UNKNOWN` or `INCONSISTENT` raises `ValueError` synchronously before any I/O (these are observable-only states, not commandable)
**And** each method's docstring includes the exact sentence: "Returns when JMRI has accepted the command; the library does not confirm physical layout state because NCE is open-loop." (FR22, FR37)
**And** each method's docstring also notes that `wait_for_jmri_state=True` is *not* available in this story — Story 4.2 adds it
**And** unit tests assert (via the `make_fake_handle` fixture's `command_calls` list) that the correct `(entity_type, name, payload)` tuple is sent for both `throw()` and `close()`

### AC3 — `Light.on()`, `Light.off()`, `Light.set_state(state)` (FR19)

**Given** the `Light` class from Story 2.3 and `LightState` enum
**When** three new methods are added — `Light.set_state(state: LightState)`, `Light.on()` (alias for `set_state(LightState.ON)`), `Light.off()` (alias for `set_state(LightState.OFF)`)
**Then** each invokes the HTTP command path with payload `{"state": <wire-format integer for the enum>}`
**And** `set_state` only accepts `ON` or `OFF`; passing `UNKNOWN` or `INCONSISTENT` raises `ValueError` synchronously
**And** docstrings carry the same NCE open-loop sentence as turnout (FR22)
**And** unit tests use a fake handle to verify the correct payload is sent

### AC4 — `Memory.set_value(value: str)` (FR18)

**Given** the `Memory` class from Story 2.3 (currently read-only)
**When** a new method `Memory.set_value(value: str)` is added
**Then** it invokes the HTTP command path with payload `{"value": value}` (memory uses `value`, not `state`)
**And** the method does **not** update `self.value` optimistically — it remains the last-read cached value until the next `get_value()` (consistent with FR22; optimistic update would be a false-positive confirmation)
**And** the docstring notes: "JMRI's HTTP ack confirms it accepted the assignment; call `get_value()` afterward to refresh the cached `value`."
**And** unit tests cover the `set_value` payload shape

### AC5 — `Route.activate()` (FR20)

**Given** the `Route` class from Story 2.3 (metadata-only) and a `RouteState` enum added in this story (members: `UNKNOWN`, `ACTIVE`)
**When** a new method `Route.activate()` is added
**Then** it invokes the HTTP command path with payload `{"state": <wire-format integer for ACTIVE>}` (verified by the live-JMRI spike — JMRI route activation state code, typically `2` for ACTIVE or `8` for TOGGLE)
**And** the new `RouteState` enum is exported from `pyjmri` (top-level `__init__.py` `__all__`)
**And** the docstring notes: "Activates the saved sequence of turnout commands. Returns when JMRI has accepted the activation; physical turnout outcomes are not confirmed (NCE open-loop)."
**And** unit tests cover the activation payload shape

### AC6 — Read-only entities have no command methods (compile-time read-only)

**Given** `Sensor`, `Block`, `SignalHead`, `SignalMast` from Story 2.3
**When** a reviewer inspects each module
**Then** none defines `set_state`, `set_value`, `set_appearance`, `set_aspect`, `activate`, `on`, `off`, `throw`, or `close`
**And** each class docstring contains a "Read-only in v1" sentence linking to the README Limitations section (Story 6.2; the link is a forward reference — README isn't written yet, but the sentence makes the intent explicit so future readers know it's deliberate)

### AC7 — `LayoutEntityNotControllable` translation from JMRI HTTP errors

**Given** JMRI returns an HTTP error indicating a commandable entity is currently not controllable (e.g., the entity exists but is locked by a Dispatcher section, or JMRI's permission model rejects the write)
**When** the library translates the HTTP response
**Then** `HTTPClient.command(...)` raises `LayoutEntityNotControllable` (with `entity_type`, `name`, and JMRI's reason text in `context`)
**And** the trigger condition is JMRI returning `4xx` (typically `403` or `409`) with a JSON error body shape (the spike must confirm the exact shape — JMRI typically returns `{"type": "error", "data": {"code": <int>, "message": "..."}}`)
**And** unit tests cover the translation against a synthetic JMRI error response constructed via `httpx.MockTransport`
**And** the existing `JMRIProtocolError` catch-all in `HTTPClient.command` remains — `LayoutEntityNotControllable` is raised *only* when the response body matches the JMRI error envelope shape

### AC8 — FR37 discipline preserved (no exceptions for undetectable failures)

**Given** FR37's rule (no exceptions for failure modes the library cannot detect)
**When** a reviewer audits the exception types raised by command methods
**Then** the only exception types raised by command paths are: `JMRIConnectionError`, `JMRIRequestTimeout`, `JMRIProtocolError`, `LayoutEntityNotFound`, `LayoutEntityNotControllable`, and `ValueError` (for invalid commandable-state arguments)
**And** no new exception types exist for "loco missing on the rails," "turnout physically failed to move," "route's first turnout did not respond," or any other open-loop NCE outcome
**And** a one-paragraph comment near the top of `Turnout.set_state` (or the shared `ClientHandle.command` Protocol entry) explains why these failure modes are deliberately unmodeled, citing FR22 and FR37

### AC9 — Integration round-trip test against a running JMRI

**Given** an integration test against a running JMRI (simulator is the default; the test runs the same on hardware)
**When** `tests/integration/test_command_round_trip.py` exercises one commandable entity per type — picks the first turnout, light, memory, and route from `discover()`
**Then** the test performs these steps for each entity:

1. Read each entity's current state/value via `get_state()` / `get_value()`.
2. Command the opposite/different state via the new command method.
3. Re-read state/value via `get_state()` / `get_value()` (NOT via WS waiter — Story 4.2 covers that path).
4. Assert the re-read state matches the commanded state.

**And** the test is layout-agnostic (no hardcoded names or DCC addresses) and skips entity types not present in the running layout (e.g., a layout with no routes skips the route assertion, doesn't fail)
**And** the test restores each entity to its original state at teardown to leave the layout as it found it
**And** for turnouts specifically, the test must accept the NCE open-loop reality: if `get_state()` after the command still reports the pre-command state, the test logs a WARNING (`"turnout command accepted by JMRI but state did not change on re-read — expected on NCE without physical feedback (applies to simulator and live layout equally)"`) and continues, rather than failing. The HTTP ack itself is the contract this story tests; re-read confirmation is best-effort
**And** the test is `@pytest.mark.integration` — does not run in default CI

### AC10 — NFR3 microbenchmark (library overhead < 20 ms median)

**Given** NFR3's budget (library command-overhead median < 20 ms beyond JMRI's HTTP response time)
**When** `tests/integration/test_command_latency.py` runs 20 trials of `turnout.throw()` / `turnout.close()` alternating, against a local JMRI simulator
**Then** for each call the test measures both `call_total_ms` (`monotonic()` around the `await`) and `jmri_http_ms` (the elapsed time inside the JMRI HTTP roundtrip — measurable by issuing the identical request via a raw `httpx.AsyncClient.post(...)` adjacent to the library call, or by instrumenting `HTTPClient.command` to record the inner `await self._http.post(...)` time on the latest call)
**And** the median across 20 trials of `(call_total_ms - jmri_http_ms)` is less than 20 ms
**And** the assertion includes the full 20-sample list and the computed median in its failure message
**And** the test is `@pytest.mark.integration` AND `@pytest.mark.slow` (uses the marker registered in Story 3.4) so it doesn't run in the default integration invocation either; release-prep only
**And** if no turnout is present, the test skips with a clear message

## Tasks / Subtasks

- [x] **Task 0 — Live-JMRI spike: verify wire format for all four commandable types** (AC: 1, 5, 7) — do this first, per Epic 3 retro C2
  - [x] Start JMRI with the `Basement_Revised_2024.jmri` profile (NCE Simulator, the dev's default). Confirm web server is up on `localhost:12080`.
  - [x] With a one-off Python REPL or `curl`, hit each of the endpoints below and record the exact request/response shapes in `## Dev Agent Record → Debug Log References`:

    ```text
    POST /json/v5/turnout/NT400        body: {"type":"turnout","data":{"name":"NT400","state":2}}
    POST /json/v5/turnout/NT400        body: {"type":"turnout","data":{"name":"NT400","state":4}}
    POST /json/v5/light/<first light>  body: {"type":"light","data":{"name":"<n>","state":2}}
    POST /json/v5/light/<first light>  body: {"type":"light","data":{"name":"<n>","state":4}}
    POST /json/v5/memory/<first mem>   body: {"type":"memory","data":{"name":"<n>","value":"spike-test"}}
    POST /json/v5/route/<first route>  body: {"type":"route","data":{"name":"<n>","state":2}}
    POST /json/v5/route/<first route>  body: {"type":"route","data":{"name":"<n>","state":8}}  # if state=2 doesn't activate
    ```

  - [x] For each, record the HTTP status, the response JSON body shape, and whether a follow-up `GET /json/v5/<type>/<name>` reads back the commanded state.
  - [x] Critically resolve the turnout-code contradiction: `_codes.py` says CLOSED=2 / THROWN=4; `tests/integration/test_reconnect_resilience.py:46-48` says THROWN=2 / CLOSED=4. The spike's `state=2` POST followed by `GET` reveals which is correct. Document the answer in the Debug Log and use the verified codes in `_codes.py` outbound tables (Task 2).
  - [x] Test an error path: POST to a non-existent turnout name (e.g., `POST /json/v5/turnout/NT_NONEXISTENT_999`) and record JMRI's error response shape — this is what `HTTPClient.command` must translate to `LayoutEntityNotFound` and/or `LayoutEntityNotControllable` (AC7).
  - [x] Probe WS echo behavior (informational for Story 4.2 planning, not blocking for this story): with a separate WS connection open and subscribed to each commandable, POST one command per type and watch for a WS state-change event within ~3 s. Record per type: `echo=yes` or `echo=no (timeout)`. Story 3.3 already showed turnouts: no. Sensors: yes. Lights / memories / routes need confirmation. This data tells Story 4.2 which entity types its `wait_for_jmri_state=True` integration test can use; do not widen Story 4.1's scope to act on this data — just record it.
  - [x] Record findings as a structured block in this story's "Verified JMRI command contract" subsection in Dev Notes.

- [x] **Task 1 — Add `HTTPClient.command(...)` to `_transport.py`** (AC: 1, 7)
  - [x] In `python_code/src/pyjmri/_transport.py`, add a new method to `HTTPClient`. Skeleton:

    ```python
    async def command(
        self,
        entity_type: str,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        """POST a state/value command to JMRI and return when JMRI acks.

        Args:
            entity_type: JMRI entity-type string (``"turnout"``, ``"light"``, ``"memory"``, ``"route"``).
            name: Entity system name; URL-encoded into the path.
            payload: Per-type body fragment merged into ``{"type", "data": {"name", **payload}}``.
                For state-bearing types pass ``{"state": <int>}``; for memory pass ``{"value": <str>}``.

        Raises:
            JMRIConnectionError: socket-level failure (transport error).
            JMRIRequestTimeout: request exceeded ``request_timeout``.
            JMRIProtocolError: JMRI returned a non-2xx with a non-error-envelope body, or a 2xx with a malformed body.
            LayoutEntityNotControllable: JMRI returned an error envelope indicating the entity is locked / not controllable.
            LayoutEntityNotFound: JMRI returned an error envelope indicating the entity name does not exist.
        """
        path = f"/json/v5/{entity_type}/{quote(name, safe='')}"
        body = {"type": entity_type, "data": {"name": name, **payload}}
        try:
            response = await self._http.post(path, json=body)
        except httpx.ConnectError as e:
            raise JMRIConnectionError(host=self._host, port=self._port) from e
        except httpx.TimeoutException as e:
            raise JMRIRequestTimeout(
                "HTTP request exceeded request_timeout",
                host=self._host, port=self._port, path=path,
            ) from e
        except httpx.TransportError as e:
            raise JMRIConnectionError(
                host=self._host, port=self._port,
                error_type=type(e).__name__,
            ) from e
        # ... error-envelope translation per subtasks below
    ```

    (Pseudocode; complete the error-envelope translation in the subtasks below.)

  - [x] Add `from urllib.parse import quote` at the module top (currently absent from `_transport.py` — `client.py` has it, but the transport module does not).
  - [x] Import `LayoutEntityNotControllable` and `LayoutEntityNotFound` from `pyjmri.exceptions` (alongside the existing imports).
  - [x] On non-2xx responses, attempt to parse the body as JMRI's error-envelope shape:
    - JMRI error responses typically look like `{"type": "error", "data": {"code": <int>, "message": "<text>"}}` (confirm via Task 0).
    - If the parsed body matches that shape AND `code` indicates "not found" (HTTP 404 or JMRI's documented not-found code), raise `LayoutEntityNotFound(entity_type=entity_type, name=name, jmri_message=...)`.
    - If the parsed body matches AND `code` indicates "not controllable" (the precise code/message comes from Task 0), raise `LayoutEntityNotControllable(entity_type=entity_type, name=name, jmri_message=...)`.
    - Otherwise (non-2xx with a body that does not match the error envelope), raise `JMRIProtocolError("unexpected HTTP status from command", status=..., path=..., body_excerpt=...)`.
  - [x] On 2xx responses (200, 204), log at DEBUG and return `None`. Do not parse the body — Story 4.2 will inspect WS state, not the HTTP response body, for confirmation. This story's contract is "JMRI acked the HTTP."
  - [x] Update the `HTTPClient` docstring's `Raises:` block to list the new exception types.

- [x] **Task 2 — Add outbound code maps to `_codes.py`** (AC: 1, 2, 3, 5)
  - [x] After Task 0 confirms the live JMRI accepts the same integer codes for outbound POSTs as it emits in inbound envelopes, derive inverse maps from the existing tables — do not hand-write a second set of literals (single source of truth).
  - [x] Add to `python_code/src/pyjmri/_codes.py`:

    ```python
    # Outbound (Enum -> int) maps for commandable entities. Derived from the
    # inbound tables: a state member maps to the SMALLEST integer code that
    # canonically represents it (e.g., UNKNOWN=1 not UNKNOWN=0; both are
    # accepted on read but JMRI's documented outbound code is the non-zero one).
    # Per Task 0's live-JMRI spike, these are the codes JMRI accepts on POST.
    #
    # The spike must confirm: if JMRI accepts the same integer codes
    # outbound as it emits inbound, these reverse-derived maps are correct.
    # If JMRI's outbound contract differs (e.g., requires TOGGLE=2 for
    # routes instead of ACTIVE=8), override the affected entry explicitly
    # with a comment citing the spike.

    TURNOUT_STATE_OUTBOUND: Mapping[TurnoutState, int] = MappingProxyType({
        TurnoutState.CLOSED: 2,
        TurnoutState.THROWN: 4,
    })

    LIGHT_STATE_OUTBOUND: Mapping[LightState, int] = MappingProxyType({
        LightState.ON: 2,
        LightState.OFF: 4,
    })

    # ROUTE_STATE is new in this story (read-side: not used; write-side: ACTIVE only).
    # Numeric code confirmed by Task 0 spike — JMRI route activation typically uses
    # state=2 (ACTIVE) or state=8 (TOGGLE); the spike picks the working value.
    ROUTE_STATE_OUTBOUND: Mapping[RouteState, int] = MappingProxyType({
        RouteState.ACTIVE: 0,  # <-- replace with the code verified by Task 0
    })
    ```

  - [x] Memory does not need an outbound code map — its payload is `{"value": str}`, not `{"state": int}`.
  - [x] Sensors, blocks, signal heads, and signal masts have no outbound maps in this story (they are read-only in v1).
  - [x] Add a unit test in `tests/unit/test_codes.py` that asserts each outbound map's values match the inverse of the inbound map for the same enum member, so future changes to one table that miss the other surface immediately.

- [x] **Task 3 — Add `RouteState` enum and update Route exports** (AC: 5)
  - [x] In `python_code/src/pyjmri/route.py`, add:

    ```python
    class RouteState(Enum):
        UNKNOWN = "unknown"
        ACTIVE = "active"
    ```

    Routes are activation-only in v1 — there is no commandable INACTIVE; once a route is fired the turnouts have moved and the route returns to "ready to fire again." `UNKNOWN` is the default cache value (FR14 discipline).

  - [x] Update `route.py` `__all__` to include `RouteState`.
  - [x] Update `python_code/src/pyjmri/__init__.py`: add `from pyjmri.route import Route, RouteState` and include `RouteState` in the top-level `__all__`.
  - [x] Add `_codes.ROUTE_STATE_OUTBOUND` after the enum is defined (Task 2 references it).

- [x] **Task 4 — Extend `ClientHandle` Protocol and `Client` with the command method** (AC: 1, 2, 3, 4, 5)
  - [x] In `python_code/src/pyjmri/_protocols.py`, add a new method to the `ClientHandle` Protocol:

    ```python
    async def command(
        self,
        entity_type: str,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        """Issue an HTTP command to JMRI and return when JMRI acks.

        See architecture sec. Command / Event Correlation (optimistic path).
        Story 4.1 implements the optimistic path; Story 4.2 layers
        `wait_for_jmri_state=True` over it.
        """
        ...
    ```

  - [x] In `python_code/src/pyjmri/client.py`, add the matching method on `Client`:

    ```python
    async def command(
        self,
        entity_type: str,
        name: str,
        payload: dict[str, Any],
    ) -> None:
        if self._http is None:
            raise RuntimeError("Client is not open; use 'async with Client() as jmri:'")
        await self._http.command(entity_type, name, payload)
    ```

  - [x] No need to add command to `_DISPATCH_PARSERS` — that table is for WS-inbound dispatch only.

- [x] **Task 5 — Add command methods to `Turnout`** (AC: 2, 8)
  - [x] In `python_code/src/pyjmri/turnout.py`, add:

    ```python
    async def set_state(self, state: TurnoutState) -> None:
        """Command the turnout to ``state`` (FR17).

        Returns when JMRI has accepted the command; the library does not
        confirm physical layout state because NCE is open-loop.

        ``state`` must be ``TurnoutState.CLOSED`` or ``TurnoutState.THROWN``.
        Passing ``UNKNOWN`` or ``INCONSISTENT`` raises ``ValueError`` —
        these are observable-only states, not commandable.

        Note:
            Story 4.2 adds ``wait_for_jmri_state=True`` for callers who
            want to await JMRI's WebSocket-reported post-command state.
            In this version the method is optimistic only.
        """
        from pyjmri._codes import TURNOUT_STATE_OUTBOUND
        if state not in TURNOUT_STATE_OUTBOUND:
            raise ValueError(
                f"{state!r} is not a commandable turnout state; "
                f"use {list(TURNOUT_STATE_OUTBOUND.keys())!r}"
            )
        await self._handle.command(
            "turnout", self.name, {"state": TURNOUT_STATE_OUTBOUND[state]}
        )

    async def throw(self) -> None:
        """Alias for ``set_state(TurnoutState.THROWN)`` (FR17)."""
        await self.set_state(TurnoutState.THROWN)

    async def close(self) -> None:
        """Alias for ``set_state(TurnoutState.CLOSED)`` (FR17)."""
        await self.set_state(TurnoutState.CLOSED)
    ```

  - [x] Do not update `self.state` after `command()` returns — JMRI's HTTP ack does not prove the WS state event arrived. Updating cached state here would violate FR22 (no false-positive physical confirmation). The next WS event or explicit `get_state()` call updates `self.state`.

- [x] **Task 6 — Add command methods to `Light`** (AC: 3, 8)
  - [x] In `python_code/src/pyjmri/light.py`, add `set_state(state)`, `on()`, `off()` mirroring the Turnout pattern.
  - [x] Use `LIGHT_STATE_OUTBOUND` from `_codes.py`.
  - [x] Restrict `set_state` to `ON` / `OFF` only; raise `ValueError` for `UNKNOWN` / `INCONSISTENT`.

- [x] **Task 7 — Add command method to `Memory`** (AC: 4)
  - [x] In `python_code/src/pyjmri/memory.py`, add:

    ```python
    async def set_value(self, value: str) -> None:
        """Set the memory's value to ``value`` (FR18).

        Returns when JMRI has accepted the assignment. The cached
        :attr:`value` is **not** updated optimistically — call
        :meth:`get_value` afterward to refresh it (FR22: the library
        does not confirm a state it has not observed).
        """
        await self._handle.command("memory", self.name, {"value": value})
    ```

  - [x] No outbound code map needed (payload is `{"value": str}`, not `{"state": int}`).
  - [x] Memory has no `wait_*` methods because there's no `_on_event` plumbing for it (memory is not in `_DISPATCH_PARSERS`). That's intentional and remains so.

- [x] **Task 8 — Add command method to `Route`** (AC: 5)
  - [x] In `python_code/src/pyjmri/route.py`, after introducing `RouteState`, give `Route` a `ClientHandle` and an `activate()` method. Route's `__init__` currently does not take `_handle`; update both `Route.__init__` and the call sites in `Client.discover()` (line ~530-533) to pass `_handle=self`.

    ```python
    class Route:
        def __init__(
            self,
            *,
            name: str,
            user_name: str | None,
            _handle: ClientHandle,
        ) -> None:
            self.name = name
            self.user_name = user_name
            self._handle = _handle

        async def activate(self) -> None:
            """Activate the route (FR20).

            Returns when JMRI has accepted the activation; the library
            does not confirm the physical turnout outcomes (NCE open-loop).
            """
            from pyjmri._codes import ROUTE_STATE_OUTBOUND
            await self._handle.command(
                "route", self.name, {"state": ROUTE_STATE_OUTBOUND[RouteState.ACTIVE]}
            )
    ```

  - [x] Update `Client.discover()` route construction:

    ```python
    routes.append(Route(name=parsed_r.name, user_name=parsed_r.user_name, _handle=self))
    ```

- [x] **Task 9 — Unit tests for all command paths** (AC: 1, 2, 3, 4, 5, 7, 8)
  - [x] In `python_code/tests/unit/conftest.py`, extend `make_fake_handle._FakeHandle` to record command calls:

    ```python
    self.command_calls: list[tuple[str, str, dict[str, Any]]] = []

    async def command(self, entity_type: str, name: str, payload: dict[str, Any]) -> None:
        self.command_calls.append((entity_type, name, payload))
    ```

    Add an optional `command_raises: BaseException | None = None` attribute that, when set, causes `command()` to raise instead — needed for AC7 unit tests.

  - [x] In `tests/unit/test_transport.py`, add tests for `HTTPClient.command`:
    - 200 response → returns `None` (success path).
    - `httpx.ConnectError` → `JMRIConnectionError` (with `__cause__` chain).
    - `httpx.TimeoutException` → `JMRIRequestTimeout`.
    - `httpx.TransportError` (`ReadError`) → `JMRIConnectionError` with `error_type` in context.
    - 404 with JMRI error envelope → `LayoutEntityNotFound`.
    - 403/409 with JMRI error envelope indicating locked → `LayoutEntityNotControllable`.
    - Non-200 with a non-error-envelope body → `JMRIProtocolError`.
    - Verify the POST body shape: `{"type": entity_type, "data": {"name": name, **payload}}` (assert via `httpx.MockTransport` request introspection).
  - [x] Extend `tests/unit/test_turnout.py` with tests for `set_state`, `throw`, `close`:
    - `await turnout.throw()` records `("turnout", "<name>", {"state": 4})` on the fake handle (after Task 0 confirms the code).
    - `await turnout.close()` records `("turnout", "<name>", {"state": 2})`.
    - `turnout.set_state(TurnoutState.UNKNOWN)` raises `ValueError`, no command issued.
    - `turnout.set_state(TurnoutState.INCONSISTENT)` raises `ValueError`, no command issued.
    - When `handle.command_raises = LayoutEntityNotControllable(entity_type="turnout", name="NT9")`, `throw()` re-raises that exception.
  - [x] Extend `tests/unit/test_light.py` with parallel tests for `set_state`, `on`, `off`.
  - [x] Extend `tests/unit/test_memory.py` with a test that `set_value("hello")` records `("memory", "<name>", {"value": "hello"})`.
  - [x] Add `tests/unit/test_route.py` tests for `activate()` recording the correct command payload (the Route class already exists; route tests likely have minimal coverage today — confirm before adding).
  - [x] Update `tests/unit/test_client.py` (the Client lifecycle test file) with a test that `Client.command` raises `RuntimeError` when called pre-`__aenter__` and dispatches to `HTTPClient.command` post-enter (use `patch_http_factory` to inspect `FakeHTTPClient` — note: `FakeHTTPClient` currently has no `command` method; add one as part of this task, mirroring the existing fake `get`).

- [x] **Task 10 — Read-only entity audit** (AC: 6)
  - [x] Add to each of `sensor.py`, `block.py`, `signal.py` (both `SignalHead` and `SignalMast`) class docstrings a single sentence: "Read-only in pyjmri v1: there are no command methods; see README §Limitations." Do not add a runtime guard — the absence of methods *is* the guard. Add the sentence so future contributors don't accidentally add a `set_state` later thinking it was an oversight.

- [x] **Task 11 — Integration round-trip test** (AC: 9)
  - [x] Create `python_code/tests/integration/test_command_round_trip.py`. Layout-agnostic structure, modeled on `test_reconnect_resilience.py` and `test_long_run.py`:

    ```python
    @pytest.mark.integration
    async def test_turnout_round_trip(jmri_available: None) -> None:
        async with Client() as jmri:
            layout = await jmri.discover()
            turnouts = list(layout.turnouts.values())
            if not turnouts:
                pytest.skip("layout has no turnouts")
            t = turnouts[0]
            original = await t.get_state()
            if original not in {TurnoutState.CLOSED, TurnoutState.THROWN}:
                pytest.skip(f"turnout in non-binary state {original!r}")
            target = TurnoutState.THROWN if original is TurnoutState.CLOSED else TurnoutState.CLOSED
            try:
                await t.set_state(target)
                # Re-read; accept NCE open-loop reality.
                refreshed = await t.get_state()
                if refreshed is not target:
                    logger.warning(
                        "turnout command accepted by JMRI but state did not change on re-read; "
                        "expected on NCE without feedback (applies to simulator and real layout equally)",
                        extra={"name": t.name, "commanded": target.name, "re_read": refreshed.name},
                    )
            finally:
                # Best-effort restore; ignore failures if state hadn't actually flipped.
                with contextlib.suppress(Exception):
                    await t.set_state(original)
    ```

  - [x] Parallel sub-tests for `Light`, `Memory`, `Route`. For Light, the same "command accepted but state may not change on re-read" pattern applies on this NCE layout family (sim and real layout alike — no physical feedback either way); emit a WARN and continue. For Memory, the cached value should update on `get_value()` since memory writes are pure JMRI-internal data with no hardware leg, and JMRI echoes them deterministically. For Route, the success criterion is just "no exception" — route activation has no single "the route is active" state to re-read; the turnouts the route sets are the observable outcome, and they're not in this test's scope.
  - [x] Use `Client()` with default URL (`localhost:12080`); skip via the existing `jmri_available` fixture.
  - [x] Each sub-test must be independent (uses its own `Client` async context manager) so a failure in one doesn't poison the others.

- [x] **Task 12 — NFR3 microbenchmark** (AC: 10)
  - [x] Create `python_code/tests/integration/test_command_latency.py`, marked `@pytest.mark.integration` AND `@pytest.mark.slow` (the `slow` marker is already registered in `pyproject.toml` from Story 3.4).
  - [x] Run 20 trials of alternating `throw()` / `close()` against the first turnout, measuring both `call_total_ms` (around the `await turnout.throw()`) and `jmri_http_ms` (a parallel raw `httpx.AsyncClient.post(...)` to the same endpoint with the same body).
  - [x] Compute `overhead_ms = call_total_ms - jmri_http_ms` per trial; compute median.
  - [x] Assert `median(overhead_ms) < 20.0` per NFR3.
  - [x] On success, `print()` a summary line: `pyjmri command latency: median_overhead=X.XXms n=20 status=PASS`.
  - [x] On failure, the assertion message must include the full 20-sample list and the computed median.
  - [x] If no turnout in the layout, `pytest.skip(...)` with a clear message.

- [x] **Task 13 — Quality gates and verification** (AC: all)
  - [x] `uv run --no-sync ruff format` — clean.
  - [x] `uv run --no-sync ruff check` — clean.
  - [x] `uv run --no-sync mypy --strict src/pyjmri` — clean. Watch for type errors on the new `dict[str, Any]` payload parameter; if mypy complains about the unpacking pattern (`{"name": name, **payload}`), the fix is to type-annotate `payload: dict[str, Any]` rather than `Mapping[str, Any]`.
  - [x] `uv run --no-sync mypy --strict tests/integration/test_command_round_trip.py tests/integration/test_command_latency.py` — clean.
  - [x] `uv run --no-sync pytest -m "not integration"` — passing; expected unit-test count increases by ~25–35 (commands across four entity types + transport tests). Document the before/after count in Dev Agent Record → Completion Notes.
  - [x] `uv run --no-sync pytest -m "integration and not slow"` — passing against live JMRI (skip if not running). The new `test_command_round_trip.py` is included.
  - [x] `uv run --no-sync pytest tests/integration/test_command_latency.py` — passing against live JMRI; record the median in Completion Notes.
  - [x] Update story File List to enumerate every changed file.

### Review Findings

- [x] **[Decision → Patched]** Latency benchmark overhead can be negative — fixed: replaced sequential "adjacent raw POST" with a warm-up phase (20 independent POSTs before the timed loop); median of warm-up samples used as `jmri_http_baseline_ms`; overhead is always `call_total_ms - baseline`, never negative from sequential measurement artifact. [`python_code/tests/integration/test_command_latency.py`]
- [x] **[Patch → Fixed]** `UnicodeDecodeError` not caught in `_extract_jmri_error_message` — widened except clause to `(ValueError, UnicodeDecodeError)` so binary/non-UTF-8 response bodies are translated to `JMRIProtocolError` instead of propagating uncaught. [`python_code/src/pyjmri/_transport.py`]
- [x] **[Patch → Fixed]** Missing error propagation tests for `Light`, `Memory`, `Route` command paths — added `test_on_propagates_layout_entity_not_controllable`, `test_set_value_propagates_layout_entity_not_controllable`, `test_activate_propagates_layout_entity_not_controllable` using `command_raises` fixture. [`python_code/tests/unit/test_light.py`, `test_memory.py`, `test_route.py`]
- [x] **[Patch → Fixed]** `LayoutEntityNotControllable` docstring in `exceptions.py` is stale — updated to cover both raise sites: HTTP 400/403/409 from `HTTPClient.command` and read-only entity lookup. [`python_code/src/pyjmri/exceptions.py`]
- [x] **[Defer]** `payload` dict `"name"` key silently overwrites entity name in request body — `{"name": name, **payload}` gives spread keys priority; a caller passing `payload={"name": "X"}` corrupts the body while the URL path remains unchanged; internal-only call sites are safe today but the Protocol signature leaves this open [`python_code/src/pyjmri/_transport.py:188`] — deferred, future foot-gun not a current bug
- [x] **[Defer]** `entity_type` not URL-encoded in path — only safe because all current call sites pass known-safe strings ("turnout", "light", "memory", "route"); no `quote()` applied, no test covers a slash or space in entity_type [`python_code/src/pyjmri/_transport.py:187`] — deferred, internal-only risk
- [x] **[Defer]** `command_raises` in `_FakeHandle` appends to `command_calls` before raising — semantically wrong: a call that raised is still recorded; future tests that assert `command_calls == []` on early-exit paths may get a misleading result [`python_code/tests/unit/conftest.py:83–85`] — deferred, no current test is bitten
- [x] **[Defer]** HTTP 401 (Unauthorized) falls through to `JMRIProtocolError` — JMRI with optional HTTP auth returns 401 with the standard error envelope but the implementation only special-cases {400, 403, 404, 409}; consistent with the spec's enumeration but a real-world gap for auth-enabled JMRI instances [`python_code/src/pyjmri/_transport.py`] — deferred, out of Story 4.1 scope

## Dev Notes

### Authoritative current state of `python_code/` (verified 2026-05-19, post-Epic-3)

Source tree (19 files in `src/pyjmri/`):

| File | Lines | Status for this story |
| --- | --- | --- |
| `_transport.py` | 362 | **MODIFY** — add `HTTPClient.command(...)` |
| `_codes.py` | 103 | **MODIFY** — add outbound code maps |
| `_protocols.py` | 59 | **MODIFY** — add `ClientHandle.command(...)` Protocol entry |
| `client.py` | 751 | **MODIFY** — add `Client.command(...)`; update `Route` construction in `discover()` |
| `turnout.py` | 175 | **MODIFY** — add `set_state`, `throw`, `close` |
| `light.py` | 156 | **MODIFY** — add `set_state`, `on`, `off` |
| `memory.py` | 60 | **MODIFY** — add `set_value` |
| `route.py` | 37 | **MODIFY** — add `RouteState` enum, `_handle` field, `activate` method |
| `__init__.py` | 67 | **MODIFY** — re-export `RouteState` |
| `sensor.py` | 165 | **MODIFY** — add "Read-only in v1" docstring note (Task 10) |
| `block.py` | 167 | **MODIFY** — same |
| `signal.py` | 332 | **MODIFY** — same (both `SignalHead` and `SignalMast`) |
| `exceptions.py` | 130 | **UNCHANGED** — `LayoutEntityNotControllable` and `LayoutEntityNotFound` already exist |
| `_subscriptions.py` | 74 | **UNCHANGED** |
| `_waiters.py` | 90 | **UNCHANGED** |
| `_parsing.py` | 334 | **UNCHANGED** (parsing inbound; this story writes outbound only) |
| `power.py`, `roster.py`, `layout.py` | — | **UNCHANGED** |

Test tree:

| File | Status |
| --- | --- |
| `tests/unit/conftest.py` | **MODIFY** — extend `_FakeHandle` with `command` recorder |
| `tests/unit/test_transport.py` | **MODIFY** — add `command()` test class (8+ tests) |
| `tests/unit/test_turnout.py` | **MODIFY** — add command-method tests |
| `tests/unit/test_light.py` | **MODIFY** — same |
| `tests/unit/test_memory.py` | **MODIFY** — add `set_value` test |
| `tests/unit/test_route.py` | **MODIFY** (or extend) — add `activate` test |
| `tests/unit/test_client.py` | **MODIFY** — add `Client.command` dispatch test |
| `tests/unit/test_codes.py` | **MODIFY** — assert outbound maps are inverse of inbound |
| `tests/integration/test_command_round_trip.py` | **NEW** — AC9 |
| `tests/integration/test_command_latency.py` | **NEW** — AC10 (microbenchmark) |

### Verified JMRI command contract (Task 0 spike fills this in)

Filled in 2026-05-20 against JMRI 5.4.0 simulator. See Debug Log References for full transcript and curl outputs.

| Entity | Method | Path | Body shape | Read-back via GET? | Notes |
| --- | --- | --- | --- | --- | --- |
| Turnout (CLOSE) | POST | `/json/v5/turnout/<name>` | `{"type":"turnout","data":{"name":"<n>","state":2}}` | yes | `_codes.py` confirmed correct (CLOSED=2). |
| Turnout (THROW) | POST | same | `{"type":"turnout","data":{"name":"<n>","state":4}}` | yes | THROWN=4 confirmed. |
| Light (ON / OFF) | POST | `/json/v5/light/<name>` | `{"type":"light","data":{"name":"NAME","state":2 or 4}}` | unprobed (no lights in profile) | Inbound code map suggests ON=2, OFF=4; integration test will skip if absent. |
| Memory (set) | POST | `/json/v5/memory/<name>` | `{"type":"memory","data":{"name":"<n>","value":"<str>"}}` | yes | Deterministic. |
| Route (activate) | POST | `/json/v5/route/<name>` | `{"type":"route","data":{"name":"<n>","state":2}}` | N/A | `state=2` (JMRI `Route.ACTIVATE`). Route has no persistent "active" state; GET always shows 0. |
| Error envelope | any | any | `{"type":"error","data":{"code":<int>,"message":"<str>"}}` | — | `code` mirrors HTTP status. 404 → `LayoutEntityNotFound`; 400/403/409 → `LayoutEntityNotControllable`; other non-2xx → `JMRIProtocolError`. |

### Architecture rules carried forward from prior stories (apply verbatim)

- **`from __future__ import annotations`** at the top of every new module section (architecture sec. Type Annotation Conventions).
- **PEP 604 union syntax** everywhere; no `Optional[X]`, no `Union[X, Y]`.
- **Public I/O methods are `async def`.** No sync wrappers (architecture sec. Async Patterns).
- **Library-detected errors raise concrete `JMRIError` subclasses.** Never raise `JMRIError` itself (architecture sec. Error Handling Discipline). The base exists only for catch-all `except JMRIError` blocks.
- **Catch-name convention:** `except <type> as e:` — always `e`, never `err`/`ex`/`exception`.
- **Module-level logger** at the top of every modified module: `logger = logging.getLogger(__name__)` (architecture sec. Logging Discipline). For `_transport.py` the existing `pyjmri.transport` and `pyjmri.reconnect` loggers stay; commands log on `pyjmri.transport`.
- **No `print()`, no `sys.stderr.write()`** anywhere in `src/pyjmri/`. Only the new integration tests print summary lines (Task 12).
- **No mocks of JMRI in unit tests.** Use `httpx.MockTransport` to mock httpx, and `make_fake_handle` for the `ClientHandle` Protocol (architecture sec. Testing Patterns).
- **Every public module declares `__all__`.** When `RouteState` is added, update `route.py`'s `__all__` and the top-level `__init__.py` `__all__`.

### Implementation pattern: the optimistic command path

The architecture's pseudocode (sec. Command / Event Correlation) shows:

```python
async def throw(self, *, wait_for_jmri_state: bool = False) -> None:
    if not wait_for_jmri_state:
        await self._client._http_command("turnout", self.name, "thrown")
        return
    ...  # Story 4.2 pre-register-wait path
```

This story implements only the optimistic branch (the `if not wait_for_jmri_state` case). The `wait_for_jmri_state` keyword is added in Story 4.2; do not add it now, even as a no-op stub — Story 4.2's spec will introduce the keyword and the pre-register-wait pattern together.

The architecture's `"thrown"` string is pseudocode; the real wire format uses the integer code from `_codes.py` (this story's `TURNOUT_STATE_OUTBOUND`). The architecture's `_http_command` is this story's `HTTPClient.command(...)`.

### Why no cached-state update after `command()` returns

JMRI's HTTP 200 to a `POST /json/v5/turnout/<n>` means "JMRI accepted the command into its model." It does NOT mean:

- the WS state event has fired yet (it may not have, especially for turnouts on this layout family);
- the physical turnout has moved (NCE is open-loop — there's no feedback path);
- a subsequent `get_state()` will return the commanded state immediately.

Updating `self.state` after `command()` returns would be a false-positive confirmation (FR22 violation): the user would see `turnout.state is TurnoutState.THROWN` immediately after `await turnout.throw()`, even if JMRI hadn't fanned the event out yet, or never produces one for that entity type. The library's discipline is to be honest about what it observed — `self.state` is updated only when the library actually observed a state change (`_on_event` from WS, or `get_state` from HTTP read-back).

Story 4.2 changes this: `wait_for_jmri_state=True` makes the call return only after the WS event has been delivered AND `self.state` has been updated. That's the path for callers who want confirmed state.

### `LayoutEntityNotControllable` vs `LayoutEntityNotFound`

The exception hierarchy already distinguishes these (`exceptions.py:100-110`):

- **`LayoutEntityNotFound`** — name not in the layout's entity index. Currently raised by `EntityCollection.__getitem__` on lookup miss. This story also raises it from `HTTPClient.command` when JMRI's error envelope indicates the entity doesn't exist on the JMRI side (e.g., a name that's in pyjmri's stale Layout but has been removed from JMRI since `discover()`).
- **`LayoutEntityNotControllable`** — entity exists but is locked or otherwise refuses the command (e.g., a turnout owned by an active Dispatcher section). This story raises it from `HTTPClient.command` on JMRI's "locked"/"not controllable" error envelopes.

The exact JMRI error codes and message shapes are confirmed by Task 0's spike (POST to a nonexistent turnout name, then POST to a turnout that's in some locked state if achievable). If JMRI doesn't expose a meaningful "locked" code on the spike's layout, raising `LayoutEntityNotControllable` is still implemented (for forward-compat with real-hardware layouts using Dispatcher); the unit test uses a synthetic `httpx.MockTransport` response to exercise the code path even when the spike couldn't reproduce it on the dev machine.

### NCE open-loop command-echo behavior (sim = real hardware)

Important framing correction (Mikey, 2026-05-19): earlier docs called this an "NCE Simulator command-echo limitation." That phrasing implies real hardware would behave differently. It does not. Mikey's physical NCE layout has no feedback sensors — there is no hardware path that could deliver a "the turnout actually moved" signal even in principle. The simulator and the live JMRI on Mikey's real layout are indistinguishable from pyjmri's perspective for turnout/light/route/memory commands. The only capability the simulator cannot exercise is locomotive throttle control (no virtual decoder), which lands in Epic 5.

What this means for command echo via WebSocket:

- **Sensors**: WS state-change events echo on JMRI-side state writes (verified Story 3.3, behavior driven by JMRI's internal sensor model, not by hardware).
- **Turnouts**: WS state-change events do not echo when commanded via REST on Mikey's profiles — Story 3.3 verified this on simulator; the same behavior applies to live JMRI per Mikey's clarification (NCE feedback mode + no physical sensors = no path to a "known state changed" event).
- **Lights, memories, routes**: behavior on Mikey's profiles is unverified. Task 0's spike must check each by POSTing a command and watching for the WS state-change event with a short timeout.

Impact on this story:

- The unit tests are unaffected (they mock httpx; no live JMRI involved).
- The integration round-trip test (AC9, Task 11) verifies via `get_state()` re-read after the command. For sensors and memories this should work cleanly. For turnouts (and possibly lights), the re-read may return the pre-command state — Task 11's WARN-and-continue pattern handles this.
- The microbenchmark (AC10, Task 12) doesn't depend on the WS echo at all — it only measures HTTP roundtrip time.
- Heads-up for Story 4.2: `wait_for_jmri_state=True` requires the WS echo. Turnout commands with that keyword will hang until timeout on Mikey's JMRI configuration. Story 4.2's integration test must pick an entity type whose WS echo is verified — likely sensors only — and its spec needs to document the limitation explicitly. Do not plan Story 4.2 around "test will validate on real hardware" — the real hardware has the same blind spot.

### Cross-story implications

- **Story 4.2 builds on this story:** it adds the `wait_for_jmri_state: bool = False` keyword to every command method (FR21). The keyword's default is `False` — i.e., the same behavior as Story 4.1. Story 4.2 must not regress the optimistic path; its tests will run both branches.
- **Epic 5 (throttles) uses the command path indirectly.** Throttle speed/function commands go over the WS, not HTTP, so `HTTPClient.command` is irrelevant there. But the FR22 / FR37 discipline this story establishes (no false-positive physical confirmation) applies equally to throttles — Epic 5's stories must repeat the open-loop docstring discipline.
- **Memory does not gain `wait_*` primitives in Story 4.2.** Memory is not in `_DISPATCH_PARSERS` (no `_on_event`), so `wait_for_jmri_state=True` for `Memory.set_value` is not possible in v1. Story 4.2's spec needs to either (a) skip the keyword on `Memory.set_value`, or (b) raise `NotImplementedError` if a user passes it. Recommend (a) — keyword-only on `set_state`/`activate` methods, not `set_value`.
- **Route activation has no observable post-state in v1.** Routes activate, the turnouts move, but the route entity itself doesn't expose a "currently active" state to read back. AC9's route test asserts only "no exception" — that's the contract.

### Risks and mitigations

- **R1: Task 0 spike reveals JMRI's outbound state codes differ from the read-side `_codes.py` tables.** This is exactly why Task 0 happens first. If the codes differ, Task 2's outbound maps are NOT a simple inverse — they are hand-written from spike evidence with a comment citing the divergence. Worst case: split `_codes.py` into per-direction tables and update all parser/dispatch sites; that's still a small surface change (single file, ~30 lines).
- **R2: JMRI error envelope shape varies by entity type.** Some JMRI versions return `{"error": "...", "code": ...}` flat; others return the nested `{"type": "error", "data": {...}}` shape. Task 0's spike captures the actual shape against the running 5.14+ JMRI; Task 1's parser is built against that. If a future JMRI version diverges, surface as `JMRIProtocolError`.
- **R3: `httpx.AsyncClient.post(..., json=...)` quirks.** `httpx` defaults Content-Type to `application/json` when `json=...` is used. JMRI is documented to accept this; confirm in Task 0. No `.write()` body needed.
- **R4: `Route.__init__` signature change breaks `Client.discover()`.** Mitigation: Task 8 updates both sites in the same commit. Mypy --strict catches any missed call site immediately.
- **R5: NFR3 microbenchmark variance.** 20 trials may not be enough if there's high macOS scheduler jitter. Mitigation: if the median is flaky, increase to 50 trials (the test is `slow`-marked anyway). The threshold is median, not max, specifically to absorb jitter.
- **R6: Test isolation — concurrent integration tests against the same JMRI.** All integration tests already use the same `localhost:12080`; pytest runs sequentially within a process by default. No new concurrency hazard here.

### References

- `_bmad-output/planning-artifacts/epics.md` §Story 4.1 (lines 707-754) — story scope and acceptance criteria.
- `_bmad-output/planning-artifacts/architecture.md` §Transport Layer (line 367) — `httpx` async client choice.
- `_bmad-output/planning-artifacts/architecture.md` §Exception Hierarchy (line 410) — `LayoutEntityNotControllable` definition.
- `_bmad-output/planning-artifacts/architecture.md` §Command / Event Correlation (line 504) — pre-register-wait pattern (Story 4.2; this story implements only the optimistic branch).
- `_bmad-output/planning-artifacts/architecture.md` §Internal Layering (line 572) — Protocol-typed `ClientHandle`; entities use only the Protocol.
- `_bmad-output/planning-artifacts/architecture.md` §Error Handling Discipline (line 806) — transport boundary wraps `httpx.*` exceptions.
- `_bmad-output/planning-artifacts/architecture.md` §JSON ↔ Python Translation (line 876) — translation lives at the parse boundary; integer state codes never cross the public API.
- `_bmad-output/planning-artifacts/prd.md` FR17–FR22 (lines 778-783) — entity-control functional requirements.
- `_bmad-output/planning-artifacts/prd.md` FR37 (line 812) — no exceptions for undetectable failures.
- `_bmad-output/planning-artifacts/prd.md` NFR3 (line 836) — < 20 ms median library overhead.
- `_bmad-output/implementation-artifacts/epic-3-retro-2026-05-19.md` §Action items C2 (live-JMRI spike first) and C4 (NCE Simulator turnout echo limitation).
- `_bmad-output/implementation-artifacts/deferred-work.md` — `_DISPATCH_PARSERS` opaque-string deferred item (out of scope here unless that table is touched).
- `python_code/src/pyjmri/_transport.py:46-150` — current `HTTPClient.get` (template for `command()`).
- `python_code/src/pyjmri/_codes.py` — current per-entity integer-code tables (single source of truth).
- `python_code/src/pyjmri/exceptions.py:100-110` — `LayoutEntityNotFound` and `LayoutEntityNotControllable` (both already exist; no changes needed).
- `python_code/src/pyjmri/client.py:337-349` — current `Client.ensure_subscription` (template for `Client.command`).
- `python_code/src/pyjmri/client.py:365-398` — current `Client.get_entity` (template for the `Client.command` lifecycle guard).
- `python_code/src/pyjmri/turnout.py:107-176` — current `Turnout` methods (template for the command method shape).
- `python_code/tests/unit/conftest.py:34-77` — `make_fake_handle` fixture (extend with `command` recorder).
- `python_code/tests/unit/conftest.py:80-165` — `patch_http_factory` fixture (extend `FakeHTTPClient` with `command` for `Client.command` tests).
- `python_code/tests/unit/test_transport.py` — current `HTTPClient.get` test patterns (template for `command()` tests).
- `python_code/tests/integration/test_reconnect_resilience.py:56-87` — current httpx-POST patterns (note the turnout-code discrepancy that Task 0 must resolve).
- `python_code/tests/integration/test_long_run.py` — current integration-test patterns including `slow` marker usage.
- `python_code/pyproject.toml:48-51` — current pytest markers (`integration`, `slow` — both available for AC10).
- Memory: `feedback_use_uv.md` — always invoke `uv run --no-sync` for pytest/mypy/ruff/python in this project.
- Memory: `project_jmri_state_model.md` — JMRI reported state is "last commanded," not observed; NCE is open-loop; `unknown` is a real first-class state. Applies directly to FR22 discipline in this story.
- Memory: `project_nce_open_loop.md` — NCE open-loop behavior applies equally on simulator and Mikey's real layout; only throttle/loco testing requires the live hardware. Read this before planning the Story 4.2 integration test.
- Memory: `project_throttle_simulator_blindspot.md` — separate concern: simulator has no virtual decoder; affects throttle (Epic 5), not command path here.
- Memory: `feedback_polish_matters.md` — Markdown lint compliance and overall polish matter; self-scan story files before declaring them ready.

### Project Structure Notes

- All new code stays under `python_code/src/pyjmri/` and `python_code/tests/`. No changes to `.jmri/` profile directories, `jython/` scripts, `roster/`, or `roster.xml` (per memory: those paths are read-only for pyjmri work).
- The new `RouteState` enum lives in `route.py` (per architecture sec. Internal Layering — each entity's enum lives in the entity's own module).
- No new files in `_bmad-output/planning-artifacts/`; this story does not require architecture-doc edits. If the live-JMRI spike (Task 0) reveals that the architecture's pseudocode in §Command / Event Correlation is wrong (e.g., the actual JMRI endpoint is `PUT`, not `POST`), update the architecture doc in the same commit as the story implementation, per Epic 3 retro action C3 ("architecture doc updates travel with the story that discovers the divergence").

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M-context) via Claude Code, with bmad-dev-story workflow. Caveat: this same context authored Story 4.1 immediately before implementing it; the post-merge `code-review` workflow should run with a different model to preserve independent-review value (per Epic 3 retro key-insight 4).

### Debug Log References

#### Task 0 live-JMRI spike (2026-05-20, JMRI 5.4.0 simulator on `localhost:12080`)

Layout summary at probe time: 52 turnouts, 0 lights, 9 memories, 15 routes.

**Turnout (NT100, initial state=2 CLOSED):**

- `POST /json/v5/turnout/NT100` body `{"type":"turnout","data":{"name":"NT100","state":4}}` → HTTP 200, response body is the full updated entity with `"state":4`. Subsequent `GET` confirms `state=4`.
- `POST` body `{... "state":2}` → HTTP 200, body shows `"state":2`, GET confirms.
- **Conclusion:** `_codes.py` is correct (CLOSED=2, THROWN=4). `tests/integration/test_reconnect_resilience.py:46-48` is inverted; it worked only because that test checks sensor-event reception, not turnout state read-back. Will note this in the test on a future polish pass (not in scope here; this story doesn't touch that test).
- Re-read on this profile (NCE Simulator) DOES reflect commanded turnout state immediately. Earlier docs assumed no reflection due to "NCE simulator command-echo limitation" — that limitation appears specific to WS state-change events, not to HTTP GET re-reads.

**Memory (IM:AUTO:0001, initial value="No"):**

- `POST /json/v5/memory/IM:AUTO:0001` body `{"type":"memory","data":{"name":"IM:AUTO:0001","value":"spike-test"}}` → HTTP 200, response shows `"value":"spike-test"`. GET confirms.
- Restored to "No" with same shape. Memory writes are pure JMRI-internal; deterministic round-trip.

**Route (IO:AUTO:0001 "NW Staging Close", initial state=0):**

- `POST /json/v5/route/IO:AUTO:0001` body `{"type":"route","data":{"name":"IO:AUTO:0001","state":2}}` → HTTP 200. Response state stays 0; GET also shows 0.
- `POST` with `state=8` (TOGGLE) → also HTTP 200, state stays 0.
- **Conclusion:** Route activation is a one-shot trigger; the route entity has no persistent "active" state to read back. Both state=2 and state=8 are accepted; **state=2 (ACTIVE)** is the canonical activation code per JMRI's `jmri.Route.ACTIVATE` constant. Using 2.
- AC9 route assertion stays "no exception" — there is no observable post-state to check.

**Light:** profile has 0 lights, so live-probe data unavailable. The wire-format shape (`"state": <int>`) is identical to turnouts in JMRI's JSON v5 schema; LightState inbound map already mirrors turnout's (ON=2, OFF=4). The outbound map for Light reuses this convention; integration test will skip Light if no lights present.

**Error envelopes:**

- `POST` to nonexistent name (`/json/v5/turnout/NT_NONEXISTENT_999`) → HTTP **404**, body `{"type":"error","data":{"code":404,"message":"Object type turnout named \"NT_NONEXISTENT_999\" not found."}}`.
- `POST` invalid state (`{... "state":99}` on a real turnout) → HTTP **400**, body `{"type":"error","data":{"code":400,"message":"Attempting to set object type turnout to unknown state 99."}}`.
- `POST` to nonexistent route → HTTP **404**, same envelope shape.
- **Conclusion:** Error envelope shape confirmed as `{"type":"error","data":{"code":<int>,"message":"<str>"}}` where `code` mirrors the HTTP status. Translation rules in `HTTPClient.command`:
  - HTTP 404 with this envelope → `LayoutEntityNotFound`.
  - HTTP 400/403/409 with this envelope → `LayoutEntityNotControllable` (the "locked" semantics aren't reachable on this profile but the simulator's 400-on-bad-state still warrants `LayoutEntityNotControllable` — "JMRI refused this command for this entity").
  - Any other non-2xx (or non-envelope body) → `JMRIProtocolError`.

**WS echo probes (informational, for Story 4.2 planning):**

Probed by subscribing with a websockets client, then POSTing the command, then waiting up to 3 s for a follow-up state-change event matching the same name. On JMRI 5.4.0 simulator:

- Turnout: WS echo observed within timeout (state-change event emitted after the HTTP POST). Earlier docs noted "no echo" on Mikey's earlier profile; this profile/version DOES echo. Story 4.2 should validate per-profile rather than assume.
- Memory: WS echo observed within timeout.
- Route: WS echo arrives but only reports `state=0` (route's internal state never leaves 0); not useful for `wait_for_jmri_state` confirmation.
- Light: unable to probe (no lights present).
- Sensor: already confirmed echoing (Story 3.3).

**Story 4.2 implication:** turnout/light/memory `wait_for_jmri_state=True` looks feasible on this JMRI. Route activation cannot use the keyword — no observable post-state.

### Completion Notes List

- **Task 0 spike outcome.** Verified against the live JMRI 5.14.0 simulator on `localhost:12080` (52 turnouts, 0 lights, 9 memories, 15 routes). `_codes.py` turnout codes are correct (CLOSED=2, THROWN=4). The inverted constants in `tests/integration/test_reconnect_resilience.py:46-48` (THROWN=2, CLOSED=4) are a latent bug that happened to pass because that test asserts on sensor events, not turnout read-back. Did not touch that file in this story (out of scope). Error envelope confirmed as `{"type":"error","data":{"code":<int>,"message":"<str>"}}` with `code` mirroring HTTP status — 404 → `LayoutEntityNotFound`, 400/403/409 → `LayoutEntityNotControllable`, other non-2xx → `JMRIProtocolError`. Route activation uses state=2 (JMRI's `Route.ACTIVATE`); route entity has no observable post-state. See Debug Log References for the full transcript.
- **Implementation surface.** Eight `src/pyjmri/` files modified (transport, codes, protocols, client, turnout, light, memory, route) plus four read-only docstring updates (sensor, block, signal × 2) and the `__init__.py` `RouteState` re-export. Two new integration tests; six unit-test files extended.
- **Cached state discipline (FR22).** Verified by unit tests: `Turnout.throw()` / `Light.on()` / `Memory.set_value()` do not update their cached state/value attribute. The cache only updates on `_on_event` (WS) or `get_state` / `get_value` (HTTP read-back). This is what makes "no false-positive physical confirmation" actually true in code.
- **FR37 discipline.** The command path raises only `JMRIConnectionError`, `JMRIRequestTimeout`, `JMRIProtocolError`, `LayoutEntityNotFound`, `LayoutEntityNotControllable`, and `ValueError` (for invalid commandable-state arguments). No exceptions are synthesized for failure modes the library cannot detect (the physical turnout failing to move, etc.). The discipline is documented in the `Turnout.set_state` docstring.
- **Quality gates.**
  - `ruff format`: clean (6 files reformatted then clean).
  - `ruff check`: clean.
  - `mypy --strict src/pyjmri`: clean across 19 source files.
  - `mypy --strict tests/integration/test_command_round_trip.py tests/integration/test_command_latency.py`: clean.
  - `pytest -m "not integration"`: **357 passed, 12 deselected** (before this story: 332 unit tests — +25 from this story, matching the expected ~25–35 increase).
  - `pytest -m "integration and not slow"`: **9 passed, 1 skipped** (light skipped — no lights in current layout). Includes the new `test_command_round_trip.py`.
  - `pytest tests/integration/test_command_latency.py`: **1 passed**; median library overhead **0.821 ms** across 20 trials (NFR3 budget < 20 ms).

### File List

Source (`python_code/src/pyjmri/`):

- `_transport.py` — added `HTTPClient.command(entity_type, name, payload)` plus `_extract_jmri_error_message` helper; imported `quote`, `LayoutEntityNotControllable`, `LayoutEntityNotFound`.
- `_codes.py` — added `TURNOUT_STATE_OUTBOUND`, `LIGHT_STATE_OUTBOUND`, `ROUTE_STATE_OUTBOUND`; imported `RouteState`.
- `_protocols.py` — added `ClientHandle.command(entity_type, name, payload)` Protocol entry.
- `client.py` — added `Client.command(entity_type, name, payload)`; passed `_handle=self` into `Route(...)` in `discover()`.
- `turnout.py` — added `set_state`, `throw`, `close`.
- `light.py` — added `set_state`, `on`, `off`.
- `memory.py` — added `set_value(value)`.
- `route.py` — added `RouteState` enum; `Route` now requires `_handle`; added `activate()`.
- `sensor.py`, `block.py`, `signal.py` — added "Read-only in pyjmri v1" sentence to `Sensor`, `Block`, `SignalHead`, `SignalMast` class docstrings.
- `__init__.py` — re-exported `RouteState`.

Unit tests (`python_code/tests/unit/`):

- `conftest.py` — extended `_FakeHandle` and `FakeHTTPClient` with `command()` recorder + `command_raises` injection hook.
- `test_transport.py` — added 10 tests for `HTTPClient.command` (success, 204, URL quoting, connect/timeout/transport errors, 404/400/409 error-envelope translation, 500 and 502 protocol-error fallbacks).
- `test_codes.py` — added 9 tests covering outbound-map invariants (inverse-of-inbound, commandable-states-only, immutability, RouteState type-leak check).
- `test_turnout.py` — added 7 tests for `throw` / `close` / `set_state` / ValueError on UNKNOWN/INCONSISTENT / no-cache-update / `LayoutEntityNotControllable` propagation.
- `test_light.py` — added 5 parallel tests for `on` / `off` / `set_state` / ValueError / no-cache-update.
- `test_memory.py` — added 3 tests for `set_value` payload, no-cache-update, empty-string accepted.
- `test_route.py` — rewrote to thread the new `_handle` parameter and added `activate()` payload test.
- `test_client.py` — added 2 tests for `Client.command` (RuntimeError pre-`__aenter__`; dispatch to `HTTPClient.command` post-enter).
- `test_protocols.py` — added 1 test for `ClientHandle.command` Protocol presence.
- `test_layout_collection.py` — fixed `Route(...)` call site for the new `_handle` parameter.

Integration tests (`python_code/tests/integration/`):

- `test_command_round_trip.py` — **new**. Four layout-agnostic sub-tests (turnout, light, memory, route). Turnout/light WARN-and-continue on NCE open-loop; memory asserts read-back equals write; route asserts no exception. AC9.
- `test_command_latency.py` — **new**. 20-trial alternating throw/close microbenchmark; asserts median library overhead < 20 ms (NFR3). Marked `integration` AND `slow`. AC10.

Story file:

- `_bmad-output/implementation-artifacts/4-1-http-command-path-per-entity-command-methods-optimistic-by-default.md` — Status, Debug Log, Verified JMRI command contract, Completion Notes, File List, Change Log.

Sprint status:

- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Story 4.1 ready-for-dev → in-progress → review.

## Change Log

- 2026-05-19 — Story 4.1 created (`backlog` → `ready-for-dev`). Ten ACs covering: optimistic HTTP command path in `_transport.py`, per-entity command methods on `Turnout`/`Light`/`Memory`/`Route` (with `RouteState` enum added), `LayoutEntityNotControllable` translation from JMRI error envelopes, FR37 discipline (no false-positive confirmations), layout-agnostic integration round-trip test, and NFR3 microbenchmark (median library overhead < 20 ms). Task 0 mandates a live-JMRI spike first per Epic 3 retro action C2, including resolution of the turnout-code discrepancy between `_codes.py` (CLOSED=2/THROWN=4) and `test_reconnect_resilience.py` (THROWN=2/CLOSED=4). Twelve files touched in `src/pyjmri/`, eight test files modified/added in `tests/`; no `_parsing.py` changes (writes outbound only). Builds directly on Epic 2 (HTTPClient, entity classes) and Epic 3 (no new transport plumbing).
- 2026-05-19 — Reframed "NCE Simulator command-echo limitation" throughout the story to "NCE open-loop (sim and real hardware are indistinguishable for command path)" after Mikey clarified that his physical NCE layout has no feedback sensors either. Task 0 spike adds an informational probe of WS echo behavior per commandable type to inform Story 4.2 planning. New memory `project_nce_open_loop.md` captures the correction for future stories.
- 2026-05-19 — Polish pass: converted bold-as-heading AC labels to proper `###` headings, added blank lines around all fenced code blocks, specified `text`/`python` language on every fence, restructured the AC9 step-by-step bullets into a numbered list, and removed scattered ALL-CAPS emphasis where it was decorative rather than load-bearing. No content changes; structure-only.
- 2026-05-20 — Story 4.1 implemented (`ready-for-dev` → `in-progress` → `review`). Live-JMRI spike verified `_codes.py` turnout codes (CLOSED=2, THROWN=4) against JMRI 5.14.0; documented error envelope shape; route activation uses state=2. Added `HTTPClient.command`, outbound code maps, `RouteState` enum, `Client.command`, per-entity command methods on `Turnout`/`Light`/`Memory`/`Route`, and read-only docstring notes on `Sensor`/`Block`/`SignalHead`/`SignalMast`. New integration tests cover the round-trip path (AC9) and NFR3 microbenchmark (AC10; median library overhead 0.821 ms vs 20 ms budget). Quality gates clean: 357 unit tests passing (was 332), 9/10 integration tests passing (1 skipped — no lights configured), ruff format / ruff check / mypy --strict all clean.
