"""WebSocket route — real streaming implementation for Week 3."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.runner import runner as _runner

router = APIRouter()


@router.websocket("/sessions/{session_id}/stream")
async def ws_stream(websocket: WebSocket, session_id: str):
    """Real-time pipeline stream.

    On connect: sends {"type": "state", "session": <full session>}
    While running: receives {"type": "log"|"transcript"|"gate"|"done"|"error"}
    Client sends keep-alive pings; pipeline pushes messages to this socket.
    """
    await websocket.accept()
    await _runner.register_ws(session_id, websocket)

    # Send current session snapshot so the client can hydrate without a REST call
    try:
        from orchestrator import load_session
        session = load_session(session_id)
        session["transcript"] = list(session.get("transcript", []))
        await websocket.send_json({"type": "state", "session": session})
    except FileNotFoundError:
        pass

    try:
        while True:
            await websocket.receive_text()  # keep-alive; pipeline pushes to us
    except WebSocketDisconnect:
        await _runner.unregister_ws(session_id, websocket)
