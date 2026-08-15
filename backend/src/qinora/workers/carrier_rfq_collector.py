import asyncio

from qinora.application import CollectCarrierRfqsCommand
from qinora.interfaces.http.container import build_container


async def collect_carrier_rfqs(window_hours: int = 24) -> None:
    container = build_container()
    await container.carrier_rfq_collector.run(CollectCarrierRfqsCommand(window_hours=window_hours))


def main() -> None:
    asyncio.run(collect_carrier_rfqs())


if __name__ == "__main__":
    main()
