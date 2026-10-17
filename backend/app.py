"""FastAPI backend: segmentation, scripts, and practice runs.

Run with: uv run uvicorn backend.app:app --port 8000
"""

from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import llm
from .segmenter import DEFAULT_MAX_WORDS, DEFAULT_WPM, build_segments, split_rule_based
from .store import Store
from .timing import InvalidTransition, PracticeSession

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
MAX_AUDIO_BYTES = 200 * 1024 * 1024


class SegmentRequest(BaseModel):
    script: str = Field(min_length=1)
    mode: str = Field("auto", pattern="^(auto|sentence|paragraph|llm)$")
    wpm: float = Field(DEFAULT_WPM, gt=0)
    max_words: int = Field(DEFAULT_MAX_WORDS, gt=0)


class ScriptCreate(BaseModel):
    title: str = Field(min_length=1)
    segments: list[str] = Field(min_length=1)
    wpm: float = Field(DEFAULT_WPM, gt=0)
    time_limit_s: float | None = Field(None, gt=0)


def create_app(store: Store | None = None, clock=time.monotonic) -> FastAPI:
    app = FastAPI(title="Presentation Practice Coach")
    app.state.store = store or Store()
    sessions: dict[int, tuple[PracticeSession, dict]] = {}

    def get_session(run_id: int) -> PracticeSession:
        if run_id not in sessions:
            raise HTTPException(404, "run not found or no longer active")
        return sessions[run_id][0]

    @app.get("/api/health")
    def health():
        return {"ok": True, "llm_available": llm.available()}

    @app.post("/api/segment")
    def segment(req: SegmentRequest):
        note = None
        if req.mode == "llm":
            try:
                texts = llm.split_with_llm(req.script)
            except (llm.LLMUnavailable, ValueError) as exc:
                note = f"LLM segmentation unavailable ({exc}); used rule-based split."
                texts = split_rule_based(req.script, "auto", req.max_words)
        else:
            texts = split_rule_based(req.script, req.mode, req.max_words)
        return {"segments": [asdict(s) for s in build_segments(texts, req.wpm)], "note": note}

    @app.post("/api/scripts")
    def create_script(req: ScriptCreate):
        segments = [asdict(s) for s in build_segments(req.segments, req.wpm)]
        if not segments:
            raise HTTPException(422, "all segments are empty")
        script_id = app.state.store.create_script(req.title, req.wpm, req.time_limit_s, segments)
        return app.state.store.get_script(script_id)

    @app.get("/api/scripts")
    def list_scripts():
        return app.state.store.list_scripts()

    @app.get("/api/scripts/{script_id}")
    def get_script(script_id: int):
        script = app.state.store.get_script(script_id)
        if script is None:
            raise HTTPException(404, "script not found")
        return script

    @app.get("/api/scripts/{script_id}/runs")
    def list_runs(script_id: int):
        return app.state.store.list_runs(script_id)

    @app.post("/api/scripts/{script_id}/runs")
    def create_run(script_id: int):
        script = get_script(script_id)
        run_id = app.state.store.create_run(script_id)
        session = PracticeSession([s["target_seconds"] for s in script["segments"]])
        sessions[run_id] = (session, script)
        return {"run_id": run_id, **session.snapshot(clock())}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int):
        return {"run_id": run_id, **get_session(run_id).snapshot(clock())}

    @app.post("/api/runs/{run_id}/{action}")
    def run_action(run_id: int, action: str):
        session = get_session(run_id)
        if action not in {"start", "advance", "stop", "resume", "rewind"}:
            raise HTTPException(404, f"unknown action {action!r}")
        now = clock()
        try:
            getattr(session, action)(now)
        except InvalidTransition as exc:
            raise HTTPException(409, str(exc)) from exc
        app.state.store.save_run(run_id, session, now)
        return {"run_id": run_id, **session.snapshot(now)}

    @app.put("/api/runs/{run_id}/audio")
    async def upload_audio(run_id: int, request: Request):
        get_session(run_id)
        body = await request.body()
        if not body:
            raise HTTPException(422, "empty audio")
        if len(body) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "audio too large")
        path = app.state.store.audio_dir / f"{run_id}.webm"
        path.write_bytes(body)
        app.state.store.set_audio(run_id, path)
        return {"ok": True, "bytes": len(body)}

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
