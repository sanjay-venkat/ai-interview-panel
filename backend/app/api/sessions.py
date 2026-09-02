from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.orchestration.session_manager import end_session, get_state, start_session

router = APIRouter()


class StartRequest(BaseModel):
    candidate_name: str = "Candidate"
    role: str = "Software Engineer"


@router.post("/session/start")
async def start(req: StartRequest):
    try:
        return await start_session(req.candidate_name, req.role)
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
