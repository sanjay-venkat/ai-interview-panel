from app.llm.groq_client import complete_json
from app.memory.conversation_state import ConversationState

DELIBERATION_SYSTEM = """You are combining notes from three interviewers (a Technical Lead, a \
Hiring Manager, and a Culture & Values Partner) into a final structured scorecard for a \
candidate. Be concise, specific, and base every judgment only on the transcript and signals \
given. Respond with ONLY a JSON object matching this schema:
{
  "technical_depth": number (0-10),
  "problem_solving": number (0-10),
  "communication": number (0-10),
  "ownership": number (0-10),
  "system_design": number (0-10),
  "culture_fit": number (0-10),
  "overall": number (0-10),
  "recommendation": "STRONG CONSIDERATION" | "CONSIDER" | "NOT RECOMMENDED",
  "technical_lead_comment": string (1-2 sentences, first person as the Technical Lead),
  "hiring_manager_comment": string (1-2 sentences, first person as the Hiring Manager),
  "culture_fit_comment": string (1-2 sentences, first person as the Culture & Values Partner)
}
"""


def _build_user_message(state: ConversationState) -> str:
    transcript = "\n".join(f"{t.speaker}: {t.text}" for t in state.transcript)
    topics = "\n".join(
        f"- {k}: mentions={v.mentions}, confidence={v.confidence:.2f}" for k, v in state.topics.items()
    ) or "none"
    claims = "\n".join(f"- {c}" for c in state.claims) or "none"
    return (
        f"Candidate: {state.candidate_name}, Role: {state.role}\n\n"
        f"TOPICS:\n{topics}\n\nCLAIMS MADE:\n{claims}\n\nFULL TRANSCRIPT:\n{transcript}"
    )


async def deliberate(state: ConversationState) -> dict:
    user_message = _build_user_message(state)
    scorecard = await complete_json(DELIBERATION_SYSTEM, user_message)
    state.scorecard = scorecard
    return scorecard
