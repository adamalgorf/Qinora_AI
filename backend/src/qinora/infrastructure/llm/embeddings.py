"""TextEmbedder implementations for knowledge-base retrieval.

OpenAITextEmbedder uses a small embedding model at 256 dimensions - plenty
for ranking a company knowledge base, and small enough that every agent
call can load and score all of an agent's chunks in Python on both the
SQLite and Postgres drivers without a vector extension. StubTextEmbedder
(no credentials) returns None, and retrieval ranks by keywords instead.
"""

from collections.abc import Sequence

from openai import AsyncOpenAI

from qinora.infrastructure.llm.openai_client import require_openai_api_key
from qinora.infrastructure.settings import Settings

EMBEDDING_DIMENSIONS = 256
_BATCH_SIZE = 96
_TIMEOUT_SECONDS = 20.0


class StubTextEmbedder:
    async def embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        _ = texts
        return None


class OpenAITextEmbedder:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        if not texts:
            return []
        client = AsyncOpenAI(
            api_key=require_openai_api_key(self._settings),
            timeout=_TIMEOUT_SECONDS,
            max_retries=1,
        )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            response = await client.embeddings.create(
                model=self._settings.openai_embedding_model,
                input=[text or " " for text in texts[start : start + _BATCH_SIZE]],
                dimensions=EMBEDDING_DIMENSIONS,
            )
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return vectors
