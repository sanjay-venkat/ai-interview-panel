import asyncio
import time

from app.evaluation.extractor import Signals, extract_claims, extract_signals, keyword_hits
from app.memory.conversation_state import ConversationState, FloorDecision, PanelistRuntime, TopicSignal, TranscriptLine

RECENT_SPEAK_PENALTY = 0.6
RECENT_SPEAK_WINDOW_TURNS = 1
EPOCH_WINDOW_SECONDS = 3.5


def _relevance(panelist: PanelistRuntime, signals: Signals) -> float:
    return min(1.0, 0.25 * keyword_hits(signals.lower_text, panelist.keywords))


def _weakness_score(panelist: PanelistRuntime, signals: Signals) -> float:
    """Generic proxy for 'this panelist should press harder': the candidate
    touched this panelist's domain but hedged, or answered thinly. This
    replaces per-agent-id special-cased logic (the old hiring_manager rule
    checked a DIFFERENT panelist's keyword hits) so it works uniformly for
    an arbitrary, role-defined panel — the trade-off is losing that one
    cross-panelist nuance, which doesn't generalize to N dynamic panelists
    anyway."""
    hits = keyword_hits(signals.lower_text, panelist.keywords)
    score = 0.0
    if signals.hedging and hits > 0:
        score += 0.5
    if hits > 0 and signals.word_count < 15:
        score += 0.3
    return min(1.0, score)


def _recent_penalty(state: ConversationState, agent_id: str) -> float:
    last_turn = state.agent_last_spoke_turn.get(agent_id)
    if last_turn is None:
        return 0.0
    if state.turn_count - last_turn <= RECENT_SPEAK_WINDOW_TURNS:
        return RECENT_SPEAK_PENALTY
    return 0.0


def score_agent(state: ConversationState, panelist: PanelistRuntime, signals: Signals) -> dict:
    relevance = _relevance(panelist, signals)
    weakness = _weakness_score(panelist, signals)
    urgency = 0.5 * relevance + 0.5 * weakness
    penalty = _recent_penalty(state, panelist.id)
    final = relevance + weakness + urgency - penalty
    return {
        "relevance": round(relevance, 3),
        "weakness": round(weakness, 3),
        "urgency": round(urgency, 3),
        "recent_penalty": round(penalty, 3),
        "final": round(final, 3),
    }


def decide_floor(state: ConversationState, candidate_text: str) -> FloorDecision:
    """Deterministic arbitration. No LLM call in this hot path — keeps the
    'who speaks next' decision fast (<20ms) and independent of API latency.
    Runs exactly once per turn epoch, so this is also the single place we
    log the candidate's line — avoids double-logging from both agents'
    independent transcripts of the same utterance."""
    state.transcript.append(TranscriptLine(speaker="candidate", text=candidate_text))
    signals = extract_signals(candidate_text)

    all_keywords: set[str] = set()
    for p in state.panel:
        all_keywords.update(p.keywords)
    for topic in all_keywords:
        if topic in signals.lower_text:
            t = state.topics.setdefault(topic, TopicSignal())
            t.mentions += 1
            t.confidence = min(1.0, t.confidence + 0.15)

    for claim in extract_claims(candidate_text):
        if claim not in state.claims:
            state.claims.append(claim)

    agent_order = state.panel_ids()
    scores = {p.id: score_agent(state, p, signals) for p in state.panel}

    # First len(panel) turns are forced, one per panelist in order, so every
    # interviewer is guaranteed to speak early in the demo rather than leaving
    # it to chance if the candidate's opening answer happens to score
    # entirely toward one panelist.
    if state.turn_count < len(agent_order):
        winner = agent_order[state.turn_count]
    else:
        best = max(scores.items(), key=lambda kv: kv[1]["final"])
        # Require a minimum signal so agents don't jump in on pure small talk.
        winner = best[0] if best[1]["final"] > 0.15 else None
        if winner is None:
            # Round-robin fallback so the interview keeps moving: whichever
            # panelist has gone longest without a turn speaks next.
            winner = min(agent_order, key=lambda a: state.agent_last_spoke_turn.get(a, -1))

    weakness = scores[winner]["weakness"] if winner else 0
    if weakness > 0.4:
        reason = f"{winner} detected a weak/hedged claim"
    elif winner:
        reason = f"{winner} has topical relevance"
    else:
        reason = "no agent met the speaking threshold"

    return FloorDecision(winner=winner, scores=scores, reason=reason)


async def resolve_decision(state: ConversationState, agent_id: str, candidate_text: str) -> FloorDecision:
    """Every interviewer agent calls this once it sees a new candidate
    message in its own conversation history. Because each agent runs an
    independent ASR pipeline, their transcripts of the same utterance won't
    match exactly — so instead of deduping by text, whichever call arrives
    first opens a short "epoch" and computes the decision; the others,
    arriving within EPOCH_WINDOW_SECONDS, reuse it instead of computing their
    own (possibly disagreeing) decision.

    Note: `decide_floor` is fully synchronous and asyncio.Lock's fast path
    doesn't yield when uncontended, so the first caller can run this whole
    function to completion before the event loop ever switches to the
    second caller. That means "is there a pending future to join" is NOT a
    reliable signal by itself — the first call may have already finished and
    cleared it. `current_epoch_consumed_by` is what actually makes this
    correct: an agent reuses the cached decision as long as it personally
    hasn't consumed it yet, regardless of whether the computation is still
    in flight or already done.
    """
    async with state.lock:
        now = time.time()
        epoch_fresh = now - state.current_epoch_started_at < EPOCH_WINDOW_SECONDS

        if epoch_fresh and state.current_epoch_decision is not None and agent_id not in state.current_epoch_consumed_by:
            state.current_epoch_consumed_by.add(agent_id)
            return state.current_epoch_decision

        if epoch_fresh and state.current_epoch_future is not None and not state.current_epoch_future.done():
            fut = state.current_epoch_future
            compute_here = False
        else:
            fut = asyncio.get_event_loop().create_future()
            state.current_epoch_future = fut
            state.current_epoch_started_at = now
            state.current_epoch_decision = None
            state.current_epoch_consumed_by = {agent_id}
            compute_here = True

    if not compute_here:
        decision = await fut
        async with state.lock:
            state.current_epoch_consumed_by.add(agent_id)
        return decision

    decision = decide_floor(state, candidate_text)

    async with state.lock:
        state.current_epoch_decision = decision
        state.turn_count += 1
        if decision.winner:
            state.agent_last_spoke_turn[decision.winner] = state.turn_count
            state.agent_last_spoke_ts[decision.winner] = time.time()
        fut2 = state.current_epoch_future
        state.current_epoch_future = None
        if fut2 and not fut2.done():
            fut2.set_result(decision)

    return decision
