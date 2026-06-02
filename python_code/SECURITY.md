# Security policy

## Reporting a vulnerability

If you believe you have found a security issue in `pyjmri`, please report it
privately rather than opening a public GitHub issue.

- **Preferred:** open a private vulnerability report via GitHub's "Security"
  tab on the repository (Security → Report a vulnerability).
- **Email fallback:** `miketraindoc@gmail.com` with `[pyjmri security]` in
  the subject line.

Please include:

- A description of the issue and its potential impact.
- Steps to reproduce (a minimal script is ideal).
- The `pyjmri` version (`pip show pyjmri`) and Python version.

I will acknowledge reports as time permits — `pyjmri` is a one-person
hobby project and there is no SLA, but security reports take priority
over feature work.

## Scope

`pyjmri` is an async client for the JMRI web server. The threat model
assumes:

- The JMRI instance is reachable on a **trusted local network**. JMRI
  itself has no authentication; this is a known property of JMRI, not
  of `pyjmri`. Anyone with network access to the JMRI port can drive
  the layout. Do not expose JMRI to the public internet.
- The `pyjmri` user is a trusted local script author who chose what URL
  to connect to.

In-scope concerns include:

- Vulnerabilities in `pyjmri`'s own parsing, transport, or state
  machinery that a malicious or compromised JMRI endpoint could
  exploit (e.g., resource exhaustion, injection into URLs/logs).
- Vulnerabilities introduced by `pyjmri`'s build/release pipeline or
  its published artifacts on PyPI.

Out of scope:

- The absence of authentication on JMRI's web server (this is a JMRI
  design property, documented upstream).
- Plaintext HTTP traffic between `pyjmri` and a JMRI instance the user
  explicitly pointed at via a `host:port` or `http://` URL. Pass an
  explicit `https://` or `wss://` URL if TLS is required.
- Issues in `httpx` or `websockets` themselves — please report those
  to their respective projects.

## Supported versions

Only the most recent published version receives security fixes. Older
versions are not patched in place; upgrade to the latest release.
