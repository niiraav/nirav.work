"""FastAPI application entrypoint.

Registers REST and WebSocket routers.  CORS enabled for Next.js dev server.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import sessions, ws

app = FastAPI(
    title="Idea Validator API",
    description="Dual-agent deliberation engine — Synthesizer vs Skeptic",
    version="0.1.0",
)

# CORS — allow Next.js dev server (localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(sessions.router, prefix="", tags=["sessions"])
app.include_router(ws.router, prefix="", tags=["websocket"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
