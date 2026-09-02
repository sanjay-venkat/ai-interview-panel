import time

from agora_token_builder import RtcTokenBuilder

from app.config import settings

ROLE_PUBLISHER = 1


def build_rtc_token(channel: str, uid: int, expire_seconds: int = 3600) -> str:
    if not settings.AGORA_APP_ID or not settings.AGORA_APP_CERTIFICATE:
        return ""  # mock mode: Agora Web SDK can still join an App-ID-only project in testing mode
    expire_ts = int(time.time()) + expire_seconds
    return RtcTokenBuilder.buildTokenWithUid(
        settings.AGORA_APP_ID,
        settings.AGORA_APP_CERTIFICATE,
        channel,
        uid,
        ROLE_PUBLISHER,
        expire_ts,
    )
