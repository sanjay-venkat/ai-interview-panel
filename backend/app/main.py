from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.llm_proxy import router as llm_proxy_router
from app.api.sessions import router as sessions_router
from app.api.ws import router as ws_router
from app.config import settings

app = FastAPI(title="AI Interview Panel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)
app.include_router(llm_proxy_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok", "mock_mode": settings.effective_mock_mode}
