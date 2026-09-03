import asyncio
import time

from app.evaluation.extractor import Signals, extract_claims, extract_signals, keyword_hits
from app.memory.conversation_state import ConversationState, FloorDecision, PanelistRuntime, TopicSignal, TranscriptLine

RECENT_SPEAK_PENALTY = 0.6
RECENT_SPEAK_WINDOW_TURNS = 1
EPOCH_WINDOW_SECONDS = 3.5

# Agora's ConvoAI engine calls our /llm/* endpoint once per VAD-detected
# turn boundary — but a candidate who pauses mid-thought (fillers, gathering
# words) can trigger several of these boundaries for what is really one
# continuous answer. Each such call arrives with Deepgram's running
# transcript of that answer so far, so consecutive calls show up as one
# candidate_text being a growing extension of the last. Without handling
# this, every fragment became its own duplicate, ever-growing transcript
# line AND its own floor decision — letting different agents jump in on
# incomplete sentences (the "I didn't catch that" / crossed-wires behavior).
# We instead merge same-utterance fragments into the existing transcript
# line and let no agent claim the floor until the candidate is done.
#
# 1.5s is deliberately short: it's meant to read as "they stopped talking,
# that's their answer" (a normal end-of-sentence pause), not "they're still
# mid-thought" — the separate MIN_THINKING_SECONDS grace period below is
# what actually protects the candidate from being cut off early; this
# window's job is just to decide when a pause means "done," not "wait."
CONTINUATION_WINDOW_SECONDS = 1.5

# Separately, Agora's VAD can end-point a turn on the candidate's very first
# few words (a false start, "um, so...", a breath) — technically a complete
# "turn" by Agora's definition, but not remotely a finished thought. Without
# a floor beneath it, whichever panelist scored highest would immediately
# ask its next question, barely giving the candidate a chance to speak.
# So after any panelist actually asks something, the floor stays closed for
# a minimum thinking window regardless of what Agora sends us in the
# meantime — the candidate's speech still gets transcribed as normal, we
# just won't let anyone respond to it until they've had a moment to think.
# Once this window passes with still no real answer, the panel is free to
# act on whatever's there (including proceeding on silence).
MIN_THINKING_SECONDS = 5.0


def _looks_like_continuation(prev_text: str, new_text: str) -> bool:
    prev = prev_text.strip().lower()
    new = new_text.strip().lower()
    if not prev or not new:
        return False
    return new.startswith(prev) or prev.startswith(new)


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
    last = state.transcript[-1] if state.transcript else None
    continuing = (
        last is not None
        and last.speaker == "candidate"
        and (time.time() - last.ts) < CONTINUATION_WINDOW_SECONDS
        and _looks_like_continuation(last.text, candidate_text)
    )
    if continuing:
        if len(candidate_text) >= len(last.text):
            last.text = candidate_text
        last.ts = time.time()
    else:
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

    thinking_time_left = (
        not continuing
        and state.last_panelist_turn_ts > 0
        and (time.time() - state.last_panelist_turn_ts) < MIN_THINKING_SECONDS
    )
    # Either kind of "not a real turn yet" skips floor selection the same
    # way — the candidate is still forming their answer, whether that's
    # because this call is a fragment of one utterance, or because they've
    # barely had time to start since the last question.
    hold_floor = continuing or thinking_time_left

    if hold_floor:
        winner = None
    elif state.turn_count < len(agent_order):
        # First len(panel) turns are forced, one per panelist in order, so
        # every interviewer is guaranteed to speak early in the demo rather
        # than leaving it to chance if the candidate's opening answer happens
        # to score entirely toward one panelist.
        winner = agent_order[state.turn_count]
    else:
        best = max(scores.items(), key=lambda kv: kv[1]["final"])
        # Require a minimum signal so agents don't jump in on pure small talk.
        winner = best[0] if best[1]["final"] > 0.15 else None
        if winner is None:
            # Round-robin fallback so the interview keeps moving: whichever
            # panelist has gone longest without a turn speaks next.
            winner = min(agent_order, key=lambda a: state.agent_last_spoke_turn.get(a, -1))

    if continuing:
        reason = "candidate still mid-answer (fragment merged into previous line)"
    elif thinking_time_left:
        reason = "giving the candidate a moment to think before the panel responds"
    else:
        weakness = scores[winner]["weakness"] if winner else 0
        if weakness > 0.4:
            reason = f"{winner} detected a weak/hedged claim"
        elif winner:
            reason = f"{winner} has topical relevance"
        else:
            reason = "no agent met the speaking threshold"

    return FloorDecision(winner=winner, scores=scores, reason=reason, continuation=hold_floor)


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
        if not decision.continuation:
            # A continuation isn't a real turn — don't advance turn_count or
            # burn a forced-order slot on a mid-answer fragment.
            state.turn_count += 1
            if decision.winner:
                state.agent_last_spoke_turn[decision.winner] = state.turn_count
                state.agent_last_spoke_ts[decision.winner] = time.time()
        fut2 = state.current_epoch_future
        state.current_epoch_future = None
        if fut2 and not fut2.done():
            fut2.set_result(decision)

    return decision
