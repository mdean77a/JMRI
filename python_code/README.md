# pyjmri

Async Python client for the JMRI web server.

## Quickstart

`pyjmri` is an async Python client for the JMRI web server. It lets you drive a JMRI-controlled model railroad — turnouts, sensors, lights, throttles — from Python scripts using `async`/`await`, instead of JMRI's bundled Jython. In the next five minutes, you'll install the library, connect to a running JMRI instance, discover the layout, and flip a turnout.

### Prerequisites

- Python 3.11 or newer.
- JMRI 5.14 or later, running with its web server enabled at `http://localhost:12080`.
- A panel file open in JMRI with at least one turnout defined.

To verify JMRI's web server is up, open `http://localhost:12080/json/v5/version` in a browser — you should see a JSON envelope reporting the JSON API version.

### Install

[uv](https://docs.astral.sh/uv/) is recommended (it's the modern Python toolchain `pyjmri` is developed against); pip works as a universal fallback:

```bash
uv add pyjmri
```

```bash
pip install pyjmri
```

### Your first script

Save this as `quickstart.py` and run `python quickstart.py`:

```python
import asyncio
from pyjmri import Client, TurnoutState


async def main() -> None:
    async with Client() as jmri:
        layout = await jmri.discover()
        turnout = next(iter(layout.turnouts.values()))
        print(f"name={turnout.name} user_name={turnout.user_name} initial state={turnout.state.name}")
        target = TurnoutState.THROWN if turnout.state is TurnoutState.CLOSED else TurnoutState.CLOSED
        await turnout.set_state(target)
        print(f"final state={target.name}")


asyncio.run(main())  # in a Jupyter notebook, use: await main()
```

### What you should see

Two lines, with the exact values depending on your panel file:

```text
name=NT400 user_name=North Yard Lead initial state=CLOSED
final state=THROWN
```

The two states are intentionally opposite — the script reads the current state, then commands the opposite. Run it again and the values will swap. The `final state` line means JMRI accepted the command — see the Limitations section below for what "accepted" does and does not imply on NCE hardware. If `initial state=UNKNOWN` appears instead of `CLOSED` or `THROWN`, that is normal — JMRI reports `UNKNOWN` for any turnout not yet commanded in the current session.

### Try it in a notebook

The repo includes `explorepyjmri.ipynb`, a Jupyter notebook that walks through the same quickstart broken into separate cells — imports, logging setup, client creation, and the turnout flip. It's a convenient sandbox for poking at JMRI interactively without restarting a script every time.

To use it:

1. Open `explorepyjmri.ipynb` in Jupyter, VS Code, Cursor, or any other notebook-capable editor.
2. Select a kernel that has `pyjmri` installed (e.g., the `.venv` from `uv sync` in this directory).
3. Run the cells top-to-bottom. The logging-setup cell writes DEBUG output to `pyjmri.log` in the working directory; that file is gitignored.

Re-running the `await main()` cell will flip the same turnout back and forth, since the script always commands the opposite of the currently reported state.

## Migrating from Jython

*(filled in Epic 6 — Story 6.3)*

A table mapping common JMRI Jython idioms to their pyjmri equivalents will go here. See PRD FR41.

## Limitations

*(filled in Epic 6 — Story 6.2)*

A clear explanation of what the library can and cannot detect — open-loop NCE, no DCC feedback, no power control on this hardware — will go here. See PRD FR42.
