"""FastAPI：本机网页、随机推荐问题及流式 Agent 事件。"""
import asyncio
import json
import queue
import random
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.state import busy, create_session, sessions
from app.stream import launch
from app.health import inspect_health
from src.execution_control import ExecutionControl
from app.super_api import router as super_router

PROJECT = Path(__file__).resolve().parent.parent
STATIC = PROJECT / "app" / "static"
app = FastAPI(title="DuReader Agent", docs_url=None, redoc_url=None)
app.include_router(super_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=2000)


@app.middleware("http")
async def local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "仅允许本地页面访问"}, status_code=403)
    return await call_next(request)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get('/healthz')
def healthz():
    return inspect_health()


@app.post("/api/session")
def session():
    try:
        return {"session_id": create_session()}
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/recommendations")
def recommendations():
    path = PROJECT / "data" / "dureader" / "full_queries.json"
    if not path.exists():
        raise HTTPException(503, "未找到固定 DuReader 题集")
    items = json.loads(path.read_text(encoding="utf-8"))["queries"]
    return {"questions": [x["text"] for x in random.SystemRandom().sample(items, min(4, len(items)))]}


@app.post("/chat")
async def chat(request: Request, body: ChatRequest):
    question = body.question.strip()
    if not question or body.session_id not in sessions:
        raise HTTPException(400, "问题或会话无效，请刷新页面")
    if not busy.acquire(blocking=False):
        raise HTTPException(409, "已有问题正在处理，请等待完成")
    try:
        control = ExecutionControl.from_env()
        events = launch(question, body.session_id, control=control)
    except Exception:
        busy.release()
        raise

    async def generate():
        finished = False
        try:
            while not await request.is_disconnected():
                try:
                    item = await asyncio.to_thread(events.get, True, 10)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                if item['type'] in ('done','error'):
                    finished = True
                yield "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
                if finished: break
        finally:
            if not finished: control.cancel()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
