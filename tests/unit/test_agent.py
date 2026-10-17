"""The agent must be wired to the school 'library' and told not to invent facts."""

import asyncio

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app import agent as agent_module


def test_agent_definition_is_grounded():
    assert agent_module.root_agent.name == "willkie_badger_ai"
    assert agent_module.look_up_school_info in agent_module.root_agent.tools
    text = agent_module.INSTRUCTION
    assert "couldn't find that on the Ed Willkie Middle School website" in text
    assert "ALWAYS call look_up_school_info" in text
    assert "Badgers" in text  # quick facts were injected
    assert agent_module.app.name == "app"


def test_tool_returns_school_pages():
    out = agent_module.look_up_school_info("What is the Willkie Way?")
    assert out["found"] and out["results"]


def _run(agent: Agent, question: str) -> str:
    async def go() -> str:
        sessions = InMemorySessionService()
        runner = Runner(agent=agent, app_name="test", session_service=sessions, auto_create_session=True)
        msg = types.Content(role="user", parts=[types.Part.from_text(text=question)])
        texts = []
        async for ev in runner.run_async(user_id="u", session_id="s1", new_message=msg):
            if ev.is_final_response() and ev.content:
                texts += [p.text for p in ev.content.parts if p.text]
        return "\n".join(texts)

    return asyncio.run(go())


def test_end_to_end_tool_call_with_scripted_model(scripted_llm):
    agent = Agent(
        name="willkie_badger_ai",
        model=scripted_llm,
        instruction=agent_module.INSTRUCTION,
        tools=[agent_module.look_up_school_info],
    )
    reply = _run(agent, "What is our school mascot?")
    assert reply.startswith("Found it.")
    # The model really received the rules and the tool declaration.
    first = scripted_llm.seen_requests[0]
    assert "look_up_school_info" in str(first.config.tools)
    assert "couldn't find" in str(first.config.system_instruction)


def test_unknown_question_falls_back(scripted_llm):
    agent = Agent(
        name="willkie_badger_ai",
        model=scripted_llm,
        instruction=agent_module.INSTRUCTION,
        tools=[agent_module.look_up_school_info],
    )
    reply = _run(agent, "What is the cafeteria pizza recipe on Tuesdays?")
    assert "couldn't find that on the Ed Willkie Middle School website" in reply
