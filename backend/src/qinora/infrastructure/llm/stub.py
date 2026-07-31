"""Deterministic fallback for RequestParsingLLM - no network, no credentials.

This is what LLM_PROVIDER=stub (the default) wires up. It exists so the app
runs out of the box and so request_parsing_agent has a real, testable
implementation to exercise before Azure OpenAI credentials are added -
it always reports low confidence and flags every field as missing, which
correctly routes everything to human review rather than silently creating
requests from unparsed text.
"""

from __future__ import annotations

from qinora.application.read_models import ParsedTransportRequestDraft


class StubRequestParsingLLM:
    async def parse(self, *, raw_text: str) -> ParsedTransportRequestDraft:
        _ = raw_text
        return ParsedTransportRequestDraft(
            mode="ftl",
            origin="",
            destination="",
            cargo=(),
            loading_time=None,
            unloading_time=None,
            confidence=0.0,
            missing_fields=(
                "mode",
                "origin",
                "destination",
                "cargo",
                "loading_time",
                "unloading_time",
            ),
        )
