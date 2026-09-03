import time
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.roles import DEFAULT_ROLE_KEY, list_roles
from app.memory.conversation_state import broadcast
from app.orchestration.session_manager import end_session, get_state, start_session
from app.resume.parser import extract_resume_text

router = APIRouter()

MAX_PROCTOR_EVENTS = 200


class StartRequest(BaseModel):
    candidate_name: str = "Candidate"
    role_key: str = DEFAULT_ROLE_KEY
    resume_text: str = ""


class ProctorEventRequest(BaseModel):
    type: Literal["tilt", "away"]


@router.get("/roles")
async def roles():
    return list_roles()


@router.post("/resume/parse")
async def parse_resume(file: UploadFile = File(...)):
    data = await file.read()
    text = extract_resume_text(file.filename or "", data)
    return {"text": text}


@router.post("/session/start")
async def start(req: StartRequest):
    try:
        return await start_session(req.candidate_name, req.role_key, req.resume_text)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/session/{session_id}/end")
async def end(session_id: str):
    try:
        return await end_session(session_id)
    except ValueError:
        raise HTTPException(404, "unknown session_id")


@router.get("/session/{session_id}/state")
async def state(session_id: str):
    st = get_state(session_id)
    if st is None:
        raise HTTPException(404, "unknown session_id")
    return st.snapshot()


@router.post("/session/{session_id}/proctor-event")
async def proctor_event(session_id: str, req: ProctorEventRequest):
    """Browser-side webcam proctoring (see frontend/lib/faceProctor.ts)
    reports debounced tilt/away incidents here — never raw video. Counts are
    the source of truth surfaced back over the WS snapshot and folded into
    the final scorecard's integrity summary."""
    st = get_state(session_id)
    if st is None:
        raise HTTPException(404, "unknown session_id")

    async with st.lock:
        if req.type == "tilt":
            st.proctor_tilt_count += 1
        else:
            st.proctor_away_count += 1
        st.proctor_events.append({"type": req.type, "ts": time.time()})
        del st.proctor_events[:-MAX_PROCTOR_EVENTS]

    broadcast(st)
    return {"proctor_tilt_count": st.proctor_tilt_count, "proctor_away_count": st.proctor_away_count}
