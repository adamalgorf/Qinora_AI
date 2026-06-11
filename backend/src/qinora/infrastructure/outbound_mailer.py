from dataclasses import dataclass, field

from qinora.application.ports import OutboundMailer
from qinora.application.read_models import OutboundReplyRecord


@dataclass
class RecordingOutboundMailer(OutboundMailer):
    sent_messages: list[OutboundReplyRecord] = field(default_factory=list)

    async def send(self, reply: OutboundReplyRecord) -> None:
        self.sent_messages.append(reply)
