# Story 9.3: `throttle_for_entry` + capability-classification decision function + capability-aware startup example

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an operator,
I want to acquire a throttle straight from a roster entry, name, or DCC address — with a reusable startup that adapts to that loco's function labels — while a brand-new loco that isn't in the roster yet still drives,
so that I can point one capability-aware script at whatever loco I put on the track, without rewriting it per engine or being blocked by an un-catalogued address.

## Acceptance Criteria

1. **`Client.throttle_for_entry(target, *, roster=None, long=None) -> Throttle` is added** and accepts `target: RosterEntry | str | int`. A `RosterEntry`, a resolvable roster **name**, or a known DCC **address** yields a `Throttle` async context manager with long/short addressing derived from the matched entry (FR54). It returns the **same** `Throttle` type as `Client.throttle(...)` — additive convenience built on top of the existing acquire path, **not** a parallel implementation. (AC-1)
2. **It is a synchronous factory** (like `Client.throttle()`): it returns an *unacquired* `Throttle`, and acquire happens on `async with` entry — so `async with jmri.throttle_for_entry(loco) as t:` works directly (no `async with await`). Therefore resolution must complete **without** an `await` inside `throttle_for_entry`. (AC-2)
3. **Resolution mechanism (the Story 9.3 design decision — see Dev Notes):**
   - A **`RosterEntry`** argument needs no roster: the Client reads `dcc_address` / `long_address` straight off the entry. (AC-3a)
   - A **name (`str`)** or **address (`int`)** is resolved against a `Roster`: the one passed as `roster=`, else the Client's **cached** roster from a prior `discover_roster()` call (`self._roster`). `discover_roster()` is extended to store its returned `Roster` on the Client as that cache. (AC-3b)
   - An explicit **`long=` override** is honored on every path (it overrides the derived/convention value). (AC-3c)
4. **Unknown address → warn-and-drive (FR55).** A `throttle_for_entry(<int address>)` for an address **not** present in the roster (or when no roster is available) does **NOT** raise: it logs an informative `WARNING` ("DCC address N is not in the roster; assuming motor-only capabilities") and acquires the throttle best-effort, consistent with FR23's raw path — keeping an un-catalogued loco drivable. Because there is no entry to derive addressing from, long/short defaults by **JMRI convention (`address > 127` ⇒ long, else short)** with the assumption logged; an explicit `long=` override is accepted. An `int` target **never raises** for a miss. (AC-4)
5. **Unresolvable name → raise (FR54/FR51).** A `throttle_for_entry(<str name>)` whose name matches no roster entry raises a typed error naming the unresolved name (a name cannot be turned into a DCC address without a matching entry). Reuse `LayoutEntityNotFound` (the same error `roster[name]` raises). When a **name** is given but **no roster is available at all** (none passed and none cached), raise a clear typed error telling the caller to run `discover_roster()` first or pass `roster=` — a name path can never silently guess an address. (AC-5)
6. **Snapshot-staleness caveat documented (FR54).** `throttle_for_entry`'s docstring states the discovery-time-snapshot caveat: a loco re-addressed in JMRI after `discover_roster()` resolves to its *prior* address until the script re-runs `discover_roster()`. (AC-6)
7. **`classify_capability(entry: RosterEntry) -> Capability` is added** as a documented, unit-tested **pure function** (no I/O, no Client) in `roster.py`, plus a small frozen `Capability` result type. It classifies capability from function **labels** (a label containing "startup"/"shutdown"/"sound"/"horn"/"whistle"/"bell"/"engine"/"mute" ⇒ sound-capable), explicitly **NOT** from `decoder_family` / `decoder_model` strings (those are date-stamped definition-file names, not capability tags). (AC-7)
8. **Motor-only fallback.** `classify_capability` falls back to a minimal **motor-only** classification when function labels are blank, absent, or unrecognized (the common real case — many fixture entries have all-`None` labels). (AC-8)
9. **Auditable, not a black box.** The function's docstring states its inputs (which fields it reads), its matching rule (case-insensitive substring match against the keyword set, on `FunctionLabel.label`), and its motor-only fallback — so the decision is reviewable. The keyword set is a module-level constant, not inline literals. (AC-9)
10. **Unit tests for classification** cover: a **sound-labeled** entry (real labels like "Bell"/"Horn 1"/"Shutdown and Startup" ⇒ `sound is True`, non-empty `sound_functions`), a **motor-only** entry (all-`None`/empty labels ⇒ `sound is False`, `motor_only is True`, empty `sound_functions`), and a **mixed/partial-labels** entry. All pinned by attribute filter against the live `roster.json` fixture (never positional `[0]`), no hardcoded fleet facts. (AC-10)
11. **`examples/capability_aware_startup.py` (FR59).** Run against `Basement_Revised_2024.jmri` with a chosen DCC address, it: connects, calls `discover_roster()`, looks the loco up by address, prints its identity/decoder, classifies capability via `classify_capability`, fires **only** the functions the classification calls for (the firable `0 <= num <= 28` sound functions; see AC-13), and drives. The **same code, unmodified**, handles a sound loco, a motor-only loco, and an address absent from the roster (which logs the motor-only WARNING and still drives). It imports **only** from the top-level `pyjmri` namespace and runs clean under `mypy --strict`. (AC-11)
12. **Example docstring states the split success criterion:** the simulator verifies *which* `set_function` commands are issued; physical "visibly correct startup" (sound actually plays, loco actually moves) is hardware-only and manual. The example also degrades gracefully (explanatory message, not a traceback) on connection failure / empty roster, and hardcodes no entity name (basement DCC default overridable via `--dcc`). (AC-12)
13. **F29+ guard.** `set_function` accepts only `0 <= n <= 28` (existing Story 5.2 constraint). The startup logic (and the example) fires only sound functions whose `num` is in `[0, 28]`; a sound-labeled function above F28 is *classified* but **not** commanded — it is skipped with a logged note, never passed to `set_function` (which would raise `ValueError`). (AC-13)
14. **Simulator/plumbing test for capability startup.** A unit test asserts the **exact set** of `set_function` calls the startup logic issues for given fixture `RosterEntry` data (recorded via a fake/recording throttle or `ClientHandle` mock) — plumbing-verifiable — and does **not** assert physical movement (the NCE simulator has no virtual loco). (AC-14)
15. **`throttle_for_entry` unit tests** cover: a `RosterEntry` arg (addressing read off the entry, no roster needed); a name resolved via cached roster and via `roster=`; a name miss → `LayoutEntityNotFound`; a name with no roster available → the clear typed error; an `int` address hit (entry addressing) and an `int` address miss → WARNING + convention addressing + **no raise**; `long=` override honored; and that the returned object is a `Throttle` that acquires through the *same* `throttle_acquire` path (assert via the existing throttle test seams, no live JMRI). (AC-15)
16. **Export + exports are alphabetical.** `Capability` and `classify_capability` are added to `src/pyjmri/__init__.py` imports and `__all__`, inserted alphabetically. `throttle_for_entry` is a `Client` method (no separate export). (AC-16)
17. **Layout-agnosticism (hard invariant).** No hardcoded roster name, DCC address, function number, keyword-derived loco identity, or fleet count appears in `src/pyjmri/`. The keyword set is capability vocabulary (e.g. "horn"), not layout data. The example may carry a basement-default `--dcc` (overridable), consistent with the other examples. (AC-17)
18. **Quality gates green.** `uv run --no-sync ruff check`, `ruff format --check`, `mypy --strict src/pyjmri`, `mypy --strict examples/capability_aware_startup.py` (the example must type-check), and `pytest -m "not integration"` all pass. (AC-18)

> **Scope fence — Story 9.3 is `throttle_for_entry` + classification + the capability startup example ONLY.** Do **NOT** build in this story: `examples/roster_catalog.py`, the exhaustive read-only no-mutating-method surface test, the user-facing Roster *documentation* section, or the v1.2 release (`pyproject.toml` bump, `uv lock`, RELEASES.md, `uv build`) — those are **Story 9.4**. Do not modify `discover_roster()`'s fetch/parse/graceful-degrade behavior (Story 9.2) beyond adding the `self._roster` cache assignment. `_codes.py`, `_parsing.py`, `layout.py`, the eight layout entity modules, and `operations.py` are **not** touched. Epics 1–8 behavior is byte-for-byte unchanged.

## Tasks / Subtasks

- [x] **Task 1 — `classify_capability` + `Capability` in `roster.py`** (AC: 7, 8, 9, 10, 17)
  - [x] Add a frozen result type next to `RosterEntry`: `@dataclass(frozen=True, kw_only=True, slots=True) class Capability` with `sound: bool` and `sound_functions: tuple[FunctionLabel, ...]` (the sound-labeled functions, in entry order), plus a `@property motor_only(self) -> bool: return not self.sound`. Google-style docstring; no command/set methods (read-only result).
  - [x] Add module-level keyword constant: `_SOUND_KEYWORDS: frozenset[str] = frozenset({"sound", "startup", "shutdown", "horn", "whistle", "bell", "engine", "mute"})` (lowercase; matched case-insensitively). Document that this is the auditable vocabulary and is intentionally label-based, NOT decoder-family-based.
  - [x] `def classify_capability(entry: RosterEntry) -> Capability:` — pure function. Scan `entry.function_labels`; a `FunctionLabel` is sound-related when `fl.label` is non-`None` and `any(kw in fl.label.lower() for kw in _SOUND_KEYWORDS)`. `sound = bool(sound_functions)`. Empty/all-`None` labels ⇒ `Capability(sound=False, sound_functions=())` (motor-only). Docstring must state: inputs read (`function_labels` only — NOT `decoder_family`/`decoder_model`), the substring-match rule, and the motor-only fallback.
  - [x] Add `Capability` and `classify_capability` to `roster.py`'s `__all__` (alphabetical: `Capability`, `FunctionLabel`, `Roster`, `RosterEntry`, `classify_capability` — keep `ruff`'s import/`__all__` ordering rule green; functions after classes per existing convention, or strict alpha — match what `ruff` enforces).

- [x] **Task 2 — `discover_roster()` caches the Roster on the Client** (AC: 3b)
  - [x] In `Client.__init__`, add `self._roster: Roster | None = None` (Client has no `__slots__`, so this is a plain attribute — keep it near `self._entities`). Type via the already-imported `Roster`.
  - [x] In `discover_roster()`, assign the result to `self._roster` immediately before returning it (both the populated `Roster(entries)` path and the graceful-degrade `Roster([])` path — the cache is "last discovered roster," which may legitimately be empty). Do NOT change any other discover_roster behavior (Story 9.2). Add one sentence to its docstring: the returned roster is cached on the Client and used by `throttle_for_entry` when no `roster=` is passed.

- [x] **Task 3 — `Client.throttle_for_entry(...)`** (AC: 1, 2, 3, 4, 5, 6, 13)
  - [x] Add `def throttle_for_entry(self, target: RosterEntry | str | int, *, roster: Roster | None = None, long: bool | None = None) -> Throttle:` — **synchronous**, mirroring the existing `throttle()` factory (lazy `from pyjmri.throttle import Throttle`; return an unacquired `Throttle(self, dcc_address=..., long=...)`).
  - [x] **`RosterEntry` path:** `dcc = target.dcc_address`; `is_long = long if long is not None else target.long_address`. No roster lookup.
  - [x] **`str` (name) path:** `r = roster if roster is not None else self._roster`. If `r is None` → raise a clear typed error (`LayoutEntityNotFound` with a message/`context` noting no roster is available, OR a `RuntimeError` — see Dev Notes for the chosen error; pick one and document it). Else `entry = r[target]` (raises `LayoutEntityNotFound` on miss, AC-5); then resolve addressing from `entry` (with `long=` override).
  - [x] **`int` (address) path:** `r = roster if roster is not None else self._roster`. `entry = r.by_address(target) if r is not None else None`. If `entry is not None` → addressing from entry (`long=` override allowed). If `entry is None` → **warn-and-drive (AC-4):** `logger.warning("DCC address %d is not in the roster; assuming motor-only capabilities", target)`; `is_long = long if long is not None else (target > 127)` (JMRI convention; log the assumption); `dcc = target`. **Never raise** on the int path.
  - [x] Use `isinstance` dispatch with `bool` rejected as an `int` is not a concern here (addresses are `int`); but guard `isinstance(target, bool)` defensively if you branch on `int` (a `bool` is an `int` subclass) — treat a `bool` target as a programming error (`TypeError`). Keep the branch order: `RosterEntry` → `str` → `int`.
  - [x] Google-style docstring: the three input forms, the resolution mechanism (roster arg → cached → for int, convention fallback; for name, raise), the FR55 warn-and-drive for an unknown address vs the raise for an unknown name, the `long=` override, and the snapshot-staleness caveat (AC-6). Note it returns the *same* `Throttle` as `throttle()` and that acquire still happens on `async with` (so FR28 open-loop honesty is unchanged — a successful acquire does not imply a physical loco).

- [x] **Task 4 — Export `Capability` + `classify_capability`** (AC: 16)
  - [x] In `src/pyjmri/__init__.py`: `from pyjmri.roster import Capability, FunctionLabel, Roster, RosterEntry, classify_capability` (keep import alphabetical as `ruff` enforces) and add `"Capability"` and `"classify_capability"` to `__all__` in the correct alphabetical slots (`Capability` before `Car`; `classify_capability` among the lowercase entries — confirm `ruff`'s `__all__` sort: it sorts case-sensitively, uppercase before lowercase, so `classify_capability` lands near the end). Run `ruff check` to confirm the exact ordering.

- [x] **Task 5 — `examples/capability_aware_startup.py`** (AC: 11, 12, 13, 17)
  - [x] New example modelled on `examples/back_and_forth.py` (argparse `--url`/`--dcc`/`--short`/`--speed`/`--seconds`) + `examples/operations_report.py` (graceful `except* JMRIError`, `SystemExit` codes, `_leaf_messages`). Imports ONLY from top-level `pyjmri`.
  - [x] Flow: `async with Client(url) as jmri:` → `roster = await jmri.discover_roster()` → `entry = roster.by_address(args.dcc)` → print identity/decoder (road number, model, decoder family/model, address; "(not in roster — motor-only)" when `entry is None`) → `caps = classify_capability(entry) if entry is not None else Capability(sound=False, sound_functions=())` (motor-only for an un-catalogued loco) → choose throttle target: `entry if entry is not None else args.dcc` → `async with jmri.throttle_for_entry(target) as t:` → fire startup: for each `fl in caps.sound_functions` with `0 <= fl.num <= 28`, `await t.set_function(fl.num, True)` (skip+print any `num > 28`) → `await t.set_speed(args.speed, forward=True)` → hold for `--seconds` → on exit the `async with` releases.
  - [x] Docstring: the split success criterion (simulator verifies *which* `set_function` commands fire; physical correctness is manual hardware-only), the simulator caveat (no virtual loco — nothing physically moves on the sim; throttle commands are accepted), and the "same code for sound / motor-only / un-catalogued address" claim. Note FR55 warn-and-drive is what keeps a brand-new address running.
  - [x] `mypy --strict examples/capability_aware_startup.py` must pass (add it to the gate list you run).

- [x] **Task 6 — Unit tests** (AC: 10, 14, 15)
  - [x] **Classification** (`tests/unit/test_roster_capability.py`, NEW): drive `classify_capability` against the live `roster.json` fixture (parse via `parse_roster_entry` + `load_fixture("roster")`). Pin a sound entry by `next(e for e in entries if any(fl.label and "horn" in fl.label.lower() for fl in e.function_labels))` → `sound is True`, `sound_functions` non-empty. Pin a motor-only entry by `next(e for e in entries if all(fl.label is None for fl in e.function_labels))` → `sound is False`, `motor_only is True`, `sound_functions == ()`. Add a synthetic mixed/partial entry (some labeled, some `None`) → only the labeled-and-matching functions appear in `sound_functions`. Assert `classify_capability` reads no decoder field (e.g. an entry with a "sound"-ish `decoder_family` but all-`None` labels classifies motor-only).
  - [x] **Startup command set** (in the same file or `test_capability_startup.py`): build the firable set the startup logic would issue for a given fixture entry, assert it equals the `[0,28]`-filtered sound function nums, and assert a synthetic entry with a sound label on F30 yields NO `set_function(30, ...)` (AC-13). If the example exposes a small pure helper (e.g. `startup_functions(caps) -> tuple[int, ...]`), import and test it; otherwise record the `set_function` calls through a recording fake throttle. **Prefer factoring the firable-selection into a tiny pure function** (in `roster.py` or the example) so it is unit-testable without driving a throttle.
  - [x] **`throttle_for_entry`** (`tests/unit/test_throttle_for_entry.py`, NEW): mirror the existing throttle unit-test seams (`tests/unit/test_throttle*.py` — reuse the same fake `ClientHandle`/acquire patching). Cases: `RosterEntry` arg → `Throttle.dcc_address`/`.long` match the entry (no roster needed); name via `roster=` and via cached `self._roster` → correct entry addressing; name miss → `LayoutEntityNotFound`; name + no roster → the chosen clear error; `int` hit → entry addressing; `int` miss → WARNING (`caplog`) + convention `long == (addr > 127)` + **no raise**; `long=` override flips addressing on each path; returned object is a `Throttle` and acquiring it goes through `throttle_acquire` (assert via the existing acquire fake). Pin fixture entries by attribute filter; derive addresses from the fixture, never hardcode.
  - [x] No new hardcoded fleet facts anywhere (AC-17): derive every expected value from the parsed fixture.

- [x] **Task 7 — Optional integration smoke (only if it fits the existing pattern)** (AC: 14 hardware note)
  - [x] If `tests/integration/test_discovery.py` (or a roster integration module) is the right home: add a `@pytest.mark.integration` test that `discover_roster()` then `async with jmri.throttle_for_entry(<entry pinned by attribute filter>) as t: await t.set_speed(0.0)` acquires + releases cleanly on the simulator (plumbing only — no movement assertion; NCE sim has no virtual loco). Skip cleanly if JMRI unreachable. This is a nice-to-have; the AC-14 obligation is satisfied by the unit-level command-set assertion. Do not block the story on hardware.

- [x] **Task 8 — Run all gates (always `uv run --no-sync`)** (AC: 18)
  - [x] `uv run --no-sync ruff check`
  - [x] `uv run --no-sync ruff format --check` (separate CI gate — run both)
  - [x] `uv run --no-sync mypy --strict src/pyjmri`
  - [x] `uv run --no-sync mypy --strict examples/capability_aware_startup.py` (the example must type-check clean)
  - [x] `uv run --no-sync pytest -m "not integration"` (baseline at story start: **636 passed / 26 deselected**; expect it to rise with the new classification + `throttle_for_entry` tests)

### Review Findings

Code review 2026-06-17 (3 adversarial layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor over the full uncommitted Epic 9 blob, 9.1–9.3). 2 decision-needed (both resolved: 1→patch, 1→dismissed), 5 patch, 2 deferred, 7 dismissed as noise.

- [x] [Review][Patch] Narrow `discover_roster` catch to transport errors — replace the broad `except Exception` with the named transport exceptions (`JMRIConnectionError`/`JMRIRequestTimeout`/`ConnectionError`) so FR57 graceful-degrade is preserved but a real `KeyError`/`TypeError`/`AttributeError` in parse/init propagates instead of silently emptying the roster. (Resolved from decision-needed.) [src/pyjmri/client.py:487-498]
- [x] [Review][Patch] ASCII guard inconsistency in function-key parsing — `_parse_function_labels` uses `fname[1:].isdecimal()` with no `.isascii()`, so a fullwidth-digit key (`F１`) is accepted, while the address parser in the SAME diff was hardened to reject it. [src/pyjmri/_parsing.py:206-216]
- [x] [Review][Patch] AC-15 unit-level acquire-path assertion missing — `test_throttle_for_entry.py` only checks the unacquired Throttle's address/long/type; the "acquires through the same `throttle_acquire` path" assertion lives ONLY in an `@pytest.mark.integration` test that skips without live JMRI. AC-15 demanded a unit-level seam. [tests/unit/test_throttle_for_entry.py]
- [x] [Review][Patch] Un-catalogued DCC address emits two redundant WARNING lines — `throttle_for_entry`'s miss path calls `Roster.by_address` (which itself logs `"no roster entry for DCC address %d"`) then logs its own `"...assuming motor-only capabilities"`. Two warnings for one event. [src/pyjmri/client.py:399-407]
- [x] [Review][Patch] Malformed F-key entries skipped with no diagnostic — a `functionKeys` element missing `name` or not starting with `F` is silently dropped in `_parse_function_labels`, so bad capability data vanishes with no trace. [src/pyjmri/_parsing.py:200-216]
- [x] [Review][Defer] `by_address` duplicate-address first-wins [src/pyjmri/roster.py:687-698] — deferred, pre-existing Story 9.2 design; second loco sharing an address is unreachable by-address with no run-time signal.
- [x] [Review][Defer] `parse_roster_entry` has no numeric DCC range guard [src/pyjmri/_parsing.py:362-371] — deferred, pre-existing; address `"0"`/`"99999999"` passes `isdecimal()` and loads, failing opaquely later at acquire.

**Resolution (2026-06-17):** All 5 patches applied. `client.py` — narrowed `discover_roster` catch to `(JMRIConnectionError, JMRIRequestTimeout, JMRIProtocolError, ConnectionError)`; switched `throttle_for_entry`'s int-miss path to a new silent `Roster._find_by_address` so an un-catalogued address warns once, not twice. `roster.py` — added `_find_by_address`. `_parsing.py` — added `.isascii()` guard to the function-key name check and DEBUG-logged skipped malformed `functionKeys` elements. `test_throttle_for_entry.py` — added `test_throttle_for_entry_acquires_through_throttle_acquire` (unit-level acquire-seam assertion for AC-15). The int-range finding was dismissed per decision (FR55 warn-and-drive purity). Gates green: ruff check + format, mypy --strict (src + example), pytest 662 passed / 27 deselected (+1 from the new test).

## Dev Notes

### What this story is, in one sentence

Add a `Client.throttle_for_entry(entry | name | address)` convenience over the existing throttle-acquire path, a pure `classify_capability(RosterEntry) -> Capability` decision function that reads function **labels** (not decoder strings), and a `capability_aware_startup.py` example that uses both — the same script driving a sound loco, a motor-only loco, and an un-catalogued address (which warns and still drives).

### The Story 9.3 design decision: how `throttle_for_entry` resolves a name/address

The epic (Story 9.3 AC) explicitly left the resolution mechanism to this story. **Decision (made here):**

- `throttle_for_entry` is a **synchronous** factory, exactly like the existing `Client.throttle()` (`client.py:610`) — it returns an *unacquired* `Throttle`; acquire happens on `async with` entry. This is required so `async with jmri.throttle_for_entry(loco) as t:` reads naturally (the Epic summary and AC-11 example both use that form). A sync factory **cannot** `await discover_roster()` internally, so resolution must use a roster that already exists.
- **Roster source, in order:** (1) an explicit `roster=` argument; (2) the Client's cached `self._roster`, which `discover_roster()` now populates. A `RosterEntry` argument needs neither (addressing is read straight off it).
- **Why cache on the Client:** the canonical flow is "call `discover_roster()` once, then drive by name/address." Caching the last-discovered roster makes `throttle_for_entry("1029 NW2 Switcher")` work after a single `discover_roster()` with no extra plumbing — and it stays consistent with the snapshot model (re-running `discover_roster()` refreshes the cache, AC-6).
- **The int path never raises** (FR55/FR23 parity): an unknown or rosterless address warns and drives motor-only with convention addressing. **The name path raises** (`LayoutEntityNotFound`): a name has no address to fall back to. **No roster at all + a name** is a usage error — raise a clear typed error. *Pick one error type for the rosterless-name case and document it in the docstring.* Recommended: `LayoutEntityNotFound` with `context={"entity_type": "rosterEntry", "key": name, "reason": "no roster available — call discover_roster() or pass roster="}` so callers catch one type for both name-miss and no-roster; if that feels like overloading the "not found" semantics, a `RuntimeError` (matching the "Client is not open" style at `client.py:899`) is acceptable — state whichever you choose.

```python
def throttle_for_entry(
    self,
    target: RosterEntry | str | int,
    *,
    roster: Roster | None = None,
    long: bool | None = None,
) -> Throttle:
    from pyjmri.throttle import Throttle  # lazy, mirrors throttle()

    if isinstance(target, RosterEntry):
        dcc = target.dcc_address
        is_long = target.long_address if long is None else long
    elif isinstance(target, bool):              # bool is an int subclass — reject explicitly
        raise TypeError("throttle_for_entry target must be a RosterEntry, name, or address")
    elif isinstance(target, str):
        r = roster if roster is not None else self._roster
        if r is None:
            raise LayoutEntityNotFound(entity_type="rosterEntry", key=target)  # + reason in context
        entry = r[target]                        # raises LayoutEntityNotFound on miss (AC-5)
        dcc = entry.dcc_address
        is_long = entry.long_address if long is None else long
    else:                                        # int address
        r = roster if roster is not None else self._roster
        entry = r.by_address(target) if r is not None else None
        if entry is not None:
            dcc = entry.dcc_address
            is_long = entry.long_address if long is None else long
        else:
            logger.warning(
                "DCC address %d is not in the roster; assuming motor-only capabilities", target
            )
            dcc = target
            is_long = (target > 127) if long is None else long  # JMRI convention
    return Throttle(self, dcc_address=dcc, long=is_long)
```

[Source: src/pyjmri/client.py:610 (`throttle()` sync-factory + lazy-import pattern), :898 (`discover_roster`), :481 (`throttle_acquire` — the path the returned Throttle uses); src/pyjmri/throttle.py:60 (`Throttle.__init__`); src/pyjmri/roster.py:129 (`by_address` get-style); src/pyjmri/layout.py:96 (`EntityCollection.__getitem__` raises `LayoutEntityNotFound`)]

> Note `by_address` already logs its own miss WARNING (`roster.py:139`). On the int-miss path you go through `by_address` (it warns "no roster entry for DCC address N") *and then* `throttle_for_entry` warns the motor-only assumption — two related WARNINGs. That is acceptable (the second explains the consequence); if a reviewer objects to the double-log, resolve the int-miss via `self._by_address`-equivalent without the find's warning — but the simplest correct path uses `by_address`, so keep it unless told otherwise.

### Capability classification — the risk-bearing core

Capability is read from **function labels**, never decoder strings. The `roster.json` fixture proves why: `decoder_family` values are date-stamped definition-file names ("Jan 2012", "Sep 2018", "ESU LokSound 5", "E-Z Command decoders") — they do not tell you whether a loco has sound. The labels do ("Bell", "Horn 1", "Shutdown and Startup"). Many entries have all-`None` labels (e.g. "1029 NW2 Switcher") → motor-only.

Recommended result + function shape (prescriptive, dev may refine the keyword set):

```python
_SOUND_KEYWORDS: frozenset[str] = frozenset(
    {"sound", "startup", "shutdown", "horn", "whistle", "bell", "engine", "mute"}
)

@dataclass(frozen=True, kw_only=True, slots=True)
class Capability:
    """What a locomotive can do, inferred from its roster function labels.

    Read-only result of :func:`classify_capability`. ``sound`` is ``True``
    when at least one function carries a sound-related label;
    ``sound_functions`` are those labelled functions in entry order.
    ``motor_only`` is the inverse — the common case for an unlabelled or
    un-catalogued loco.
    """
    sound: bool
    sound_functions: tuple[FunctionLabel, ...]

    @property
    def motor_only(self) -> bool:
        return not self.sound


def classify_capability(entry: RosterEntry) -> Capability:
    """Classify a locomotive's capabilities from its function labels.

    Reads ONLY ``entry.function_labels`` — never ``decoder_family`` /
    ``decoder_model`` (those are decoder-definition-file names, not
    capability tags). A function is sound-related when its label
    (case-insensitive) contains any of ``_SOUND_KEYWORDS``. Falls back to a
    motor-only classification when labels are blank, absent, or
    unrecognised (the common real case).
    """
    sound_fns = tuple(
        fl for fl in entry.function_labels
        if fl.label is not None and any(kw in fl.label.lower() for kw in _SOUND_KEYWORDS)
    )
    return Capability(sound=bool(sound_fns), sound_functions=sound_fns)
```

The startup logic fires only firable sound functions: `[fl.num for fl in caps.sound_functions if 0 <= fl.num <= 28]`. **Factor this into a tiny pure helper** (e.g. `firable_startup_functions(caps) -> tuple[int, ...]`, in `roster.py` next to `classify_capability`, OR a private helper in the example) so AC-14's command-set assertion is a pure unit test, not a throttle-driving test. If you put it in `roster.py`, export it too (AC-16) and unit-test it directly; if it lives in the example, the example test imports it. The fixture has sound labels up to **F31**, so the F28 guard is exercised by real data, not just a synthetic.

### Read these before you write (do not reinvent)

- **`src/pyjmri/client.py:610` `throttle()`** — the exact sync-factory + lazy-`Throttle`-import pattern `throttle_for_entry` copies. `:898` `discover_roster()` — add the `self._roster = result` cache here. `:135` `__init__` — add `self._roster: Roster | None = None`. [Source: src/pyjmri/client.py]
- **`src/pyjmri/throttle.py`** — `Throttle` is constructed unacquired and acquires in `__aenter__`; `set_function(n, on)` enforces `0 <= n <= 28` and **raises `ValueError`** outside it (`throttle.py:236`) — this is exactly why AC-13's F29+ guard must filter before calling. `set_speed(value, *, forward=True)` (forward now defaults forward after commit `cec8beb`). [Source: src/pyjmri/throttle.py:202, :146]
- **`src/pyjmri/roster.py`** — add `Capability` + `classify_capability` (+ optional `firable_startup_functions`) here; `RosterEntry`/`FunctionLabel`/`Roster` already exist. `by_address` is get-style (`None` + WARNING on miss, `:129`). [Source: src/pyjmri/roster.py]
- **`examples/operations_report.py`** — the read-only-example template: argparse `--url`, `except* JMRIError` with `_leaf_messages`, `SystemExit` codes, graceful empty-data message. **`examples/back_and_forth.py`** — the throttle-driving template: `async with layout.throttle(...) as t:` loop, `--dcc`/`--short`/`--speed` args, and the explicit "simulator has no virtual loco — nothing moves; tap sensors / use real hardware to see motion" note you must echo. [Source: examples/operations_report.py, examples/back_and_forth.py]
- **`tests/unit/test_throttle*.py`** — reuse the existing fake-`ClientHandle`/acquire seams for the `throttle_for_entry` tests so you assert acquire goes through `throttle_acquire` without live JMRI. **`tests/unit/test_roster_parsing.py`** + `tests/unit/conftest.py` `load_fixture` — the fixture-driven test style (`load_fixture("roster")`, `parse_roster_entry`, pin by `next(...)`). [Source: tests/unit/test_throttle.py, tests/unit/test_roster_parsing.py, tests/unit/conftest.py]

### Real-data facts to lean on (from the live `roster.json` fixture; do NOT hardcode in `src/`)

- 44 entries. Sound entries carry real labels ("Headlights", "Bell", "Horn 1", "Shutdown and Startup", …) with `functionKeys` up to **F31**. Motor-only entries (e.g. "1029 NW2 Switcher") have all-`None` labels. Decoder families are heterogeneous date-stamped strings. Duplicate DCC addresses exist (41, 606) — irrelevant to 9.3 but note `by_address` first-wins already handles them.
- Use these in **tests** via attribute filters; never write the names/addresses into `src/pyjmri/` (AC-17).

### Project Structure Notes

All paths under `python_code/` (the only writable tree — `.jmri` profiles, `roster.xml`, `roster/` are read-only; the library reads JMRI's JSON over HTTP, never the profile XML):

- `src/pyjmri/roster.py` — **UPDATE**: add `Capability`, `classify_capability` (+ optional `firable_startup_functions` pure helper) and `_SOUND_KEYWORDS`. `RosterEntry`/`FunctionLabel`/`Roster` unchanged.
- `src/pyjmri/client.py` — **UPDATE**: `self._roster` cache in `__init__`; cache assignment in `discover_roster()`; new `throttle_for_entry()` sync factory.
- `src/pyjmri/__init__.py` — **UPDATE**: export `Capability`, `classify_capability` (alphabetical).
- `examples/capability_aware_startup.py` — **NEW**.
- `tests/unit/test_throttle_for_entry.py` — **NEW**.
- `tests/unit/test_roster_capability.py` — **NEW** (classification + firable-function-set).
- `tests/integration/test_discovery.py` — **OPTIONAL UPDATE** (Task 7 smoke).

Untouched (scope fence): `_parsing.py`, `_codes.py`, `layout.py`, `throttle.py` (consumed, not modified), `operations.py`, and the eight layout entity modules. `examples/roster_catalog.py`, the read-only surface test, the docs section, and the v1.2 release are **Story 9.4**.

### Testing Requirements

- Framework `pytest`; classification tests are pure (no live JMRI) against `load_fixture("roster")` + `parse_roster_entry`. `throttle_for_entry` tests reuse the existing throttle fake-handle seams (no live JMRI). [Source: tests/unit/conftest.py, tests/unit/test_throttle.py]
- **No hardcoded fleet facts** in `src/` or as test oracles (AC-17): pin entries with `next(e for e in ... if <attribute>)`, derive addresses/counts from the fixture.
- Required unit cases: classification (sound / motor-only / mixed, and decoder-string-ignored); firable-function set with the F28 guard (F30 sound label not commanded); `throttle_for_entry` for `RosterEntry`, name-via-`roster=`, name-via-cache, name-miss → `LayoutEntityNotFound`, name + no-roster → chosen error, int-hit, int-miss → WARNING + convention + no-raise, `long=` override; returned `Throttle` acquires via `throttle_acquire`.
- The capability-startup command-set assertion (AC-14) is a **unit** test (plumbing-verifiable); physical movement is explicitly NOT asserted (NCE sim has no virtual loco — see memory `project_throttle_simulator_blindspot`).
- Run before declaring done (always `uv run --no-sync`): `ruff check`; `ruff format --check`; `mypy --strict src/pyjmri`; `mypy --strict examples/capability_aware_startup.py`; `pytest -m "not integration"`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.3] — story statement + acceptance criteria (`throttle_for_entry`, classification, capability-startup example)
- [Source: _bmad-output/planning-artifacts/epics.md — "Roster increment (v1.2) — additional technical requirements"] — `throttle_for_entry` addressing (JMRI convention `>127⇒long`, `long=` override), capability = function labels NOT `decoderFamily`, throttle F0–F28 constraint, reuse existing assets
- [Source: _bmad-output/planning-artifacts/architecture.md — "Roster Subsystem (Read-Only)"] — `Client.throttle_for_entry` derives long/short from the matched entry, returns the same `Throttle`; unknown address warns motor-only best-effort, unresolvable name raises; capability-from-labels with motor-only fallback
- [Source: _bmad-output/planning-artifacts/prd.md — FR54, FR55 (amended 2026-06-16), FR59] — entry/name/address throttle, warn-and-drive for unknown address vs raise for unknown name, capability-aware startup example
- [Source: _bmad-output/implementation-artifacts/9-2-discover-roster-standalone-by-address-graceful-degrade.md] — `discover_roster()` + `Roster.by_address` this story builds on; the FR55 split (`by_address` returns None, `roster[name]` raises) Dev Notes
- [Source: _bmad-output/implementation-artifacts/9-1-roster-wire-format-parsing-and-capability-aware-entity-classes.md] — `RosterEntry`/`FunctionLabel` fields + the F29–F31-in-data finding
- [Source: src/pyjmri/client.py:610 (`throttle`), :898 (`discover_roster`), :481 (`throttle_acquire`), :135 (`__init__`)]
- [Source: src/pyjmri/throttle.py:202 (`set_function` F0–F28 guard), :146 (`set_speed`)]
- [Source: src/pyjmri/roster.py:129 (`by_address`)]
- [Source: examples/operations_report.py, examples/back_and_forth.py] — example templates (graceful read-only + throttle-driving)

### Git / recent-work intelligence

No recent commit touches `throttle_for_entry`/classification. Commit `cec8beb` made `set_speed`'s `forward` default to forward — the startup example can call `await t.set_speed(speed)` without `forward=True`, but pass it explicitly for clarity. Recent `python_code/` work is notebook/example tinkering (`b5351fc`, `9cd8548`, `1f63c66`) — no source conflicts. Stories 9.1 (parser + entity classes, done) and 9.2 (`discover_roster()` + `Roster.by_address`, done) are the foundation; this story consumes both unchanged. [Source: git log -- python_code/]

### Project context reference

- `python_code/` is a modern Python 3.11+ async JMRI client (external, over the web server), targeting only `Basement_Revised_2024.jmri`. v1.0.x shipped to PyPI; Epic 8 (Operations) is v1.1; Epic 9 (Roster) is v1.2. [Source: memory project_python_code, project_pyjmri_status, project_roster_feature]
- Roster is **fully simulator-testable** (pure metadata, no NCE open-loop blind spot) — but the capability-startup example's *physical* "sound plays / loco moves" check is hardware-only and manual; the NCE simulator accepts throttle commands but has no virtual loco. [Source: memory project_throttle_simulator_blindspot, project_nce_open_loop]
- Only `python_code/` and `_bmad-output/` are writable; all `.jmri` dirs and shared JMRI assets are read-only. [Source: memory feedback_writable_paths]
- Always drive Python tooling through `uv run --no-sync <tool>`. Both `ruff check` and `ruff format --check` are CI gates; keep this story file markdownlint-clean. [Source: memory feedback_use_uv, feedback_ruff_format_gate, feedback_polish_matters]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (1M context)

### Debug Log References

- Gates (all `uv run --no-sync`): `ruff check` → All checks passed; `ruff format --check` → 74 files already formatted; `mypy --strict src/pyjmri` → Success, no issues in 22 source files; `mypy --strict examples/capability_aware_startup.py` → Success; `pytest -m "not integration"` → **661 passed / 27 deselected** (baseline at story start 636/26; +25 new tests across three new files).
- Fixture reality check: every entry in `roster.json` carries `isLongAddress: true` (even low addresses like 41), so a "short-address roster entry" cannot be assumed — the address-hit test was adjusted to read addressing off whatever entry is first rather than requiring a short one. The short/long *convention* fallback is exercised separately via absent addresses derived from the fixture.
- One ruff RUF002 (en-dash in a docstring) caught in `roster.py` and fixed to a hyphen; the example needed two E501 fixes + a `ruff format` pass.
- **Live integration run against the basement layout (`localhost:12080`): `pytest tests/integration/test_discovery.py -m integration` → 4 passed (0.49s)**, including the new `test_throttle_for_entry_acquires_on_simulator` (acquires a throttle derived from a roster entry, `set_speed(0.0)`, releases — plumbing only).

### Completion Notes List

- **`classify_capability` + `Capability` + `firable_startup_functions`** added to `roster.py`. Classification reads ONLY `function_labels` (proven by a test where `decoder_family="ESU LokSound 5"` with all-`None` labels still classifies motor-only). `_SOUND_KEYWORDS` is the auditable, label-based vocabulary. `firable_startup_functions` filters to the throttle-commandable `[0, 28]` range so an F29+ sound label is recognised but never passed to `set_function` (which would raise `ValueError`).
- **`Client.throttle_for_entry(target, *, roster=None, long=None)`** is a synchronous factory mirroring `throttle()` — returns an unacquired `Throttle`, so `async with jmri.throttle_for_entry(loco) as t:` works. Resolution: a `RosterEntry` is used directly; a name/address resolves against `roster=` else the cached `self._roster`. **Chosen error for the rosterless/unresolvable name: `LayoutEntityNotFound`** (one type for both name-miss and no-roster, documented in the docstring and Dev Notes). The int path never raises — an unknown/rosterless address warns and drives with the `>127⇒long` convention; `long=` overrides everywhere. A `bool` target is rejected with `TypeError` (bool-is-int guard).
- **`discover_roster()` now caches its result** on `self._roster` (both populated and empty/graceful-degrade paths) so the convenience path works after one discovery; no other discover_roster behavior changed.
- **`examples/capability_aware_startup.py`** drives the same flow for a sound loco, a motor-only loco, and an un-catalogued address (FR55 warn-and-drive). Imports only top-level `pyjmri`; passes `mypy --strict`; documents the split simulator/hardware success criterion.
- **Exports:** `Capability`, `classify_capability`, `firable_startup_functions` added to `roster.py` and top-level `__init__.py` `__all__` (ruff-verified ordering). `firable_startup_functions` is a small public helper sanctioned by the story Dev Notes so the firable-selection is unit-testable and reusable by the example.
- **25 new tests** across `test_roster_capability.py` (10), `test_throttle_for_entry.py` (12), `test_capability_startup.py` (3), plus 1 integration smoke. No hardcoded fleet facts — every expected value is derived from the parsed fixture and probes are pinned by `next(...)` attribute filter.
- Scope respected: `_parsing.py`, `_codes.py`, `layout.py`, `throttle.py`, `operations.py`, and the eight layout entity modules untouched. `roster_catalog.py`, the read-only surface test, the docs section, and the v1.2 release remain Story 9.4. Epics 1–8 behavior unchanged.

### File List

- `python_code/src/pyjmri/roster.py` — UPDATED: `Capability`, `_SOUND_KEYWORDS`, `classify_capability`, `firable_startup_functions`; `__all__` extended.
- `python_code/src/pyjmri/client.py` — UPDATED: `self._roster` cache in `__init__`; `discover_roster()` caches its result (+ docstring); new `throttle_for_entry()`; `LayoutEntityNotFound` import added.
- `python_code/src/pyjmri/__init__.py` — UPDATED: re-export `Capability`, `classify_capability`, `firable_startup_functions` + `__all__`.
- `python_code/examples/capability_aware_startup.py` — NEW: FR59 capability-aware startup example.
- `python_code/tests/unit/test_roster_capability.py` — NEW: 10 classification + firable-helper tests.
- `python_code/tests/unit/test_throttle_for_entry.py` — NEW: 12 resolution tests.
- `python_code/tests/unit/test_capability_startup.py` — NEW: 3 startup-command-set plumbing tests.
- `python_code/tests/integration/test_discovery.py` — UPDATED: added `test_throttle_for_entry_acquires_on_simulator` (integration smoke).

## Change Log

| Date | Change |
|------|--------|
| 2026-06-17 | Story 9.3 drafted (create-story): `Client.throttle_for_entry(entry\|name\|address)` sync factory over the existing throttle path (resolution via `roster=` arg or a new `self._roster` cache populated by `discover_roster()`; int-miss warn-and-drive with JMRI-convention addressing, name-miss raises `LayoutEntityNotFound`); `classify_capability(RosterEntry) -> Capability` pure function reading function labels not decoder strings, motor-only fallback; `examples/capability_aware_startup.py` (FR59) with the F28-firable guard and split simulator/hardware success criterion. Scope fenced to throttle + classification + capability-startup example; `roster_catalog.py`, read-only surface test, docs, and v1.2 release deferred to Story 9.4. Status → ready-for-dev. |
| 2026-06-17 | Story 9.3 implemented (dev-story): `Capability` + `classify_capability` + `firable_startup_functions` in `roster.py` (labels-only, motor-only fallback, F0-F28 firable filter); `Client.throttle_for_entry()` sync factory with `self._roster` cache (populated by `discover_roster()`), FR55 int warn-and-drive + name-raise (chosen error `LayoutEntityNotFound`), `bool` rejected; `examples/capability_aware_startup.py` (FR59); 25 new unit tests + 1 integration smoke. All gates green (661 passed / 27 deselected; ruff check + format clean; mypy --strict src + example clean). Live integration run against the basement layout: 4 passed. Status → review. |
