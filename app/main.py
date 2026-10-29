"""API FastAPI: POST /chat, GET /health, POST /reindex."""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from . import tools
from .agent import responder

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    tools.inicializar(os.getenv("CATALOGO_DB", ":memory:"))
    obs = None
    if os.getenv("WATCH", "1") == "1":
        from .watcher import iniciar_watcher
        obs = iniciar_watcher(tools.CATALOGO, tools.INDICE)
    yield
    if obs:
        obs.stop()


app = FastAPI(title="Altamar Normativa AI", lifespan=lifespan)


class ChatIn(BaseModel):
    prompt: str
    usuario: str  # en producción viene del token SSO (Entra ID), no del body


@app.get("/health")
def health():
    return {"status": "ok", "documentos": len(tools.CATALOGO.documentos()) if tools.CATALOGO else 0}


@app.post("/chat")
def chat(body: ChatIn):
    return responder(body.prompt, body.usuario)


@app.post("/reindex")
def reindex():
    return {"documentos": tools.inicializar(os.getenv("CATALOGO_DB", ":memory:"))}
