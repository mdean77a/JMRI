# Deferred Work

## Deferred from: code review of 2-1-http-transport-client-lifecycle-exception-hierarchy-logging-foundation (2026-05-07)

- **Logger calls absent in `_transport.py` and `client.py`** — AC #5 only requires logger declaration; actual `logger.debug()`/`logger.info()` calls for HTTP request/response events are appropriate for stories 2.2+ when there are substantive transport operations to log.
- **`aclose()` raising in `__aexit__` or probe-cleanup can mask original exception** — `httpx.AsyncClient.aclose()` is documented not to raise in normal circumstances; this is a common Python context-manager tradeoff. Revisit if production issues surface.
- **Probe endpoint deviation (`/json/v5/version`) not recorded in architecture document** — Captured in story 2.1 completion notes. Architecture doc update deferred per retro action item A1 (update architecture doc when next touched).
