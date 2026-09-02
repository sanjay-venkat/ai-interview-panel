import base64
import uuid

import httpx

from app.agora.rtc_token import build_rtc_token
from app.agora.tts_vendors import build_tts_config
from app.config import settings

CANDIDATE_UID = 1000
# Positional — index 0/1/2 within a session's panel, regardless of which
# persona/role that slot holds. Caps panel size at 3 (matches the 3 TTS
# voice slots configured in .env).
PANEL_UIDS = [2001, 2002, 2003]

DEEPGRAM_MODEL = "nova-3"


def _auth_header() -> dict:
    raw = f"{settings.AGORA_CUSTOMER_ID}:{settings.AGORA_CUSTOMER_SECRET}".encode()
    return {"Authorization": f"Basic {base64.b64encode(raw).decode()}"}


def _build_join_payload(
    slot: int, agent_id: str, session_id: str, channel: str, system_prompt: str, greeting: str | None
) -> dict:
    llm_url = f"{settings.PUBLIC_BACKEND_URL}/llm/{agent_id}/{session_id}/chat/completions"
    llm_block = {
        "vendor": "custom",
        "style": "openai",
        "url": llm_url,
        "system_messages": [{"role": "system", "content": system_prompt}],
        "failure_message": "Sorry, could you say that again?",
        "max_history": 20,
        "params": {"model": settings.GROQ_MODEL},
    }
    # Only the first panelist in the panel gets a static greeting_message,
    # spoken immediately on join before any candidate input. If every agent
    # had one, they'd all speak simultaneously the instant they join — the
    # rest introduce themselves dynamically on their forced first turn
    # instead (see prompts.py build_first_turn_intro), staggered by the
    # floor controller.
    if greeting:
        llm_block["greeting_message"] = greeting

    uid = PANEL_UIDS[slot]
    return {
        "name": f"{session_id}-{agent_id}",
        "properties": {
            "channel": channel,
            "token": build_rtc_token(channel, uid),
            "agent_rtc_uid": str(uid),
            "remote_rtc_uids": [str(CANDIDATE_UID)],
            "enable_string_uid": False,
            "idle_timeout": 600,
            "asr": {
                "vendor": "deepgram",
                "params": {
                    "url": "wss://api.deepgram.com/v1/listen",
                    "api_key": settings.DEEPGRAM_API_KEY,
                    "model": DEEPGRAM_MODEL,
                    "language": "en",
                },
            },
            "llm": llm_block,
            "tts": build_tts_config(slot),
        },
    }


async def join_agent(
    slot: int, agent_id: str, session_id: str, channel: str, system_prompt: str, greeting: str | None
) -> str:
    if not settings.AGORA_CUSTOMER_ID or not settings.AGORA_CUSTOMER_SECRET or settings.effective_mock_mode:
        return f"mock-agent-{uuid.uuid4().hex[:8]}"

    payload = _build_join_payload(slot, agent_id, session_id, channel, system_prompt, greeting)
    url = f"{settings.AGORA_CONVOAI_BASE_URL}/projects/{settings.AGORA_APP_ID}/join"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=_auth_header())
        resp.raise_for_status()
        return resp.json()["agent_id"]


async def leave_agent(agent_id: str):
    if agent_id.startswith("mock-agent-"):
        return
    url = f"{settings.AGORA_CONVOAI_BASE_URL}/projects/{settings.AGORA_APP_ID}/agents/{agent_id}/leave"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=_auth_header())
        resp.raise_for_status()
