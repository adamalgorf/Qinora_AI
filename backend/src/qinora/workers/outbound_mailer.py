import asyncio

from qinora.application import ProcessOutboundQueueCommand
from qinora.interfaces.http.container import build_container


async def process_email_queue(limit: int = 10) -> None:
    container = build_container()
    await container.process_outbound_queue.execute(ProcessOutboundQueueCommand(limit=limit))


def main() -> None:
    asyncio.run(process_email_queue())


if __name__ == "__main__":
    main()
