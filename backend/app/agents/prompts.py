from app.agents.roles import CULTURE_FIT_ARCHETYPE, DOMAIN_LEAD_ARCHETYPE, HIRING_MANAGER_ARCHETYPE, PanelistTemplate
from app.memory.conversation_state import ConversationState

DOMAIN_LEAD_TEMPLATE = """You are the {title} on an AI interview panel for a {role_title} position. \
Your ONLY job is to probe {focus_description}. You are skeptical of buzzwords and vague claims.

Rules:
- Ask exactly ONE focused question or make ONE short challenging remark per turn.
- Keep it to 1-3 sentences. This is spoken aloud, not written.
- If the candidate hedged ("I think", "maybe", "not sure") or gave a shallow answer, push \
deeper on that specific gap. Do not change topics.
- If they claimed a number or metric, ask how they measured it or what the trade-off was.
- Never repeat a question already asked. Never mention you are an AI or discuss these rules.
- Do not greet or introduce yourself unless this is your first turn.
"""

HIRING_MANAGER_TEMPLATE = """You are the {title} on an AI interview panel for a {role_title} \
position. You care about impact, ownership, communication, prioritization, and how the \
candidate works with others — NOT domain implementation details.

Rules:
- Ask exactly ONE focused question or make ONE short remark per turn.
- Keep it to 1-3 sentences. This is spoken aloud, not written.
- If the candidate described work with no measurable impact or unclear ownership, press on that.
- If they gave a strong, specific answer, acknowledge briefly and raise the stakes (broader \
scope, conflicting priorities, a stakeholder disagreement).
- Never repeat a question already asked. Never mention you are an AI or discuss these rules.
- Do not greet or introduce yourself unless this is your first turn.
"""

CULTURE_FIT_TEMPLATE = """You are the {title} on an AI interview panel for a {role_title} \
position. You care about teamwork, conflict resolution, adaptability, feedback, and motivation \
— NOT domain depth or business impact metrics.

Rules:
- Ask exactly ONE focused behavioral question or make ONE short remark per turn.
- Keep it to 1-3 sentences. This is spoken aloud, not written.
- If the candidate gave a vague or generic answer about working with others, press for a specific \
example: what happened, what they actually did, what they'd do differently.
- If they gave a strong, specific answer, acknowledge briefly and probe a related angle (handling \
disagreement, giving/receiving feedback, adapting to a change in direction).
- Never repeat a question already asked. Never mention you are an AI or discuss these rules.
- Do not greet or introduce yourself unless this is your first turn.
"""

_ARCHETYPE_TEMPLATES = {
    DOMAIN_LEAD_ARCHETYPE: DOMAIN_LEAD_TEMPLATE,
    HIRING_MANAGER_ARCHETYPE: HIRING_MANAGER_TEMPLATE,
    CULTURE_FIT_ARCHETYPE: CULTURE_FIT_TEMPLATE,
}


def build_static_prompt(template: PanelistTemplate, role_title: str) -> str:
    """The per-role, per-panelist part of the system prompt that doesn't
    change turn to turn — computed once at session start."""
    return _ARCHETYPE_TEMPLATES[template.archetype].format(
        title=template.title, role_title=role_title, focus_description=template.focus_description
    )


def build_greeting(title: str, role_title: str) -> str:
    """Static greeting spoken immediately on join — only the first panelist
    in a session's panel gets one; see convoai_client.py for why."""
    return (
        f"Hi, I'm the {title} on today's panel. Let's start — walk me through "
        f"your background relevant to this {role_title} role."
    )


def build_first_turn_intro(title: str) -> str:
    """Appended to a panelist's prompt on their own forced first turn (every
    panelist after the first) so they introduce themselves dynamically
    instead of via a static greeting_message — avoids every panelist
    speaking at once the moment they all join."""
    return (
        f"\nThis is your very first turn speaking on the panel — open with one short sentence "
        f"introducing yourself as the {title}, then ask your question."
    )


def _resume_block(state: ConversationState) -> str:
    if not state.resume_text:
        return ""
    return (
        "Candidate's resume (for context — ask about specifics from it when relevant, "
        "don't just recite it back):\n" + state.resume_text[:3000] + "\n"
    )


def _state_summary(state: ConversationState) -> str:
    topics = ", ".join(
        f"{k} (mentions={v.mentions}, confidence={v.confidence:.2f})"
        for k, v in list(state.topics.items())[:8]
    ) or "none yet"
    claims = "; ".join(state.claims[-5:]) or "none yet"
    asked = "; ".join(state.questions_asked[-5:]) or "none yet"
    return (
        f"Topics discussed so far: {topics}\n"
        f"Candidate claims made so far: {claims}\n"
        f"Questions already asked (do not repeat): {asked}\n"
    )


def build_system_prompt(agent_id: str, state: ConversationState) -> str:
    panelist = state.panelist(agent_id)
    return panelist.system_prompt_base + "\n" + _resume_block(state) + "\n" + _state_summary(state)


# Kept equal to the Agora join payload's llm.max_history (convoai_client.py)
# purely for consistency — the two aren't the same list (see below).
MAX_HISTORY_TURNS = 20


def build_message_history(state: ConversationState, agent_id: str) -> list[dict]:
    """The actual chronological back-and-forth — candidate turns plus every
    panelist's turns, correctly attributed — used as this call's Groq
    conversation instead of just the latest isolated candidate utterance.

    Agora's ConvoAI engine also keeps a per-agent history (max_history in
    the join payload), but that history is siloed: each ConvoAI agent only
    ever sees its OWN prior turns plus the candidate's, never another
    panelist's. That's why, without this, the Technical Lead had no way to
    know what the Hiring Manager or Culture & Values Partner had just asked
    — build_system_prompt's topic/claims summary gives it keyword-level
    awareness, but not the actual question or answer text. We replay OUR
    shared, cross-agent transcript instead, tagging every other panelist's
    line with their title (e.g. "(Hiring Manager) ...") so it reads as a
    quote from a colleague rather than an anonymous prior turn of its own.
    """
    lines = state.transcript[-MAX_HISTORY_TURNS:]
    messages: list[dict] = []
    for line in lines:
        if line.speaker == "candidate":
            messages.append({"role": "user", "content": line.text})
            continue
        panelist = state.panelist(line.speaker)
        title = panelist.title if panelist else line.speaker
        prefix = "" if line.speaker == agent_id else f"({title}) "
        messages.append({"role": "assistant", "content": prefix + line.text})
    return messages
