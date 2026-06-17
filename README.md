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
│   │   ├── 5e82e5b0-.../                (Machine-specific profile overrides)
│   │   │   ├── profile.xml
│   │   │   ├── profile.properties
│   │   │   └── user-interface.xml
│   │   └── d2a3bcad-.../                (Machine-specific profile overrides)
│   │       ├── profile.xml
│   │       ├── profile.properties
│   │       └── user-interface.xml
│   ├── March2026Settings.xml            (Current panel/layout configuration)
│   ├── May2025Settings.xml              (Previous panel versions)
│   ├── April2025Settings.xml
│   ├── October2022Settings.xml
│   ├── FebruaryPanelNewSectioning.xml
│   ├── backupPanels/                    (Timestamped automatic backups)
│   ├── signal/
│   │   └── WarrantPreferences.xml
│   ├── throttle/
│   │   ├── ThrottlesPreferences.xml
│   │   └── WiThrottlePreferences.xml
│   ├── programmers/                     (Custom decoder programmer configs)
│   ├── resources/                       (Custom icons, images)
│   └── roster.xml                       (Profile-local roster reference)
├── Decoder_TestTrack.jmri/              (Decoder calibration testing profile)
├── My_NCE_Simulator.jmri/              (Simulation without hardware)
├── Programming_Track.jmri/              (Programming track profile)
├── roster/                              (Shared locomotive roster)
├── jython/                              (Shared Jython scripts, ~250 files)
├── roster.xml                           (Master roster index)
└── roster.csv                           (CSV export of roster)
```

Each `.jmri` profile directory follows the same structure shown above for `Basement_Revised_2024.jmri`. The machine-specific UUID subdirectories under `profile/` allow different machines to have their own UI and connection preferences while sharing the same layout configuration.

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
