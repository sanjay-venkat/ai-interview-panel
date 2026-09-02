import uuid

from app.agents.prompts import GREETINGS, build_system_prompt
from app.agora.convoai_client import AGENT_UIDS, CANDIDATE_UID, join_agent, leave_agent
from app.agora.rtc_token import build_rtc_token
from app.agora.tts_vendors import validate_tts_config
from app.config import settings
from app.evaluation.scoring import deliberate
from app.memory.conversation_state import ConversationState, Phase, session_store

# session_id -> {agent_id: agora_agent_id}
_active_agents: dict[str, dict[str, str]] = {}


async def start_session(candidate_name: str, role: str) -> dict:
    # Fail fast on a misconfigured TTS vendor (missing key, wrong voice id
    # env var) instead of joining two agents that will then fail silently
    # partway through a live demo.
    validate_tts_config()

    channel = f"interview-{uuid.uuid4().hex[:10]}"
    state = await session_store.create(candidate_name, role, channel)
    state.channel = channel
    state.phase = Phase.ACTIVE

    agent_ids: dict[str, str] = {}
    for agent_id in ("technical_lead", "hiring_manager"):
        system_prompt = build_system_prompt(agent_id, state)
        agora_agent_id = await join_agent(
            agent_id, state.session_id, channel, system_prompt, GREETINGS[agent_id]
        )
        agent_ids[agent_id] = agora_agent_id
    _active_agents[state.session_id] = agent_ids

    return {
        "session_id": state.session_id,
        "app_id": settings.AGORA_APP_ID,
        "channel": channel,
        "candidate_uid": CANDIDATE_UID,
        "candidate_token": build_rtc_token(channel, CANDIDATE_UID),
        "agent_uids": AGENT_UIDS,
        "mock_mode": settings.effective_mock_mode,
    }


async def end_session(session_id: str) -> dict:
    state = session_store.get(session_id)
    if state is None:
        raise ValueError("unknown session")

    state.phase = Phase.DELIBERATING
    for agora_agent_id in _active_agents.pop(session_id, {}).values():
        await leave_agent(agora_agent_id)

    scorecard = await deliberate(state)
    state.phase = Phase.COMPLETE
    return scorecard


def get_state(session_id: str) -> ConversationState | None:
    return session_store.get(session_id)
