import asyncio
import logging
import re
import time
from typing import Optional

from app.evaluation.extractor import Signals, extract_claims, extract_signals, keyword_hits
from app.memory.conversation_state import ConversationState, FloorDecision, PanelistRuntime, TopicSignal, TranscriptLine

logger = logging.getLogger(__name__)

RECENT_SPEAK_PENALTY = 0.6
RECENT_SPEAK_WINDOW_TURNS = 1

# Agora's ConvoAI engine calls our /llm/* endpoint once per VAD-detected
# turn boundary, and Agora's own VAD decides when a "turn" ends -- often on
# a pause well short of the candidate actually being finished (in practice,
# as short as ~1 second). Earlier versions of this file tried to detect
# "is this still the same answer" by checking whether a new call's text was
# a growing, textually-overlapping extension of the previous one -- but
# that assumption doesn't hold up: once Agora's VAD ends a turn on a pause,
# the NEXT call's text is often a completely fresh, disjoint fragment (the
# candidate's next few words, not a superset of what came before), so a
# text-prefix check can never recognize it as a continuation, no matter how
# generous the time window is made.
#
# The actual fix is to stop trying to decide the instant any single call
# arrives. Every candidate utterance is buffered in state.pending_fragments;
# each new call just extends that buffer and resets the silence clock. Only
# once SILENCE_CONFIRM_SECONDS of genuine quiet has passed -- no candidate
# speech from ANY of the three agents' independent ASR pipelines -- does
# the panel actually commit to a floor decision, using every fragment
# collected since the panel's last turn (see _reconstruct_pending_text).
# This is the one signal that reliably distinguishes "they paused to
# think" from "they're done," regardless of how Agora slices the
# underlying speech into turns.
SILENCE_CONFIRM_SECONDS = 3.0

# Separately: after a panelist actually asks something, the panel shouldn't
# jump back in the instant the candidate goes quiet for SILENCE_CONFIRM_
# SECONDS if that's only a second or two into their answer (e.g. "let me
# think..." followed by a real pause to gather their thoughts). So a floor
# decision also can't finalize until at least this long has passed since
# the panel's last turn, on top of the silence check above.
MIN_THINKING_SECONDS = 5.0

# Hard ceiling on how long a single pending answer can be buffered before
# the panel is FORCED to finalize, no matter what. Without this, any bug
# (or any unexpected pattern of activity that keeps resetting the silence
# clock) could stall the debounce loop forever -- and because every one of
# the three agents' HTTP calls is awaiting the same shared decision, that
# would silently freeze the entire panel for the rest of the interview,
# exactly the "stopped and not going to next" failure this exists to rule
# out.
MAX_PENDING_WAIT_SECONDS = 25.0

# Independently of all the above: each of the three panelists runs its own
# ASR pipeline, and under real network/API latency one can simply be much
# slower than the others (not visible in a backend-only mock smoke test --
# only once real multi-agent audio was involved). If a straggler's call for
# an utterance the panel has ALREADY responded to arrives well after the
# fact, it must never be treated as a new answer -- it's just merged into
# the historical line it belongs to. Bounded to a generous window since a
# genuine straggler can lag many seconds behind.
STALE_ANSWER_WINDOW_SECONDS = 25.0

# How similar two pieces of text need to be (as a fraction of the shorter
# one's words found in the longer one) to be treated as "the same
# utterance, possibly re-transcribed" rather than genuinely different
# content. A strict startswith() check -- what this used to be -- breaks on
# the small revisions real ASR makes between calls for what is really one
# utterance (Deepgram/Agora commonly firms up punctuation or a word choice
# as more audio comes in, e.g. "...and sorry." becoming "...and sorry? can
# you go to the next", where the character right after "sorry" no longer
# matches at all). Word-level overlap tolerates that.
REVISION_SIMILARITY_THRESHOLD = 0.6

_WORD_RE = re.compile(r"[a-z0-9']+")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _similarity(a: str, b: str) -> float:
    """Fraction of the shorter text's words that also appear in the longer
    text (each word consumed at most once). 1.0 for identical text modulo
    punctuation/case; still high for a text that grew a few extra words or
    had punctuation revised; low for genuinely unrelated sentences."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    shorter, longer = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    remaining: dict[str, int] = {}
    for w in longer:
        remaining[w] = remaining.get(w, 0) + 1
    matched = 0
    for w in shorter:
        if remaining.get(w, 0) > 0:
            remaining[w] -= 1
            matched += 1
    return matched / len(shorter)


def _merge_fragment(prev: str, new: str) -> str:
    """Combine two pieces of candidate text that may represent the same
    underlying speech (Agora/Deepgram re-transcribing with a revised word
    or different punctuation) or genuinely different content (a new
    fragment after a VAD-detected pause). High word-overlap similarity
    means "same utterance, keep the fuller capture"; low similarity means
    "different content, concatenate" rather than silently dropping either
    side of the answer."""
    prev, new = prev.strip(), new.strip()
    if not prev:
        return new
    if not new:
        return prev
    if _similarity(prev, new) >= REVISION_SIMILARITY_THRESHOLD:
        return new if len(new.split()) >= len(prev.split()) else prev
    return f"{prev} {new}"


def _reconstruct_pending_text(fragments: list[tuple[str, str, float]]) -> str:
    """`fragments` is every (agent_id, candidate_text, ts) call received
    since the panel's last turn. Each agent transcribes the same candidate
    audio independently, so we rebuild each agent's own running view by
    merging its successive fragments in order, then take the longest
    reconstruction as the best single source of truth (more words
    generally means a fuller capture of what was actually said)."""
    per_agent: dict[str, str] = {}
    for agent_id, text, _ts in fragments:
        per_agent[agent_id] = _merge_fragment(per_agent.get(agent_id, ""), text)
    return max(per_agent.values(), key=lambda t: len(t.split()), default="")


def _find_stale_match(state: ConversationState, candidate_text: str, now: float) -> Optional[TranscriptLine]:
    """Is this call actually a late straggler for an utterance the panel
    has already responded to, rather than a fresh new answer? True only if
    the most recent candidate transcript line already has a panelist reply
    after it AND this call's text is a near-match for that line's (see
    REVISION_SIMILARITY_THRESHOLD)."""
    for i in range(len(state.transcript) - 1, -1, -1):
        line = state.transcript[i]
        if line.speaker != "candidate":
            continue
        if now - line.ts > STALE_ANSWER_WINDOW_SECONDS:
            return None
        has_reply_after = any(t.speaker != "candidate" for t in state.transcript[i + 1 :])
        if has_reply_after and _similarity(line.text, candidate_text) >= REVISION_SIMILARITY_THRESHOLD:
            return line
        return None  # most recent candidate line has no reply yet -- it's the current pending answer, not stale
    return None


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


def _finalize_turn(state: ConversationState) -> FloorDecision:
    """Called once real silence has been confirmed since the candidate's
    last speech activity (or the hard MAX_PENDING_WAIT_SECONDS ceiling was
    hit). Reconstructs the full answer from every fragment received since
    the panel's last turn, logs it as one transcript line, and scores which
    panelist should respond next. No LLM call in this hot path — keeps the
    'who speaks next' decision fast and independent of API latency."""
    text = _reconstruct_pending_text(state.pending_fragments)
    state.pending_fragments = []
    state.transcript.append(TranscriptLine(speaker="candidate", text=text))

    signals = extract_signals(text)

    all_keywords: set[str] = set()
    for p in state.panel:
        all_keywords.update(p.keywords)
    for topic in all_keywords:
        if topic in signals.lower_text:
            t = state.topics.setdefault(topic, TopicSignal())
            t.mentions += 1
            t.confidence = min(1.0, t.confidence + 0.15)

    for claim in extract_claims(text):
        if claim not in state.claims:
            state.claims.append(claim)

    agent_order = state.panel_ids()
    scores = {p.id: score_agent(state, p, signals) for p in state.panel}

    if state.turn_count < len(agent_order):
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

    weakness = scores[winner]["weakness"] if winner else 0
    if weakness > 0.4:
        reason = f"{winner} detected a weak/hedged claim"
    elif winner:
        reason = f"{winner} has topical relevance"
    else:
        reason = "no agent met the speaking threshold"

    return FloorDecision(winner=winner, scores=scores, reason=reason, continuation=False)


def _fallback_decision(reason: str) -> FloorDecision:
    """Used only when finalizing a turn raised an unexpected error. Passes
    the floor to nobody rather than crashing the debounce task -- an agent
    simply asks its next question when the candidate speaks again, instead
    of the whole panel going silent for the rest of the interview."""
    return FloorDecision(winner=None, scores={}, reason=reason, continuation=True)


async def _debounce_and_finalize(state: ConversationState, fut: asyncio.Future, started_at: float):
    """Background task, one per pending answer: waits for real silence
    (and the post-question thinking grace) before finalizing. Re-arms
    itself whenever new candidate activity arrives during the wait, so a
    candidate who keeps pausing and resuming is never cut off mid-answer.
    Bounded by MAX_PENDING_WAIT_SECONDS and wrapped so that ANY unexpected
    failure still resolves `fut` -- every one of the three agents' HTTP
    calls is awaiting it, so leaving it unresolved would silently freeze
    the whole panel for the rest of the session."""
    try:
        while True:
            await asyncio.sleep(SILENCE_CONFIRM_SECONDS)
            async with state.lock:
                quiet_for = time.time() - state.last_candidate_activity_ts
                since_question = (
                    time.time() - state.last_panelist_turn_ts
                    if state.last_panelist_turn_ts > 0
                    else MIN_THINKING_SECONDS
                )
                waited_total = time.time() - started_at
            if waited_total >= MAX_PENDING_WAIT_SECONDS:
                break
            if quiet_for < SILENCE_CONFIRM_SECONDS or since_question < MIN_THINKING_SECONDS:
                continue
            break

        async with state.lock:
            decision = _finalize_turn(state)
            state.turn_count += 1
            if decision.winner:
                state.agent_last_spoke_turn[decision.winner] = state.turn_count
                state.agent_last_spoke_ts[decision.winner] = time.time()
            state.pending_decision_future = None
            if not fut.done():
                fut.set_result(decision)
    except Exception:
        logger.exception("floor controller: finalizing a pending turn failed, passing instead of freezing the panel")
        async with state.lock:
            state.pending_fragments = []
            state.pending_decision_future = None
        if not fut.done():
            fut.set_result(_fallback_decision("floor decision failed unexpectedly; passing this turn"))


async def resolve_decision(state: ConversationState, agent_id: str, candidate_text: str) -> FloorDecision:
    """Every interviewer agent calls this once its own ASR sees a new
    candidate message. Rather than deciding synchronously, this buffers the
    fragment and lets a single background debounce task (shared across all
    three agents' calls for the same pending answer) decide once real
    silence is confirmed — see _debounce_and_finalize. A late straggler for
    an utterance the panel has already answered is detected and merged in
    directly, without ever starting a new decision cycle."""
    now = time.time()
    async with state.lock:
        stale = _find_stale_match(state, candidate_text, now)
        if stale is not None:
            merged = _merge_fragment(stale.text, candidate_text)
            if len(merged.split()) > len(stale.text.split()):
                stale.text = merged
                stale.ts = now
            return FloorDecision(
                winner=None,
                scores={},
                reason="late duplicate of an already-answered line (merged, no new turn)",
                continuation=True,
            )

        state.last_candidate_activity_ts = now
        state.pending_fragments.append((agent_id, candidate_text, now))

        if state.pending_decision_future is not None and not state.pending_decision_future.done():
            fut = state.pending_decision_future
        else:
            fut = asyncio.get_event_loop().create_future()
            state.pending_decision_future = fut
            asyncio.create_task(_debounce_and_finalize(state, fut, now))

    return await fut
