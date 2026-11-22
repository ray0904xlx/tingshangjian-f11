"""FastAPI 入口。啟動：uvicorn app.main:app --reload"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .engine import CourtSession, list_cases, load_case
from .llm import get_provider

app = FastAPI(title="庭上見 F11 單人 AI 模擬法庭")
SESSIONS: dict = {}   # 先放記憶體；之後換成 PostgreSQL 保存學習紀錄
STATIC = Path(__file__).parent.parent / "static"


class NewSession(BaseModel):
    case_id: str = "rent_deposit_01"


class Turn(BaseModel):
    text: str


def _get(sid: str) -> CourtSession:
    if sid not in SESSIONS:
        raise HTTPException(404, "找不到這場模擬開庭")
    return SESSIONS[sid]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/cases")
def cases():
    return list_cases()


@app.post("/api/sessions")
def create_session(body: NewSession):
    try:
        case = load_case(body.case_id)
    except KeyError:
        raise HTTPException(404, "找不到案件")
    s = CourtSession(case, get_provider())
    SESSIONS[s.id] = s
    return {"messages": s.start(), "state": s.state()}


@app.post("/api/sessions/{sid}/turn")
def turn(sid: str, body: Turn):
    s = _get(sid)
    return {"messages": s.turn(body.text), "state": s.state()}


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    s = _get(sid)
    return {"transcript": s.transcript, "state": s.state()}
