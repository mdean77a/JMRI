# JMRI

This repository contains my JMRI configurations. It provides version control of changes and the ability to clone settings to other computers, including Raspberry Pi boards (where DropBox is not practical).

I have multiple profiles for different purposes: a main layout, a programming track, a decoder calibration test track (based on Erich Whitney's project shown in Kansas City), and a simulation configuration for working with Jython without hardware attached.

All profiles share a single roster and a single jython scripts directory, avoiding the confused spaghetti of duplicated files I accumulated over several years of using JMRI.

## pyjmri — Async Python client

This repository also hosts [`pyjmri`](python_code/README.md), a modern async Python client for the JMRI web server. It lets you drive a JMRI-controlled layout — turnouts, sensors, lights, throttles — from Python scripts using `async`/`await`, over JMRI's JSON API, as a typed alternative to the bundled Jython scripts. It lives under [`python_code/`](python_code/) and is published to PyPI.

See [python_code/README.md](python_code/README.md) for the quickstart, installation, and migration guide.

## File Structure

```
JMRI/                                    (this git repository)
├── Basement_Revised_2024.jmri/          (Main layout profile - active development)
│   ├── profile/
│   │   ├── profile.xml                  (Connection config and startup actions)
│   │   ├── profile.properties           (Preferences: roster path, web server, LogixNG)
│   │   ├── 5e82e5b0-.../                (Per-machine profile overrides - one dir per host)
│   │   ├── 67cb7c83-.../
│   │   └── d2a3bcad-.../
│   ├── June2026Settings.xml             (Current panel/layout configuration - active)
│   ├── March2026Settings.xml            (Previous panel versions - in-tree rollback points)
│   ├── May2025Settings.xml
│   ├── April2025Settings.xml
│   ├── FebruaryPanelNewSectioning.xml
│   ├── October2022Settings.xml
│   ├── backupPanels/                    (Timestamped automatic backups)
│   ├── operations/                      (Operations module data - locations, trains, cars)
│   ├── signal/  throttle/  programmers/  resources/   (Per-profile preferences & assets)
│   └── roster.xml                       (Profile-local roster reference)
├── Decoder_TestTrack.jmri/              (Decoder calibration testing profile)
├── My_NCE_Simulator.jmri/              (Simulation without hardware)
├── Programming_Track.jmri/              (Programming track profile)
├── roster/                              (Shared locomotive roster, ~45 locos + photos)
├── jython/                              (Shared Jython scripts, ~250 files)
├── python_code/                         (pyjmri - async Python client; published to PyPI)
│   ├── src/pyjmri/                      (Library source)
│   ├── tests/                           (unit/ + integration/ test suites)
│   ├── examples/                        (Runnable example scripts)
│   ├── scripts/                         (Maintainer tooling, e.g. release smoke test)
│   ├── pyproject.toml  uv.lock          (Packaging + locked dependencies)
│   ├── README.md  CONTRIBUTING.md  RELEASES.md  SECURITY.md  LICENSE
│   └── explorepyjmri.ipynb             (Interactive quickstart notebook)
├── _bmad-output/                        (pyjmri planning & story artifacts - PRD, architecture, epics)
├── CLAUDE.md                            (Guidance for AI coding assistants)
├── GIT_SETUP.md                         (Per-machine git filter setup - required after cloning)
├── roster.xml                           (Master roster index)
└── roster.csv                           (CSV export of roster)
```

Each `.jmri` profile directory follows the same structure shown above for `Basement_Revised_2024.jmri`. The machine-specific UUID subdirectories under `profile/` (three hosts share this repo today) let each machine keep its own UI and connection preferences while sharing the same layout configuration. Only one `*Settings.xml` is active at a time — selected in `profile/profile.xml`; the others are kept as in-tree rollback points. The `python_code/` subtree is the `pyjmri` package and has its own [README](python_code/README.md), tests, and release tooling.

## Roster

The `roster/` directory is shared across all profiles. Each profile points to it via `jmri-jmrit-roster.directory=home:JMRI/` in its `profile.properties`, so there is only one copy of each locomotive definition regardless of which profile is active. The root-level `roster.xml` is the master index that JMRI uses to find individual locomotive files.

Each locomotive has an XML file containing its DCC address, decoder CV settings, function labels, and other configuration. Many also have a corresponding photo.

```
roster/
├── consist/
│   └── consist.xml                      (Consist definitions)
├── Big_Boy_4_8_8_4.xml                  (Locomotive definition - DCC/CV config)
├── BigBoySide.jpeg                      (Corresponding photo)
├── 1029_NW2_Switcher.xml
├── up1029.jpg
├── ... (45+ locomotive XML files and 20+ photos)
└── ...
```

See [GIT_SETUP.md](GIT_SETUP.md) for setup instructions when cloning to a new machine.
