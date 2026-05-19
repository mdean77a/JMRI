# Deferred Work

## Deferred from: code review of 3-2 and 3-3 (BMAD code-review, 2026-05-19)

- **`_DISPATCH_PARSERS` primary_attr is an opaque string with no static type-checking** — stored as plain `str`; `getattr(parsed, primary_attr)` is unchecked by mypy. A typo becomes a runtime `AttributeError` swallowed by the dispatch `except Exception`. Current strings are correct at HEAD. Fix: replace with a typed accessor callable. [`python_code/src/pyjmri/client.py:635-652`]
- **Entity dispatch name matching without case/whitespace normalization (pre-existing)** — `_entities.get((entity_type, name))` uses exact string match. JMRI WS vs REST name-form mismatch would cause silent event drops. Pre-existing; not introduced by Stories 3.2 or 3.3. [`python_code/src/pyjmri/client.py:259-319`]

## Deferred from: fresh independent review of 3-2-per-entity-waiter-list-and-wait-primitives (2026-05-12)

- **`wait_change` may miss A→B transition during `ensure_subscription` await** — `starting` captured post-subscribe reflects any transitions that fired during subscribe; inherent trade-off from the prior review's lost-wakeup fix (capturing before subscribe risks missing the registered event). AC3 says "at call time" but implementation chose post-subscribe semantics. [`python_code/src/pyjmri/turnout.py:963-965` and equivalents]
- **`_entities` rebuild window during `discover()`** — WS events arriving for newly-polled entities between HTTP discovery and `self._entities = new_index` are silently dropped; window is very small and caller has no entity references yet. Inherent to HTTP-poll + WS-subscribe. [`python_code/src/pyjmri/client.py:379-392`]
- **`Waitable` Protocol `_on_event: Any` allows silent wrong-type dispatch** — If a parser returns the wrong type for a primary attribute, all waiters silently never resolve (predicates return `False` forever). Design Decision #2 accepted this. [`python_code/src/pyjmri/_protocols.py:116`]
- **TOCTOU on stale cached state in `wait_state` early-return** — Pre-subscribe `if self.state == target` reads last-polled state; if cache is stale, early-return gives a false "already there" result. By design; documented behavior. [All six entity `wait_state` implementations]
- **`ensure_subscription` raising after `register` untested** — If `_registry.send()` fails inside `ensure_subscription`, the exception propagates through the `try` block; Python `finally` guarantees `remove(future)` runs. No test exercises this error path. [`python_code/src/pyjmri/turnout.py:131` and equivalents]
- **`_on_event(None)` could corrupt cached state** — Requires a parser to return `None` for its primary attribute field; speculative under `mypy --strict`, but no `isinstance` guard exists in `_on_event`. [`python_code/src/pyjmri/turnout.py:907-914` and equivalents]
- **`BaseException` from predicate escapes `fanout` and `_on_ws_message` exception guards** — `fanout` catches `Exception` per predicate; `CancelledError` (a `BaseException` in Python 3.8+) would escape both guards. Practically impossible with current equality-only lambdas. [`python_code/src/pyjmri/_waiters.py`, `client.py:323-334`]
- **Old Layout entity waiters never resolve after second `discover()`** — Documented in `discover()` docstring. No programmatic safety net (e.g., cancellation sweep). Considered and deferred in prior review. [`python_code/src/pyjmri/client.py:~540`]
- **AC1 spec text says `_waiters: list[tuple[...]]` but implementation uses `WaiterList[StateT]`** — Design Decision #1 chose Option A but the AC1 `Then` clause was not updated to reflect it. Spec/implementation documentation inconsistency only; no code change needed. [Spec AC1 vs. `_waiters.py`]

## Deferred from: code review of 3-2-per-entity-waiter-list-and-wait-primitives (2026-05-12)

- **`_on_ws_message` dispatch DROP logs vs AC6 prose** — AC6 wording references `pyjmri.transport`; story Tasks / implementation log via `logging.getLogger(__name__)` on `pyjmri.client`. Behavior matches Task 162; unify documentation or logger name in a doc-hardening pass. [`python_code/src/pyjmri/client.py:258-284`]
- **`discover()` silently abandons in-flight waiters from the prior Layout** — documented in the `discover()` docstring; consider adding a WARNING log on rebuild if `_entities` was non-empty at entry. [`python_code/src/pyjmri/client.py:~538`]
- **Tests inline JMRI integer state codes (`2`, `4`) rather than importing from `_codes.SENSOR_STATE`** — drift in `_codes.py` would not surface as a test failure. [`python_code/tests/unit/test_state_machine.py:~50-60`, `python_code/tests/integration/test_wait_primitives_latency.py:32-34`]
- **`WaiterList.remove` is O(n) via list comprehension** — fine for expected N (≤ tens per entity), but a hot-fired waiter loop on a high-event entity would prefer in-place remove. [`python_code/src/pyjmri/_waiters.py:53`]
- **`# noqa: ASYNC109` repeated on every `timeout` parameter across six entity files** — user-chosen approach (preferred over project-wide ruff config for narrower suppression scope); revisit if more `timeout`-bearing public methods land.
- **`signalHead`/`signalMast` partial-envelope tolerance unverified against live JMRI** — `parse_signal_head`/`parse_signal_mast` require `held`+`lit` as `_required_bool`; a thin push event would raise `JMRIProtocolError` and silently drop. Speculation — verify against live JMRI during Story 3.3 (forced-disconnect resilience test exercises push paths); loosen parser only if real JMRI behavior confirms partial pushes. [`python_code/src/pyjmri/_parsing.py:245-289`, `client.py:~395`]
- **`_DISPATCH_TABLE` keys are case-sensitive** — future JMRI version drift in entity-type strings would silently stop dispatch. Forward-compat speculation; no current evidence of JMRI changing these keys. [`python_code/src/pyjmri/client.py:~410`]
- **`asyncio.timeout(0)` behavior on `wait_*`** — always raises before any event can arrive; minor documentation note: `timeout=0` is a non-blocking probe that succeeds only via early-return. [Five entity modules' `wait_state` / `wait_change` docstrings]

## Deferred from: code review of 3-1-websocket-transport-subscriptionregistry-reconnect-with-bounded-backoff (2026-05-12)

- **`replay()` partial re-subscribe on mid-replay `send()` failure** — If `send()` raises on the nth of N subscriptions, remaining ones are not re-sent this cycle. Set is unchanged, so the next reconnect replays all correctly. Low impact: JMRI subscription state self-corrects. [`_subscriptions.py:62`]
- **`ensure()` adds key to set before `_send` completes** — If `_send` raises after the set add, key is permanently marked as "subscribed" but server never received it. Corrects on next reconnect via `replay()`. [`_subscriptions.py:46-54`]
- **`_connection` not cleared on normal server close (1000/1001)** — Graceful close exits the inner receive loop without `WebSocketException`; `_connection` stays non-None. Subsequent `send()` on the stale reference raises `WebSocketException` → `JMRIConnectionError` (handled). [`_transport.py:236-248`]
- **`UnicodeDecodeError` from invalid-UTF-8 binary frames not translated to `JMRIProtocolError`** — `raw.decode("utf-8")` raises raw `UnicodeDecodeError` on non-UTF-8 binary WS frames; not wrapped. JMRI is documented to send only UTF-8, so low real-world risk. [`_transport.py:318-319`]
- **`discover()` version check re-probes on every call after `JMRIVersionUnsupported`** — `_version_checked` stays `False` after version raise, so retry loops re-hit the network. Pre-existing from Epic 2. [`client.py:356-359`]

## Deferred from: code review of 2-2-wire-format-translation-codes-parsing-per-entity-state-enums (2026-05-07)

- **DCC address `"0"` (broadcast) accepted without range check** — Address 0 is the NMRA DCC broadcast address and is not a valid locomotive address. Range check (`>= 1`) deferred to the throttle story (5.1) where DCC addressing is exercised and the domain constraint is more naturally validated.
- **No cross-validation of `isLongAddress` vs. `dcc_address` numeric range** — Per NMRA DCC, short addresses are 1–127 and long addresses 1–10239. Validating the combination (e.g., short address flagged as long) is a throttle-acquisition concern more than a roster-parsing concern. Deferred to Story 5.1.



## Deferred from: code review of 2-3-per-entity-classes-with-read-only-state-and-value-access (2026-05-11)

- **`_optional_str` silent coercion of non-string to `None`** — Pre-existing Story 2.2 behavior in `_parsing.py`. Affects `Memory.value` and `Block.value` if JMRI ever sends numeric values for those fields. Consider raising `JMRIProtocolError` for non-string, non-None typed value fields.
- **`patch_http_factory` cannot stage separate pre-enter/post-enter responses** — Story 2.5 version check will break all existing lifecycle tests because `next_response = {}` is used for both the `__aenter__` version probe and the call under test. Needs per-phase response staging before Story 2.5.
- **`_get_entity` "got list" error message wrong for non-list/non-dict payloads** — Message says "got list" when payload is `None`, `str`, or `int`. Real transport prevents these; fake misuse only. Consider a more generic "unexpected response type" message.
- **`SignalHead` appearance code 256 (HELD sentinel) not handled** — Pre-existing Story 2.2 `_codes.py` design decision. Some JMRI versions may emit `appearance: 256`; currently raises `JMRIProtocolError("unknown state code")` rather than being handled gracefully alongside `held: bool`.
- **URL encoding of `$`, `(`, `)` in signal mast names untested with real JMRI** — `quote(name, safe='')` percent-encodes these characters present in real mast system names (e.g., `IF$shsm:basic:one-low($0001)`). JMRI acceptance of the encoded form via per-entity JSON v5 endpoints is unverified; needs integration testing.
- **`power_state()` discards `parsed.name` and `parsed.default`** — By design for single-booster v1. If multi-district support is added, the `default=True` flag should be used to select the primary booster rather than always taking `payload[0]`.
- **`SignalHead`/`SignalMast` `get_state()` atomicity guarantee undocumented** — Both methods update all fields only after a successful parse (all-or-nothing). The docstrings' "Side effects: also updates `held` and `lit`" should note this is atomic.

## Deferred from: code review of 2-4-layout-container-entitycollection-with-dual-name-lookup (2026-05-11)

- ~~**`Mapping.get()` raises `LayoutEntityNotFound` instead of returning default**~~ — **Resolved in Story 3.1 (2026-05-12)**. `LayoutEntityNotFound` now multi-inherits `KeyError` (analogous to `WaitTimeout(JMRIError, TimeoutError)`); `EntityCollection.get("missing")` returns `None` / the supplied default. Verified by `test_get_missing_returns_default_now_that_layout_entity_not_found_is_key_error`.
- **Silent overwrite on duplicate system names in `EntityCollection.__init__`** — If two entities share a system name, the later one silently overwrites the earlier one. JMRI guarantees unique system names per entity type, so this is low-risk in practice. Could add an assertion or warning if defensive validation is desired in a future hardening pass.

## Deferred from: code review of 2-1-http-transport-client-lifecycle-exception-hierarchy-logging-foundation (2026-05-07)

- ~~**Logger calls absent in `_transport.py` and `client.py`**~~ — **Resolved in Story 3.1 (2026-05-12)**. `HTTPClient.get` emits DEBUG on `pyjmri.transport` after each successful 200 response; `WSConnection.run`/`send` emit DEBUG on inbound/outbound envelopes; the WS supervisor emits INFO on reconnect and WARN on each retry attempt and at give-up via `pyjmri.reconnect`. The `pyjmri.subscription` logger fires INFO on first-add and on replay.
- **`aclose()` raising in `__aexit__` or probe-cleanup can mask original exception** — `httpx.AsyncClient.aclose()` is documented not to raise in normal circumstances; this is a common Python context-manager tradeoff. Revisit if production issues surface.
- **Probe endpoint deviation (`/json/v5/version`) not recorded in architecture document** — Captured in story 2.1 completion notes. Architecture doc update deferred per retro action item A1 (update architecture doc when next touched).
