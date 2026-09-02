import uuid

from app.agents.prompts import build_greeting, build_static_prompt, build_system_prompt
from app.agents.roles import get_role
from app.agora.convoai_client import CANDIDATE_UID, PANEL_UIDS, join_agent, leave_agent
from app.agora.rtc_token import build_rtc_token
from app.agora.tts_vendors import validate_tts_config
from app.config import settings
from app.evaluation.scoring import deliberate
from app.memory.conversation_state import ConversationState, PanelistRuntime, Phase, session_store

MAX_PANEL_SIZE = len(PANEL_UIDS)

# session_id -> {agent_id: agora_agent_id}
_active_agents: dict[str, dict[str, str]] = {}


def _build_panel(role_config) -> list[PanelistRuntime]:
    panelists = role_config.panelists[:MAX_PANEL_SIZE]
    panel: list[PanelistRuntime] = []
    for i, template in enumerate(panelists):
        panel.append(
            PanelistRuntime(
                id=f"p{i + 1}",
                title=template.title,
                keywords=template.keywords,
                system_prompt_base=build_static_prompt(template, role_config.role_title),
                greeting=build_greeting(template.title, role_config.role_title) if i == 0 else None,
            )
        )
    return panel


async def start_session(candidate_name: str, role_key: str, resume_text: str) -> dict:
    # Fail fast on a misconfigured TTS vendor (missing key, wrong voice id
    # env var) instead of joining agents that will then fail silently
    # partway through a live demo.
    validate_tts_config()

    role_config = get_role(role_key)
    panel = _build_panel(role_config)

    channel = f"interview-{uuid.uuid4().hex[:10]}"
    state = await session_store.create(
        candidate_name, role_config.role_title, role_config.key, resume_text.strip()[:6000], channel, panel
    )
    state.phase = Phase.ACTIVE

    agent_ids: dict[str, str] = {}
    for i, panelist in enumerate(panel):
        system_prompt = build_system_prompt(panelist.id, state)
        agora_agent_id = await join_agent(i, panelist.id, state.session_id, channel, system_prompt, panelist.greeting)
        agent_ids[panelist.id] = agora_agent_id
    _active_agents[state.session_id] = agent_ids

    return {
        "session_id": state.session_id,
        "app_id": settings.AGORA_APP_ID,
        "channel": channel,
        "candidate_uid": CANDIDATE_UID,
        "candidate_token": build_rtc_token(channel, CANDIDATE_UID),
        "role_title": role_config.role_title,
        "panel": [{"id": p.id, "title": p.title, "uid": PANEL_UIDS[i]} for i, p in enumerate(panel)],
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
