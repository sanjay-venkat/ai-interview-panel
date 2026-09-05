import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agents.prompts import build_first_turn_intro, build_message_history, build_system_prompt
from app.llm.groq_client import stream_chat
from app.memory.conversation_state import TranscriptLine, broadcast, session_store
from app.orchestration.floor_controller import resolve_decision
from app.orchestration.session_manager import maybe_conclude_early

router = APIRouter()


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _chunk(completion_id: str, content: str | None, finish_reason: str | None) -> dict:
    delta = {"content": content} if content is not None else {}
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


async def _pass_stream(completion_id: str) -> AsyncIterator[str]:
    """This agent did not win the floor this turn. We must still return a
    valid OpenAI-style stream (Agora's engine expects one), but with no real
    content so the TTS vendor never synthesizes audio for it — effectively a
    silent 'pass'. `interruptable: true` ensures it never blocks the winning
    agent's turn. VERIFY LIVE: confirm empty content truly yields no TTS
    audio rather than an error — this is the one behavior undocumented by
    Agora that needs a Day-1 smoke test."""
    yield _sse({
        "id": completion_id,
        "object": "chat.completion.custom_metadata",
        "choices": [],
        "metadata": {"interruptable": True},
    })
    yield _sse(_chunk(completion_id, "", "stop"))
    yield "data: [DONE]\n\n"


async def _speak_stream(agent_id: str, session_id: str, candidate_text: str, completion_id: str) -> AsyncIterator[str]:
    state = session_store.get(session_id)
    already_spoke = any(t.speaker == agent_id for t in state.transcript)
    system_prompt = build_system_prompt(agent_id, state)
    # Every panelist except the first (which has a static greeting_message)
    # introduces itself dynamically on its own forced first turn.
    if state.panel and agent_id != state.panel[0].id and not already_spoke:
        system_prompt += build_first_turn_intro(state.panelist(agent_id).title)

    # The real cross-panel back-and-forth, not just this one isolated line —
    # this is what lets e.g. the Technical Lead see the question the Hiring
    # Manager just asked and how the candidate answered it. Falls back to
    # the raw candidate_text on the off chance the floor controller's
    # transcript merge hasn't landed yet.
    history = build_message_history(state, agent_id)
    if not history or history[-1]["role"] != "user":
        history.append({"role": "user", "content": candidate_text})

    start = time.time()
    first_token_at = None
    full_text = ""

    async for delta in stream_chat(system_prompt, history):
        if first_token_at is None:
            first_token_at = time.time()
            state.current_speaker = agent_id
            broadcast(state)
        full_text += delta
        yield _sse(_chunk(completion_id, delta, None))

    yield _sse(_chunk(completion_id, None, "stop"))
    yield "data: [DONE]\n\n"

    ttfa_ms = round(((first_token_at or time.time()) - start) * 1000, 1)
    state.latency_ms[agent_id] = ttfa_ms
    state.questions_asked.append(full_text.strip())
    state.transcript.append(TranscriptLine(speaker=agent_id, text=full_text.strip()))
    state.current_speaker = "candidate"
    state.last_panelist_turn_ts = time.time()
    broadcast(state)
    await maybe_conclude_early(state)


@router.post("/llm/{agent_id}/{session_id}/chat/completions")
async def llm_proxy(agent_id: str, session_id: str, request: Request):
    state = session_store.get(session_id)
    if state is None:
        raise HTTPException(404, "unknown session_id")

    if state.panelist(agent_id) is None:
        raise HTTPException(400, "unknown agent_id")

    body = await request.json()
    messages = body.get("messages", [])
    user_messages = [m for m in messages if m.get("role") == "user"]
    if not user_messages:
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        return StreamingResponse(_pass_stream(completion_id), media_type="text/event-stream")

    candidate_text = user_messages[-1].get("content", "")

    decision = await resolve_decision(state, agent_id, candidate_text)
    broadcast(state)

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    if decision.winner == agent_id:
        return StreamingResponse(
            _speak_stream(agent_id, session_id, candidate_text, completion_id),
            media_type="text/event-stream",
        )
    return StreamingResponse(_pass_stream(completion_id), media_type="text/event-stream")
