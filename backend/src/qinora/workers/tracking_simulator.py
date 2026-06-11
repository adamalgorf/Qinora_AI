import asyncio

from qinora.application import RunTrackingSimulatorCommand
from qinora.interfaces.http.container import build_container


async def run_tracking_simulator(limit: int = 10) -> None:
    container = build_container()
    await container.tracking_simulator.run(RunTrackingSimulatorCommand(limit=limit))


def main() -> None:
    asyncio.run(run_tracking_simulator())


if __name__ == "__main__":
    main()
