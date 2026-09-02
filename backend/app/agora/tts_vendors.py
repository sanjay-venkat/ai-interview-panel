"""Pluggable TTS vendor configs for the Agora ConvoAI join payload.

Why this exists: ElevenLabs' free tier is routinely blocked by Agora's
abuse-detection for real-time streaming use (confirmed in Agora's own docs),
which would silently kill audio output mid-demo. Cartesia's free tier
(20K credits/mo, but crucially 2 concurrent streams — exactly our two-agent
case — and sub-90ms latency) actually works for this use case, so it's the
default. Swap vendors with one env var (TTS_VENDOR) instead of editing code
if you upgrade to a paid ElevenLabs plan or want to compare voice quality.
"""

from app.config import settings

CARTESIA_MODEL_ID = "sonic-2"
ELEVENLABS_MODEL = "eleven_flash_v2_5"  # ElevenLabs' lowest-latency model


def _cartesia_voice_id(agent_id: str) -> str:
    return (
        settings.CARTESIA_VOICE_ID_TECHNICAL
        if agent_id == "technical_lead"
        else settings.CARTESIA_VOICE_ID_MANAGER
    )


def _elevenlabs_voice_id(agent_id: str) -> str:
    return (
        settings.ELEVENLABS_VOICE_ID_TECHNICAL
        if agent_id == "technical_lead"
        else settings.ELEVENLABS_VOICE_ID_MANAGER
    )


def _cartesia_config(agent_id: str) -> dict:
    return {
        "vendor": "cartesia",
        "params": {
            "api_key": settings.CARTESIA_API_KEY,
            "model_id": CARTESIA_MODEL_ID,
            "voice": {"mode": "id", "id": _cartesia_voice_id(agent_id)},
            "output_format": {"container": "raw", "sample_rate": 16000},
            "language": "en",
        },
    }


def _elevenlabs_config(agent_id: str) -> dict:
    return {
        "vendor": "elevenlabs",
        "params": {
            "api_key": settings.ELEVENLABS_API_KEY,
            "model": ELEVENLABS_MODEL,
            "voice_setting": {"voice_id": _elevenlabs_voice_id(agent_id)},
        },
    }


_BUILDERS = {
    "cartesia": _cartesia_config,
    "elevenlabs": _elevenlabs_config,
}

# Settings attribute names required per vendor — read dynamically (not
# captured at import time) so validate_tts_config() always reflects the
# current .env, not whatever was loaded when this module first imported.
_REQUIRED_KEYS = {
    "cartesia": ["CARTESIA_API_KEY", "CARTESIA_VOICE_ID_TECHNICAL", "CARTESIA_VOICE_ID_MANAGER"],
    "elevenlabs": ["ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_TECHNICAL", "ELEVENLABS_VOICE_ID_MANAGER"],
}


def build_tts_config(agent_id: str) -> dict:
    vendor = settings.TTS_VENDOR
    builder = _BUILDERS.get(vendor)
    if builder is None:
        raise ValueError(f"Unknown TTS_VENDOR '{vendor}'. Supported: {', '.join(_BUILDERS)}")
    return builder(agent_id)


def validate_tts_config():
    """Call once before joining agents. Raises with a precise, actionable
    message rather than letting a missing key surface as silent TTS failure
    mid-interview."""
    if settings.effective_mock_mode:
        return
    vendor = settings.TTS_VENDOR
    if vendor not in _REQUIRED_KEYS:
        raise ValueError(f"Unknown TTS_VENDOR '{vendor}'. Supported: {', '.join(_BUILDERS)}")
    missing = [name for name in _REQUIRED_KEYS[vendor] if not getattr(settings, name)]
    if missing:
        raise ValueError(
            f"TTS_VENDOR is '{vendor}' but these .env vars are empty: {', '.join(missing)}. "
            f"Set them, or switch TTS_VENDOR to another supported vendor: {', '.join(_BUILDERS)}."
        )
