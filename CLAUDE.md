# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

This is a JMRI (Java Model Railroad Interface) **user configuration repository** for Mike Dean's basement N-scale model railroad. It is NOT the JMRI application source code. JMRI itself is installed separately. This repo version-controls layout profiles, locomotive roster data, and Jython automation scripts, and can be cloned to other machines (including Raspberry Pi boards).

## Per-machine Setup

After cloning on a new machine, configure the JMRI timestamp filter once (see `GIT_SETUP.md`). Without it, `roster.xml` shows spurious diffs every time JMRI saves. The filter rules are tracked in `.gitattributes`; the filter *definitions* live in per-machine git config and are not committed.

## Repository Layout

```
~/JMRI/                              # Git root
├── Basement_Revised_2024.jmri/      # Main layout profile (active development)
│   ├── profile/<UUID>/              # Machine-specific overrides (one per host)
│   └── March2026Settings.xml        # Currently active panel file
├── Decoder_TestTrack.jmri/          # Decoder calibration testing profile
├── My_NCE_Simulator.jmri/           # Simulator profile (no hardware needed)
├── Programming_Track.jmri/          # Programming track profile
├── roster/                          # Shared locomotive roster (~45 locos + photos)
│   └── consist/                     # Consist definitions
├── jython/                          # Shared Jython scripts (~168 .py files)
├── roster.xml                       # Master roster index
├── roster.csv                       # CSV export of roster
├── README.md                        # Repo overview
└── GIT_SETUP.md                     # Per-machine git filter setup (required after cloning)
```

All profiles share a single `roster/` directory and a single `jython/` scripts directory. This is configured via `jmri-jmrit-roster.directory=home:JMRI/` in each profile's `profile.properties`.

## Profiles at a Glance

| Profile | Connection | Purpose |
|---|---|---|
| `Basement_Revised_2024.jmri` | NCE Simulator | Main layout, active development |
| `My_NCE_Simulator.jmri` | NCE Simulator | Hardware-free Jython work |
| `Decoder_TestTrack.jmri` | NCE USB (`cu.usbserial-0001`, 19200 baud) | Decoder calibration with real hardware |
| `Programming_Track.jmri` | NCE USB | Programming track with real hardware |

The connection type for each profile is set in its `profile/profile.xml`.

## JMRI Profile Structure

Each `.jmri` profile directory contains:
- `profile/profile.xml` — Connection config, startup actions (loads panel XML, starts WiThrottle on port 12090, web server on port 12080)
- `profile/profile.properties` — Preferences (roster path, LogixNG options, web server settings)
- `profile/<UUID>/` — Per-machine overrides (`profile.xml`, `profile.properties`, `user-interface.xml`). JMRI selects the matching UUID at startup, so different hosts can have different connection/UI prefs while sharing the layout config.
- `*Settings.xml` — Main panel/layout configuration file (sensors, turnouts, signals, blocks, layout editor geometry)
- `backupPanels/` — Timestamped automatic backups
- `signal/`, `throttle/`, `programmers/`, `resources/` — Per-profile preferences

## Panel File Versioning

`Basement_Revised_2024.jmri/` keeps multiple dated `*Settings.xml` files (e.g., `March2026Settings.xml`, `May2025Settings.xml`, `April2025Settings.xml`, `October2022Settings.xml`). Only one is active at a time — selected by the `enabled="yes"` `PerformFileModelXml` entry in `profile/profile.xml`; the others are present as `enabled="no"`. Older files are kept as in-tree rollback points; do not delete them without first checking which one is active.

## Panel XML Structure

The main `*Settings.xml` files are JMRI's serialized layout configuration, containing (in order):
1. **Sensors** — NCE sensors (`NS*`) and internal sensors (`IS*`)
2. **Turnouts** — NCE turnouts (`NT*`)
3. **Signal Heads / Signal Masts** — 12 each, CTC-style signaling
4. **Blocks** — 38 blocks for occupancy detection
5. **Sections** — none currently defined (the layout uses blocks, not Dispatcher/warrant sections)
6. **Layout Editor panel** — Track geometry, turnout positions, visual elements

JMRI system name conventions: prefix `N` = NCE hardware, `I` = internal; type letter: `S` = sensor, `T` = turnout, `B` = block.

## Layout Geography

The layout is divided into zones: **North** (zones 1-10, tracks 1-6, bypass), **South** (zones 1-7, tracks 1-4), **East** (zones 1-13), **West** (NW and SW sub-areas), and **Mountain**. Sensors and blocks follow this geographic naming scheme.

## Jython Scripts

The shared `jython/` directory mixes user-authored scripts with JMRI's bundled examples. The distinction matters when deciding what's safe to modify:

- **User-authored scripts** — filenames prefixed with `Mike` (e.g., `MikeMeasureMaxSpeeds.py`, `MikeStartATrain.py`). These are the user's own code; safe to read and modify on request.
- **Shipped examples** — everything else at the `jython/` root and most subdirectories (`ctc/`, `dccspecialties/`, `IoT/`, `Jynstruments/`, `javaone/`, `operations/`, `serialinput/`, `test/`) come from the JMRI distribution. Several have their own README files; some (e.g., `dccspecialties/`) explicitly say to copy before editing. Don't modify these in-place unless the user asks.
- **New scripts** — keep the `Mike` prefix when adding user scripts so the boundary stays clear.

Note: `jython/operations/` (shipped Jython for the Operations module) is separate from any profile-local `operations/` directory.

## Working with XML Files

- Panel XML files are generated by JMRI. **Prefer making changes through the JMRI GUI** when possible.
- When editing XML directly: preserve schema references, maintain element ordering, and follow JMRI system name conventions.
- JMRI auto-creates `.bak` files; these are gitignored.
- `Basement_Revised_2024.jmri/operations/` holds JMRI Operations module data (train manifests, cars, locations) — distinct from `jython/operations/`. JMRI auto-backs it up to `operations/autoBackups/`.

## Git Conventions

- Primary branch: `master`, pushed to GitHub (`mdean77a/JMRI`).
- Commit messages are informal, describing layout configuration changes.
- `.gitignore` excludes: `.bak` files, `.DS_Store`, `backupPanels/*.xml`, `user-interface.xml`, `profile.properties`, and various preference XMLs.
