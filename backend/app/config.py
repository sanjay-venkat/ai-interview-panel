import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # Agora
    AGORA_APP_ID = os.getenv("AGORA_APP_ID", "")
    AGORA_APP_CERTIFICATE = os.getenv("AGORA_APP_CERTIFICATE", "")
    AGORA_CUSTOMER_ID = os.getenv("AGORA_CUSTOMER_ID", "")
    AGORA_CUSTOMER_SECRET = os.getenv("AGORA_CUSTOMER_SECRET", "")
    AGORA_CONVOAI_BASE_URL = os.getenv(
        "AGORA_CONVOAI_BASE_URL", "https://api.agora.io/api/conversational-ai-agent/v2"
    )

    # Public URL the Agora ConvoAI engine can reach to call OUR /llm/* endpoint.
    # During the hackathon this MUST be a public tunnel (ngrok/cloudflared), not localhost.
    PUBLIC_BACKEND_URL = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000")

    # STT vendor used inside Agora ConvoAI agent config
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

    # TTS vendor is pluggable — see app/agora/tts_vendors.py. Cartesia is the
    # default: its free tier supports 2 concurrent real-time streams (exactly
    # our two-agent case) with sub-90ms latency. ElevenLabs' free tier is
    # routinely blocked for real-time streaming by Agora's abuse detection,
    # so only use it once you're on a paid plan.
    TTS_VENDOR = os.getenv("TTS_VENDOR", "cartesia")  # "cartesia" | "elevenlabs"

    CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")
    CARTESIA_VOICE_ID_TECHNICAL = os.getenv("CARTESIA_VOICE_ID_TECHNICAL", "")
    CARTESIA_VOICE_ID_MANAGER = os.getenv("CARTESIA_VOICE_ID_MANAGER", "")

    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID_TECHNICAL = os.getenv("ELEVENLABS_VOICE_ID_TECHNICAL", "")
    ELEVENLABS_VOICE_ID_MANAGER = os.getenv("ELEVENLABS_VOICE_ID_MANAGER", "")

    # LLM (Groq free tier, lightweight model)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    # Fallback mode: no external calls, deterministic canned responses.
    # Auto-enables if GROQ_API_KEY is missing so the app never hard-crashes in a demo.
    MOCK_MODE = _bool("MOCK_MODE", default=False)

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

    @property
    def effective_mock_mode(self) -> bool:
        return self.MOCK_MODE or not self.GROQ_API_KEY


settings = Settings()
