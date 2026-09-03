import asyncio
import time
import uuid

from app.agents.prompts import build_greeting, build_static_prompt, build_system_prompt
from app.agents.roles import get_role
from app.agora.convoai_client import CANDIDATE_UID, PANEL_UIDS, join_agent, leave_agent
from app.agora.rtc_token import build_rtc_token
from app.agora.tts_vendors import validate_tts_config
from app.config import settings
from app.evaluation.scoring import deliberate
from app.memory.conversation_state import ConversationState, PanelistRuntime, Phase, broadcast, session_store

MAX_PANEL_SIZE = len(PANEL_UIDS)

# Hard cap: the interview auto-evaluates and ends at 45 minutes regardless
# of anything else, win the candidate is fast or slow.
MAX_INTERVIEW_SECONDS = 45 * 60

# Early-finish heuristic: if every panelist has already had a real second
# turn (nobody's domain went unexplored) AND the candidate has substantively
# covered enough distinct topics (repeated, confident keyword hits rather
# than one passing mention), the panel is "satisfied" and wraps up early
# instead of running the full 45 minutes. This directly rewards a candidate
# who answers efficiently — the fewer turns it takes to reach this bar, the
# sooner the interview ends. It's a heuristic proxy, not a semantic judgment
# of answer quality; the 45-minute watchdog is the real backstop either way.
MIN_TURNS_PER_PANELIST_FOR_EARLY_END = 2
MIN_STRONG_TOPICS_FOR_EARLY_END = 5
STRONG_TOPIC_CONFIDENCE = 0.75
# However fast the candidate answers, the panel won't exit before this —
# an interview needs at least 30 minutes on the clock before "satisfied"
# is allowed to end it early.
MIN_SECONDS_BEFORE_EARLY_END = 30 * 60

# Short pause before actually disconnecting agents on an early/satisfied
# end, so the last thing spoken has a moment to finish playing out over
# Agora's TTS before we tear the channel down. Manual "End Interview" and
# the 45-minute cutoff skip this — those are explicit/hard stops.
EARLY_END_GRACE_SECONDS = 4.0

# session_id -> {agent_id: agora_agent_id}
_active_agents: dict[str, dict[str, str]] = {}
# session_id -> the 45-minute watchdog task, so it can be cancelled once a
# session ends any other way.
_watchdog_tasks: dict[str, asyncio.Task] = {}


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
    _watchdog_tasks[state.session_id] = asyncio.create_task(_time_limit_watchdog(state.session_id))

    return {
        "session_id": state.session_id,
        "app_id": settings.AGORA_APP_ID,
        "channel": channel,
        "candidate_uid": CANDIDATE_UID,
        "candidate_token": build_rtc_token(channel, CANDIDATE_UID),
        "role_title": role_config.role_title,
        "panel": [{"id": p.id, "title": p.title, "uid": PANEL_UIDS[i]} for i, p in enumerate(panel)],
        "mock_mode": settings.effective_mock_mode,
        "max_duration_seconds": MAX_INTERVIEW_SECONDS,
    }


async def _conclude(state: ConversationState, grace_seconds: float = 0.0) -> dict:
    """The single funnel that actually ends a session: leaves all agents and
    runs deliberation. Safe to call more than once / concurrently — the
    lock-guarded phase check means only the first caller (manual end, the
    45-minute watchdog, or the early-satisfaction check) does anything."""
    async with state.lock:
        if state.phase != Phase.ACTIVE:
            return state.scorecard or {}
        state.phase = Phase.DELIBERATING
    broadcast(state)

    if grace_seconds > 0:
        await asyncio.sleep(grace_seconds)

    for agora_agent_id in _active_agents.pop(state.session_id, {}).values():
        await leave_agent(agora_agent_id)

    scorecard = await deliberate(state)
    state.phase = Phase.COMPLETE
    broadcast(state)

    task = _watchdog_tasks.pop(state.session_id, None)
    if task and not task.done():
        task.cancel()
    return scorecard


async def end_session(session_id: str) -> dict:
    """Candidate-initiated end (the "End Interview" button) — immediate,
    no grace pause."""
    state = session_store.get(session_id)
    if state is None:
        raise ValueError("unknown session")
    return await _conclude(state)


async def _time_limit_watchdog(session_id: str):
    try:
        await asyncio.sleep(MAX_INTERVIEW_SECONDS)
    except asyncio.CancelledError:
        return
    state = session_store.get(session_id)
    if state is not None:
        await _conclude(state)


def _panel_satisfied(state: ConversationState) -> bool:
    if not state.panel:
        return False
    if time.time() - state.started_at < MIN_SECONDS_BEFORE_EARLY_END:
        return False
    if state.turn_count < len(state.panel) * MIN_TURNS_PER_PANELIST_FOR_EARLY_END:
        return False
    if any(state.agent_last_spoke_turn.get(p.id, 0) == 0 for p in state.panel):
        return False
    strong_topics = sum(1 for t in state.topics.values() if t.confidence >= STRONG_TOPIC_CONFIDENCE)
    return strong_topics >= MIN_STRONG_TOPICS_FOR_EARLY_END


async def maybe_conclude_early(state: ConversationState):
    """Called after every panelist turn finishes. If the panel has covered
    enough ground already, let the interview wrap up early instead of
    always running the full 45 minutes."""
    if state.phase != Phase.ACTIVE or not _panel_satisfied(state):
        return
    asyncio.create_task(_conclude(state, grace_seconds=EARLY_END_GRACE_SECONDS))


def get_state(session_id: str) -> ConversationState | None:
    return session_store.get(session_id)
