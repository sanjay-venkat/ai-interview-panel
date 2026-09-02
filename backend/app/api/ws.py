import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.memory.conversation_state import session_store, subscribe, unsubscribe

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    state = session_store.get(session_id)
    if state is None:
        await websocket.close(code=4404)
        return

    queue = subscribe(state)
    await websocket.send_json(state.snapshot())
    try:
        while True:
            snapshot = await queue.get()
            await websocket.send_json(snapshot)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        unsubscribe(state, queue)
