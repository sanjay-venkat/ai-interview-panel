import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings

MOCK_RESPONSES = [
    "That's a reasonable start. Can you walk me through why you chose that approach over the alternatives?",
    "Interesting. What was the hardest trade-off you had to make there?",
    "Let's go a level deeper — what would break first if traffic tripled?",
    "Good. Who else was involved, and how did you handle disagreement on the approach?",
    "What would you do differently if you rebuilt this today?",
]
_mock_idx = 0


async def stream_chat(system_prompt: str, messages: list[dict], max_tokens: int = 220) -> AsyncIterator[str]:
    """Yields text deltas. `messages` is the real chronological transcript
    (candidate + every panelist's turns, correctly attributed — see
    prompts.build_message_history) rather than just the latest isolated
    candidate line, so each agent's call reflects the actual conversation
    instead of one utterance in a vacuum. Falls back to a deterministic
    canned response when MOCK_MODE is on or no GROQ_API_KEY is set, so the
    rest of the pipeline (floor control, state, WS updates) stays
    testable/demoable offline."""
    if settings.effective_mock_mode:
        global _mock_idx
        text = MOCK_RESPONSES[_mock_idx % len(MOCK_RESPONSES)]
        _mock_idx += 1
        for word in text.split(" "):
            yield word + " "
        return

    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
        "max_tokens": max_tokens,
        "temperature": 0.6,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        async with client.stream(
            "POST", f"{settings.GROQ_BASE_URL}/chat/completions", json=payload, headers=headers
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield delta


async def complete_json(system_prompt: str, user_message: str, max_tokens: int = 600, mock_panel=None) -> dict:
    """Non-streaming call used only for the end-of-interview scorecard, where
    we need one clean JSON object rather than incremental audio."""
    if settings.effective_mock_mode:
        panel = mock_panel or []
        return {
            "domain_depth": 7.0,
            "problem_solving": 6.5,
            "communication": 7.5,
            "ownership": 7.0,
            "collaboration": 7.2,
            "overall": 7.0,
            "recommendation": "STRONG CONSIDERATION",
            "panelist_comments": {
                p.title: "Solid, specific answers overall; a bit more depth on trade-offs would help."
                for p in panel
            },
            "metric_feedback": {
                "domain_depth": {
                    "why": "Answers showed working knowledge of the core concepts but leaned on generalities rather than specifics from real projects.",
                    "improve": "Walk through one project in concrete technical detail — the actual data, the actual failure mode, the actual fix.",
                },
                "problem_solving": {
                    "why": "Trade-offs were acknowledged but rarely quantified, so it's hard to tell how the decision was actually reached.",
                    "improve": "Name the alternatives you rejected and the specific reason each one lost out.",
                },
                "communication": {
                    "why": "Explanations were clear and well-paced, with good use of concrete examples.",
                    "improve": "Keep leading with the conclusion first, then the supporting detail, especially on longer answers.",
                },
                "ownership": {
                    "why": "The candidate described their role in past work but was vague about which decisions were actually theirs versus the team's.",
                    "improve": "Be explicit about what you personally decided, drove, or were accountable for versus what the team did.",
                },
                "collaboration": {
                    "why": "Mentioned working with others but gave little detail on how disagreements or blockers were actually resolved.",
                    "improve": "Describe one specific disagreement and how it was resolved, not just that the team worked together.",
                },
                "overall": {
                    "why": "A consistent, competent performance across all three interviewers with no major red flags.",
                    "improve": "Add more concrete numbers and named trade-offs throughout — depth is the single biggest lever left.",
                },
            },
        }

    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{settings.GROQ_BASE_URL}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
