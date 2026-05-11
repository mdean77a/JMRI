# Deferred Work

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

## Deferred from: code review of 2-1-http-transport-client-lifecycle-exception-hierarchy-logging-foundation (2026-05-07)

- **Logger calls absent in `_transport.py` and `client.py`** — AC #5 only requires logger declaration; actual `logger.debug()`/`logger.info()` calls for HTTP request/response events are appropriate for stories 2.2+ when there are substantive transport operations to log.
- **`aclose()` raising in `__aexit__` or probe-cleanup can mask original exception** — `httpx.AsyncClient.aclose()` is documented not to raise in normal circumstances; this is a common Python context-manager tradeoff. Revisit if production issues surface.
- **Probe endpoint deviation (`/json/v5/version`) not recorded in architecture document** — Captured in story 2.1 completion notes. Architecture doc update deferred per retro action item A1 (update architecture doc when next touched).
