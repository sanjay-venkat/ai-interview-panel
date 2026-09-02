import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    DELIBERATING = "deliberating"
    COMPLETE = "complete"


@dataclass
class TopicSignal:
    score: float = 0.5
    confidence: float = 0.3
    mentions: int = 0


@dataclass
class TranscriptLine:
    speaker: str  # "candidate" | a panelist id (e.g. "p1", "p2", "p3")
    text: str
    ts: float = field(default_factory=time.time)


@dataclass
class FloorDecision:
    winner: Optional[str]  # panelist id or None if nobody should speak
    scores: dict
    reason: str


@dataclass
class PanelistRuntime:
    """One interviewer assembled for this specific session, from the
    RoleConfig picked at session start. `id` is positional ("p1".."p3") —
    it maps 1:1 to Agora RTC uid and TTS voice slot by index, regardless
    of what persona/title that slot holds for this role."""

    id: str
    title: str
    keywords: list[str]
    system_prompt_base: str  # static per-role part; per-turn state appended later
    greeting: Optional[str] = None  # only the first panelist gets one


@dataclass
class ConversationState:
    session_id: str
    candidate_name: str = "Candidate"
    role: str = "Software Engineer"
    role_key: str = "software_engineer"
    resume_text: str = ""
    channel: str = ""

    panel: list[PanelistRuntime] = field(default_factory=list)

    phase: Phase = Phase.IDLE
    topics: dict[str, TopicSignal] = field(default_factory=dict)
    claims: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    questions_asked: list[str] = field(default_factory=list)
    transcript: list[TranscriptLine] = field(default_factory=list)

    current_speaker: str = "candidate"
    agent_last_spoke_ts: dict[str, float] = field(default_factory=dict)
    agent_last_spoke_turn: dict[str, int] = field(default_factory=dict)
    turn_count: int = 0

    # Each interviewer agent runs its own independent ASR pipeline against the
    # same candidate audio, so their transcripts of "the same" utterance won't
    # match byte-for-byte. We dedupe by time window (an "epoch") instead of by
    # exact text: whichever agent's proxy call arrives first opens the epoch
    # and computes the decision; the other, arriving within EPOCH_WINDOW
    # seconds, reuses it instead of computing its own (possibly disagreeing)
    # decision. See floor_controller.resolve_decision.
    current_epoch_future: Optional[asyncio.Future] = None
    current_epoch_started_at: float = 0.0
    current_epoch_decision: Optional[FloorDecision] = None
    current_epoch_consumed_by: set = field(default_factory=set)

    latency_ms: dict[str, float] = field(default_factory=dict)
    scorecard: Optional[dict] = None

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    subscribers: list[asyncio.Queue] = field(default_factory=list)

    def panelist(self, agent_id: str) -> Optional[PanelistRuntime]:
        return next((p for p in self.panel if p.id == agent_id), None)

    def panel_ids(self) -> list[str]:
        return [p.id for p in self.panel]

    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "candidate_name": self.candidate_name,
            "role_title": self.role,
            "panel": [{"id": p.id, "title": p.title} for p in self.panel],
            "phase": self.phase.value,
            "current_speaker": self.current_speaker,
            "turn_count": self.turn_count,
            "topics": {k: v.__dict__ for k, v in self.topics.items()},
            "weaknesses": self.weaknesses,
            "claims": self.claims,
            "transcript": [
                {"speaker": t.speaker, "text": t.text, "ts": t.ts}
                for t in self.transcript[-30:]
            ],
            "latency_ms": self.latency_ms,
            "scorecard": self.scorecard,
        }


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, ConversationState] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        candidate_name: str,
        role: str,
        role_key: str,
        resume_text: str,
        channel: str,
        panel: list[PanelistRuntime],
    ) -> ConversationState:
        session_id = str(uuid.uuid4())[:8]
        state = ConversationState(
            session_id=session_id,
            candidate_name=candidate_name,
            role=role,
            role_key=role_key,
            resume_text=resume_text,
            channel=channel,
            panel=panel,
        )
        async with self._lock:
            self._sessions[session_id] = state
        return state

    def get(self, session_id: str) -> Optional[ConversationState]:
        return self._sessions.get(session_id)

    async def remove(self, session_id: str):
        async with self._lock:
            self._sessions.pop(session_id, None)


session_store = SessionStore()


def subscribe(state: ConversationState) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    state.subscribers.append(q)
    return q


def unsubscribe(state: ConversationState, q: asyncio.Queue):
    if q in state.subscribers:
        state.subscribers.remove(q)


def broadcast(state: ConversationState):
    snapshot = state.snapshot()
    for q in list(state.subscribers):
        if q.full():
            continue
        q.put_nowait(snapshot)
