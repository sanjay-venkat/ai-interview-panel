import base64
import uuid

import httpx

from app.agora.rtc_token import build_rtc_token
from app.agora.tts_vendors import build_tts_config
from app.config import settings

CANDIDATE_UID = 1000
AGENT_UIDS = {"technical_lead": 2001, "hiring_manager": 2002}

DEEPGRAM_MODEL = "nova-3"


def _auth_header() -> dict:
    raw = f"{settings.AGORA_CUSTOMER_ID}:{settings.AGORA_CUSTOMER_SECRET}".encode()
    return {"Authorization": f"Basic {base64.b64encode(raw).decode()}"}


def _build_join_payload(agent_id: str, session_id: str, channel: str, system_prompt: str, greeting: str) -> dict:
    llm_url = f"{settings.PUBLIC_BACKEND_URL}/llm/{agent_id}/{session_id}/chat/completions"
    return {
        "name": f"{session_id}-{agent_id}",
        "properties": {
            "channel": channel,
            "token": build_rtc_token(channel, AGENT_UIDS[agent_id]),
            "agent_rtc_uid": str(AGENT_UIDS[agent_id]),
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
            "llm": {
                "vendor": "custom",
                "style": "openai",
                "url": llm_url,
                "system_messages": [{"role": "system", "content": system_prompt}],
                "greeting_message": greeting,
                "failure_message": "Sorry, could you say that again?",
                "max_history": 20,
                "params": {"model": settings.GROQ_MODEL},
            },
            "tts": build_tts_config(agent_id),
        },
    }


async def join_agent(agent_id: str, session_id: str, channel: str, system_prompt: str, greeting: str) -> str:
    if not settings.AGORA_CUSTOMER_ID or not settings.AGORA_CUSTOMER_SECRET or settings.effective_mock_mode:
        return f"mock-agent-{uuid.uuid4().hex[:8]}"

    payload = _build_join_payload(agent_id, session_id, channel, system_prompt, greeting)
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
