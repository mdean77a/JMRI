# pyjmri release notes

## v1.0.1

Security-pass cleanup; no API changes.

- Make the JMRI version-string parser tolerant of build suffixes (e.g.
  `5.14+Rdea51dcccf`); previously such versions raised
  `JMRIProtocolError` and blocked `discover()`.
- Document the plaintext-HTTP default and the TLS opt-in path on
  `Client` so callers know when to pass `https://` / `wss://`.
- Add `SECURITY.md` with a private-disclosure policy and threat-model
  scope.

JMRI version tested against: JMRI 5.14.1

Long-run test: skipped for this release; v1.0.0 evidence reused
(`duration=3600s disconnects=5 reconnects=5 rss_delta=-5.1MB fd_delta=0
task_delta=0 status=PASS`). No source changes in v1.0.1 touch the
WebSocket transport, reconnect machinery, or supervised-task plumbing,
so the v1.0.0 long-run result still characterizes the same code.

Hardware-mode validation (release-checklist step 6): drive and
keep-alive scripts both passed against the basement layout, DCC 1032,
on JMRI 5.14.1 / NCE USB / 2026-06-02. JMRI keeps throttle held after
30 s silence — v1 no-op keep-alive stub remains correct.

(Published 2026-06-02)

## v1.0.0

JMRI version tested against: JMRI 5.14.1

Long-run test result (Story 3.4): pyjmri long-run: duration=3600s disconnects=5 reconnects=5 rss_delta=-5.1MB fd_delta=0 task_delta=0 status=PASS

Hardware-mode keep-alive observation (Story 5.3): JMRI keeps throttle held after 30 s silence on JMRI 5.14.1 / NCE USB / 2026-05-26.

(Published 2026-05-26)
