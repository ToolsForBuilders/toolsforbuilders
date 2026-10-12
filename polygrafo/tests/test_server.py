import base64
import time

import pytest
from fastapi.testclient import TestClient

from polygrafo import auth, main
from polygrafo.models import Post, Report


def basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    auth._failures.clear()
    for k in ("POLYGRAFO_PASSWORD", "POLYGRAFO_REQUIRE_PASSWORD", "POLYGRAFO_USER"):
        monkeypatch.delenv(k, raising=False)


client = TestClient(main.app)


def test_open_locally_without_password():
    assert client.get("/").status_code == 200


def test_fail_closed_when_password_required_but_missing(monkeypatch):
    monkeypatch.setenv("POLYGRAFO_REQUIRE_PASSWORD", "1")
    assert client.get("/").status_code == 503
    assert client.get("/health").status_code == 200  # verificação do alojamento continua a funcionar


def test_password_required(monkeypatch):
    monkeypatch.setenv("POLYGRAFO_PASSWORD", "uma-senha-longa-123")
    r = client.get("/")
    assert r.status_code == 401 and "Basic" in r.headers["www-authenticate"]
    assert client.get("/", headers=basic("eu", "errada")).status_code == 401
    assert client.get("/", headers=basic("outro", "uma-senha-longa-123")).status_code == 401
    assert client.get("/", headers=basic("eu", "uma-senha-longa-123")).status_code == 200


def test_short_password_rejected(monkeypatch):
    monkeypatch.setenv("POLYGRAFO_PASSWORD", "curta")
    assert client.get("/", headers=basic("eu", "curta")).status_code == 503


def test_lockout_after_failures(monkeypatch):
    monkeypatch.setenv("POLYGRAFO_PASSWORD", "uma-senha-longa-123")
    for _ in range(auth.MAX_FAILURES):
        assert client.get("/", headers=basic("eu", "x")).status_code == 401
    assert client.get("/", headers=basic("eu", "uma-senha-longa-123")).status_code == 429


def test_job_flow(monkeypatch):
    def fake_analyze(self, post, image=None, image_type="image/png"):
        return Report(post=post, claims=[], overall_score=None, overall_label="Não verificável",
                      overall_confidence=0.0, summary="ok")
    monkeypatch.setattr(main.Polygrafo, "__init__", lambda self, s=None: None)
    monkeypatch.setattr(main.Polygrafo, "analyze", fake_analyze)
    r = client.post("/api/check", data={"text": "A Terra é plana"})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done" and job["result"]["post"]["text"] == "A Terra é plana"


def test_job_error_is_reported(monkeypatch):
    def boom(self, *a, **k):
        raise main.AnalysisError("sem conteúdo")
    monkeypatch.setattr(main.Polygrafo, "__init__", lambda self, s=None: None)
    monkeypatch.setattr(main.Polygrafo, "analyze", boom)
    job_id = client.post("/api/check", data={"text": "x"}).json()["job_id"]
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job == {"status": "error", "stage": job["stage"], "error": "sem conteúdo"}


def test_empty_request_rejected():
    assert client.post("/api/check", data={}).status_code == 400


def test_unknown_job():
    assert client.get("/api/jobs/nao-existe").status_code == 404
