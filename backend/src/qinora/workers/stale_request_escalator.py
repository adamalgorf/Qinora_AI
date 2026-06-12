import asyncio

from qinora.application import EscalateStaleRequestsCommand
from qinora.interfaces.http.container import build_container


async def escalate_stale_requests(max_age_hours: int = 24) -> None:
    container = build_container()
    await container.stale_request_escalator.run(
        EscalateStaleRequestsCommand(max_age_hours=max_age_hours)
    )


def main() -> None:
    asyncio.run(escalate_stale_requests())


if __name__ == "__main__":
    main()
