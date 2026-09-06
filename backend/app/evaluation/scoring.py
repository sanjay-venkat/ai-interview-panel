from app.llm.groq_client import complete_json
from app.memory.conversation_state import ConversationState

SCORECARD_METRICS = ["domain_depth", "problem_solving", "communication", "ownership", "collaboration", "overall"]

SCORECARD_SCHEMA = """Respond with ONLY a JSON object matching this schema:
{
  "domain_depth": number (0-10),
  "problem_solving": number (0-10),
  "communication": number (0-10),
  "ownership": number (0-10),
  "collaboration": number (0-10),
  "overall": number (0-10),
  "recommendation": "STRONG CONSIDERATION" | "CONSIDER" | "NOT RECOMMENDED",
  "panelist_comments": { "<panelist title exactly as given>": "1-2 sentence first-person comment from that panelist" },
  "metric_feedback": {
    "domain_depth": { "why": "1-2 sentences on why this score, citing specific transcript evidence", "improve": "1 concrete, actionable sentence on what would raise this score" },
    "problem_solving": { "why": "...", "improve": "..." },
    "communication": { "why": "...", "improve": "..." },
    "ownership": { "why": "...", "improve": "..." },
    "collaboration": { "why": "...", "improve": "..." },
    "overall": { "why": "...", "improve": "..." }
  }
}
"panelist_comments" must have exactly one entry per panelist listed below, keyed by their exact title.
"metric_feedback" must have exactly one entry per metric above (domain_depth, problem_solving, communication,
ownership, collaboration, overall), each with both "why" and "improve" filled in — never leave either blank."""


def _build_system_prompt(state: ConversationState) -> str:
    titles = ", ".join(f'"{p.title}"' for p in state.panel)
    return (
        f"You are combining notes from {len(state.panel)} interviewers ({titles}) into a final "
        f"structured scorecard for a candidate interviewing for a {state.role} position. Be "
        f"concise, specific, and base every judgment only on the transcript and signals given.\n\n"
        f"{SCORECARD_SCHEMA}"
    )


def _build_user_message(state: ConversationState) -> str:
    transcript = "\n".join(f"{t.speaker}: {t.text}" for t in state.transcript)
    topics = "\n".join(
        f"- {k}: mentions={v.mentions}, confidence={v.confidence:.2f}" for k, v in state.topics.items()
    ) or "none"
    claims = "\n".join(f"- {c}" for c in state.claims) or "none"
    resume = state.resume_text[:2000] if state.resume_text else "not provided"
    proctor_note = (
        f"Webcam proctoring during the session recorded {state.proctor_tilt_count} sustained head-tilt "
        f"event(s) and {state.proctor_away_count} away-from-camera event(s). This is a rough automated "
        f"signal (lighting/webcam quality can cause false positives) — only mention it if the count is "
        f"notably high; do not treat a low count as noteworthy."
    )
    return (
        f"Candidate: {state.candidate_name}, Role: {state.role}\n\n"
        f"RESUME:\n{resume}\n\n"
        f"TOPICS:\n{topics}\n\nCLAIMS MADE:\n{claims}\n\nFULL TRANSCRIPT:\n{transcript}\n\n{proctor_note}"
    )


async def deliberate(state: ConversationState) -> dict:
    system_prompt = _build_system_prompt(state)
    user_message = _build_user_message(state)
    scorecard = await complete_json(system_prompt, user_message, mock_panel=state.panel)
    state.scorecard = scorecard
    return scorecard
