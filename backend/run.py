import os

import uvicorn

if __name__ == "__main__":
    # Reload is off by default. `reload_dirs=["app"]` was tried to scope the
    # watcher away from .venv/ (which lives inside backend/), but WatchFiles
    # still fired on changes inside .venv on this setup — each reload kills
    # in-flight requests, which surfaces as random 502s through a tunnel
    # while Agora's agents are mid-conversation. Not worth the risk during a
    # live session. Set RELOAD=true if you want hot-reload for local editing
    # with no tunnel/live-demo traffic in flight.
    reload = os.getenv("RELOAD", "false").strip().lower() in ("1", "true", "yes")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=reload)
