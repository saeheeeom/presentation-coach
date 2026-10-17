import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.store import Store


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path):
    clock = FakeClock()
    client = TestClient(create_app(Store(tmp_path), clock=clock))
    return client, clock


SCRIPT = "Hello everyone, welcome to the talk.\n\nToday we cover three main ideas about practice. First, segments."


def test_segment_endpoint(env):
    client, _ = env
    res = client.post("/api/segment", json={"script": SCRIPT, "mode": "paragraph", "wpm": 120})
    assert res.status_code == 200
    segs = res.json()["segments"]
    assert len(segs) == 2
    assert segs[0]["word_count"] == 6 and segs[0]["target_seconds"] == 3.0


def test_llm_mode_falls_back_without_model(env, monkeypatch):
    from backend import llm

    def unavailable(_):
        raise llm.LLMUnavailable("not installed")

    monkeypatch.setattr(llm, "split_with_llm", unavailable)
    res = env[0].post("/api/segment", json={"script": SCRIPT, "mode": "llm"})
    assert res.status_code == 200
    assert "rule-based" in res.json()["note"]


def test_practice_run_with_resume(env, tmp_path):
    client, clock = env
    script = client.post("/api/scripts", json={"title": "T", "segments": ["one two three", "four five six"], "wpm": 60}).json()
    run = client.post(f"/api/scripts/{script['id']}/runs").json()
    rid = run["run_id"]

    def act(action, t):
        clock.t = t
        return client.post(f"/api/runs/{rid}/{action}")

    act("start", 0)
    act("advance", 4)
    act("stop", 6)
    assert act("advance", 7).status_code == 409   # can't advance while stopped
    snap = act("resume", 20).json()
    assert snap["base_elapsed"] == 4 and snap["current"] == 1
    snap = act("advance", 23).json()
    assert snap["state"] == "finished"
    assert [s["actual"] for s in snap["segments"]] == [4, 3]

    assert client.put(f"/api/runs/{rid}/audio", content=b"fakewebm").json()["bytes"] == 8
    runs = client.get(f"/api/scripts/{script['id']}/runs").json()
    assert runs[0]["state"] == "finished" and runs[0]["total_seconds"] == 7
    assert runs[0]["audio_path"].endswith(f"{rid}.webm")
    assert client.get("/api/scripts").json()[0]["runs"] == 1


def test_unknown_run_and_action(env):
    client, _ = env
    assert client.post("/api/runs/999/start").status_code == 404
    script = client.post("/api/scripts", json={"title": "T", "segments": ["a b c"]}).json()
    rid = client.post(f"/api/scripts/{script['id']}/runs").json()["run_id"]
    assert client.post(f"/api/runs/{rid}/explode").status_code == 404


def test_frontend_served(env):
    res = env[0].get("/")
    assert res.status_code == 200 and "Presentation Coach" in res.text
