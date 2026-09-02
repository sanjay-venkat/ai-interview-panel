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


async def stream_chat(system_prompt: str, user_message: str, max_tokens: int = 220) -> AsyncIterator[str]:
    """Yields text deltas. Falls back to a deterministic canned response when
    MOCK_MODE is on or no GROQ_API_KEY is set, so the rest of the pipeline
    (floor control, state, WS updates) stays testable/demoable offline."""
    if settings.effective_mock_mode:
        global _mock_idx
        text = MOCK_RESPONSES[_mock_idx % len(MOCK_RESPONSES)]
        _mock_idx += 1
        for word in text.split(" "):
            yield word + " "
        return

    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
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


async def complete_json(system_prompt: str, user_message: str, max_tokens: int = 600) -> dict:
    """Non-streaming call used only for the end-of-interview scorecard, where
    we need one clean JSON object rather than incremental audio."""
    if settings.effective_mock_mode:
        return {
            "technical_depth": 7.0,
            "problem_solving": 6.5,
            "communication": 7.5,
            "ownership": 7.0,
            "system_design": 6.8,
            "culture_fit": 7.2,
            "overall": 7.0,
            "recommendation": "STRONG CONSIDERATION",
            "technical_lead_comment": "Solid grasp of core concepts; deployment trade-offs were less clear.",
            "hiring_manager_comment": "Communicated clearly and owned decisions well; impact could be quantified more.",
            "culture_fit_comment": "Gave a specific, credible example of handling disagreement with a peer.",
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
