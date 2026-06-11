from dataclasses import dataclass

from qinora.application.ports import OutboundMailer, OutboundReplyRepository
from qinora.application.read_models import OutboundReplyRecord


@dataclass(frozen=True)
class ProcessOutboundQueueCommand:
    limit: int = 10


@dataclass(frozen=True)
class ProcessOutboundQueueResult:
    sent: tuple[OutboundReplyRecord, ...]
    failed: tuple[OutboundReplyRecord, ...]


class ProcessOutboundQueueUseCase:
    def __init__(
        self,
        repository: OutboundReplyRepository,
        mailer: OutboundMailer,
    ) -> None:
        self._repository = repository
        self._mailer = mailer

    async def execute(self, command: ProcessOutboundQueueCommand) -> ProcessOutboundQueueResult:
        queued = await self._repository.next_queued(command.limit)
        sent: list[OutboundReplyRecord] = []
        failed: list[OutboundReplyRecord] = []

        for reply in queued:
            try:
                await self._mailer.send(reply)
            except Exception as error:
                failed.append(await self._repository.mark_failed(reply.id, str(error)))
            else:
                sent.append(await self._repository.mark_sent(reply.id))

        return ProcessOutboundQueueResult(sent=tuple(sent), failed=tuple(failed))
