# Git Setup

After cloning or pulling this repo on a new machine, run these two commands from the repo root to configure the JMRI timestamp filter:

```bash
git config filter.strip-jmri-timestamp.clean 'sed s/<!--Written by JMRI version .*/<!--Written by JMRI-->/'
git config filter.strip-jmri-timestamp.smudge cat
```

This prevents JMRI's automatic timestamp updates in `roster.xml` from showing up as git changes. The filter rule itself is already tracked in `.gitattributes`, but the filter definition is per-machine and must be set up manually.
