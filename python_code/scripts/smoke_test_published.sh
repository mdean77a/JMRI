#!/usr/bin/env bash
#
# smoke_test_published.sh — verify a PUBLISHED pyjmri wheel from PyPI installs
# and works in a clean environment.
#
# Why a separate script: run from inside the repo, an editable `src/` install of
# pyjmri shadows the real wheel, so you'd be testing your local code, not what
# users get. This builds a throwaway uv project in a temp dir OUTSIDE the repo,
# installs pyjmri straight from PyPI, and checks it.
#
# Usage:
#   scripts/smoke_test_published.sh [VERSION] [JMRI_URL]
#
#   VERSION   Optional. e.g. 1.2.0 — pins the install and asserts the installed
#             version matches. Omit (or "latest") to install the latest release.
#   JMRI_URL  Optional. e.g. 192.168.1.159:12080 — if given, also runs a LIVE
#             check against that JMRI instance, exercising EVERY discover
#             routine: discover() (layout entities + power), discover_operations()
#             (locations/trains/cars/engines), and discover_roster() (roster
#             entries), printing the counts/results for each. Omit to run only
#             the offline checks (no JMRI needed).
#
# Examples:
#   scripts/smoke_test_published.sh                      # latest, offline only
#   scripts/smoke_test_published.sh 1.2.0                # pin 1.2.0, offline only
#   scripts/smoke_test_published.sh 1.2.0 192.168.1.159:12080   # + live check
#
# Exit code is 0 only if every check passes.

set -euo pipefail

VERSION="${1:-latest}"
JMRI_URL="${2:-}"

# --- pick the install spec -------------------------------------------------
if [[ "$VERSION" == "latest" ]]; then
  SPEC="pyjmri"
else
  SPEC="pyjmri==${VERSION}"
fi

# --- isolated scratch project, auto-cleaned on exit ------------------------
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/pyjmri-smoke.XXXXXX")"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

echo "==> Smoke-testing published pyjmri ('${SPEC}')"
echo "    scratch dir: $WORKDIR"

cd "$WORKDIR"

# Fresh, self-contained uv project. --no-workspace so it never attaches to the
# pyjmri repo's workspace if you happen to run this from within ~/JMRI.
uv init --no-workspace . >/dev/null
# Remove the sample module uv scaffolds so nothing local can shadow the wheel.
rm -f main.py hello.py 2>/dev/null || true

echo "==> Installing from PyPI ..."
uv add "$SPEC" >/dev/null

# --- offline checks: version + imports + new-in-1.2 symbols ----------------
echo "==> Offline checks ..."
uv run python - "$VERSION" <<'PY'
import sys
import importlib.metadata as md
import pyjmri

requested = sys.argv[1]
installed = md.version("pyjmri")
print(f"    installed version : {installed}")

ok = True

if requested != "latest" and installed != requested:
    print(f"    FAIL: expected {requested}, got {installed}")
    ok = False

# Core surface must import.
for name in ("Client", "JMRIError"):
    if not hasattr(pyjmri, name):
        print(f"    FAIL: pyjmri.{name} missing")
        ok = False

# v1.2 roster surface must be present.
roster_symbols = ("Roster", "RosterEntry", "FunctionLabel",
                  "classify_capability", "firable_startup_functions")
missing = [n for n in roster_symbols if not hasattr(pyjmri, n)]
if missing:
    print(f"    FAIL: missing roster symbols: {missing}")
    ok = False
else:
    print("    roster API        : present")

# Every discover routine must exist on Client.
discover_methods = ("discover", "discover_operations", "discover_roster", "power_state")
missing_methods = [m for m in discover_methods if not hasattr(pyjmri.Client, m)]
if missing_methods:
    print(f"    FAIL: Client missing methods: {missing_methods}")
    ok = False
else:
    print("    discover routines : present (discover, discover_operations, discover_roster, power_state)")

print("    imports           : OK")
sys.exit(0 if ok else 1)
PY

# --- optional live functional check: run EVERY discover routine ------------
if [[ -n "$JMRI_URL" ]]; then
  echo "==> Live check against JMRI at ${JMRI_URL} — running all discover routines ..."
  uv run python - "$JMRI_URL" <<'PY'
import asyncio
import sys

import pyjmri

url = sys.argv[1]


def _counts(title, pairs):
    """Print a titled block of 'label: count' lines for a container."""
    print(f"    {title}")
    for label, collection in pairs:
        print(f"      {label:<14} {len(collection)}")


async def main() -> int:
    rc = 0
    try:
        async with pyjmri.Client(url) as jmri:
            # 1) Layout — discover()
            try:
                layout = await jmri.discover()
                _counts("Layout  (discover):", [
                    ("turnouts", layout.turnouts),
                    ("sensors", layout.sensors),
                    ("lights", layout.lights),
                    ("blocks", layout.blocks),
                    ("routes", layout.routes),
                    ("memories", layout.memories),
                    ("signal heads", layout.signal_heads),
                    ("signal masts", layout.signal_masts),
                ])
                power = await jmri.power_state()
                print(f"      {'power':<14} {power}")
            except Exception as exc:  # noqa: BLE001 - report and keep going
                print(f"      FAIL discover(): {type(exc).__name__}: {exc}")
                rc = 1

            # 2) Operations — discover_operations()
            try:
                ops = await jmri.discover_operations()
                _counts("Operations  (discover_operations):", [
                    ("locations", ops.locations),
                    ("trains", ops.trains),
                    ("cars", ops.cars),
                    ("engines", ops.engines),
                ])
            except Exception as exc:  # noqa: BLE001
                print(f"      FAIL discover_operations(): {type(exc).__name__}: {exc}")
                rc = 1

            # 3) Roster — discover_roster()
            try:
                roster = await jmri.discover_roster()
                print("    Roster  (discover_roster):")
                print(f"      {'entries':<14} {len(roster)}")
                for entry in list(roster.values())[:5]:
                    ident = entry.road_number or entry.name
                    print(f"        - {ident}  DCC {entry.dcc_address}  "
                          f"{entry.model or '—'}  [{entry.decoder_family or '—'}]")
                if len(roster) > 5:
                    print(f"        ... and {len(roster) - 5} more")
            except Exception as exc:  # noqa: BLE001
                print(f"      FAIL discover_roster(): {type(exc).__name__}: {exc}")
                rc = 1
        return rc
    except Exception as exc:  # noqa: BLE001 - connection/open failure
        print(f"    FAIL connecting to {url}: {type(exc).__name__}: {exc}")
        return 1


raise SystemExit(asyncio.run(main()))
PY
else
  echo "==> Skipping live discover sweep (no JMRI_URL given)."
fi

echo "==> ✅ Smoke test PASSED for '${SPEC}'."
