from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.roles import DEFAULT_ROLE_KEY, list_roles
from app.orchestration.session_manager import end_session, get_state, start_session
from app.resume.parser import extract_resume_text

router = APIRouter()


class StartRequest(BaseModel):
    candidate_name: str = "Candidate"
    role_key: str = DEFAULT_ROLE_KEY
    resume_text: str = ""


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
