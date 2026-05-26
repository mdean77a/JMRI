import argparse
import asyncio

from pyjmri import Client


async def main(dcc: int, url: str) -> None:
    async with Client(url) as jmri:
        layout = await jmri.discover()
        async with layout.throttle(dcc, long=True) as t:
            await t.set_speed(0.3, forward=True)
            await asyncio.sleep(8)
            await t.set_speed(0.0, forward=True)  # stop before reversing
            await asyncio.sleep(3)
            await t.set_speed(0.3, forward=False)
            await asyncio.sleep(8)
            await t.set_function(0, True)
            await asyncio.sleep(3)
            await t.set_function(0, False)  # restore headlight state
            await t.set_speed(0.0, forward=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dcc", type=int, default=5327)
    p.add_argument("--url", type=str, default="http://localhost:12080")
    args = p.parse_args()
    asyncio.run(main(args.dcc, args.url))
