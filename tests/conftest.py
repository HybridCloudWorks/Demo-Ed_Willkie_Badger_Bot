"""Shared test helpers: a scripted stand-in for Gemini so tests need no API key."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types


class ScriptedLlm(BaseLlm):
    """Pretends to be Gemini.

    Turn 1: asks to call look_up_school_info with the student's question.
    Turn 2: answers using whatever the tool returned (or the fallback line).
    """

    model: str = "scripted-test-model"
    seen_requests: list[LlmRequest] = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.seen_requests.append(llm_request)
        last = llm_request.contents[-1]
        tool_result = next(
            (p.function_response for p in last.parts if p.function_response), None
        )
        if tool_result is None:
            question = "".join(p.text or "" for p in last.parts)
            part = types.Part.from_function_call(
                name="look_up_school_info", args={"question": question}
            )
        else:
            data = tool_result.response or {}
            if data.get("found"):
                titles = ", ".join(r["title"] for r in data["results"])
                part = types.Part.from_text(text=f"Found it. {titles}")
            else:
                part = types.Part.from_text(
                    text="I couldn't find that on the Ed Willkie Middle School website."
                )
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.fixture
def scripted_llm():
    llm = ScriptedLlm()
    llm.seen_requests = []
    return llm
