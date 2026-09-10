from dataclasses import dataclass

from qinora.application.ports import CaseNoteRepository
from qinora.application.read_models import CaseNoteRecord


@dataclass(frozen=True)
class AddCaseNoteCommand:
    request_id: str
    author: str
    body_text: str


class CaseNotesService:
    def __init__(self, repository: CaseNoteRepository) -> None:
        self._repository = repository

    async def add_note(self, command: AddCaseNoteCommand) -> CaseNoteRecord:
        return await self._repository.create_note(
            command.request_id,
            author=command.author,
            body_text=command.body_text,
        )
