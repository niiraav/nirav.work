"""WebSocket route — echo stub for Week 2.

Real streaming (stdout capture + pipeline thread) wired in Week 3.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.runner import runner

router = APIRouter()


@router.websocket("/sessions/{session_id}/stream")
async def ws_stream(websocket: WebSocket, session_id: str):
    """WebSocket for real-time pipeline output.

    Messages (server → client):
      {"type": "log", "text": "  ROUND 2/4"}
      {"type": "transcript", "entry": {...}}
      {"type": "gate", "stage": 3, "gate_data": {...}}
      {"type": "done", "session_id": "..."}
      {"type": "error", "message": "..."}
    """
    await websocket.accept()
    try:
        while True:
            # Echo anything the client sends (heartbeat / keep-alive)
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        pass
