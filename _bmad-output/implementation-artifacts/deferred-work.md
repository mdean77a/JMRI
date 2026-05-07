# Deferred Work

## Deferred from: code review of 2-2-wire-format-translation-codes-parsing-per-entity-state-enums (2026-05-07)

- **DCC address `"0"` (broadcast) accepted without range check** — Address 0 is the NMRA DCC broadcast address and is not a valid locomotive address. Range check (`>= 1`) deferred to the throttle story (5.1) where DCC addressing is exercised and the domain constraint is more naturally validated.
- **No cross-validation of `isLongAddress` vs. `dcc_address` numeric range** — Per NMRA DCC, short addresses are 1–127 and long addresses 1–10239. Validating the combination (e.g., short address flagged as long) is a throttle-acquisition concern more than a roster-parsing concern. Deferred to Story 5.1.



## Deferred from: code review of 2-1-http-transport-client-lifecycle-exception-hierarchy-logging-foundation (2026-05-07)

- **Logger calls absent in `_transport.py` and `client.py`** — AC #5 only requires logger declaration; actual `logger.debug()`/`logger.info()` calls for HTTP request/response events are appropriate for stories 2.2+ when there are substantive transport operations to log.
- **`aclose()` raising in `__aexit__` or probe-cleanup can mask original exception** — `httpx.AsyncClient.aclose()` is documented not to raise in normal circumstances; this is a common Python context-manager tradeoff. Revisit if production issues surface.
- **Probe endpoint deviation (`/json/v5/version`) not recorded in architecture document** — Captured in story 2.1 completion notes. Architecture doc update deferred per retro action item A1 (update architecture doc when next touched).
