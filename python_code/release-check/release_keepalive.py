import argparse
import asyncio

from pyjmri import Client


async def main(dcc: int, url: str) -> None:
    async with Client(url) as jmri:
        layout = await jmri.discover()
        async with layout.throttle(dcc, long=True) as t:
            await t.set_speed(0.0, forward=True)
            await asyncio.sleep(30)  # silent hold (2x default keepalive interval)
            await t.set_speed(0.1, forward=True)  # does the loco move now?
            await asyncio.sleep(5)
            await t.set_speed(0.0, forward=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dcc", type=int, default=5327)
    p.add_argument("--url", type=str, default="http://localhost:12080")
    args = p.parse_args()
    asyncio.run(main(args.dcc, args.url))
