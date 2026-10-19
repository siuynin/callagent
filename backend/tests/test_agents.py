import httpx
import pytest
from conftest import ADMIN_A, ADMIN_B, STAFF_A, TENANT_A

from voiceos.agents.config import config_hash

SVC = {"X-Service-Token": "test-service-token", "X-Tenant-Id": str(TENANT_A)}


@pytest.fixture()
def gateway(monkeypatch):
    """Capture eval requests the backend sends to the media gateway."""
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        return httpx.Response(202, request=httpx.Request("POST", url), json={"accepted": True})

    monkeypatch.setattr("voiceos.api.routers.agents.httpx.post", fake_post)
    return calls


def _seeded(client):
    items = client.get("/api/v1/agents", headers=ADMIN_A).json()["items"]
    assert len(items) == 1
    return client.get(f"/api/v1/agents/{items[0]['id']}", headers=ADMIN_A).json()["data"]


def _save(client, agent, config, headers=ADMIN_A):
    return client.put(
        f"/api/v1/agents/{agent['id']}/draft",
        json={"config": config},
        headers={**headers, "If-Match": str(agent["version"])},
    )


def _report(client, version_id, config, passed=True):
    body = {
        "config_hash": config_hash(config),
        "passed": passed,
        "summary": {"scenarios": 2, "passed": 2 if passed else 1},
    }
    return client.post(f"/api/v1/internal/agent-versions/{version_id}/eval-result", json=body, headers=SVC)


def test_seeded_agent_is_live_and_served_to_gateway(client):
    agent = _seeded(client)
    assert agent["active_version"]["number"] == 1 and agent["draft"] is None
    live = client.get("/api/v1/internal/agents/active", headers=SVC).json()
    assert live["version_id"] == agent["active_version"]["id"]
    assert "{greeting}" in live["config"]["instructions"]


def test_invalid_template_variables_rejected(client):
    agent = _seeded(client)
    cfg = dict(agent["active_config"], instructions=agent["active_config"]["instructions"] + " {secret_key}")
    r = _save(client, agent, cfg)
    assert r.status_code == 400 and "instructions" in r.json()["error"]["field_errors"]
    bad_brace = dict(agent["active_config"], greeting="Xin chào {business_name")
    assert _save(client, agent, bad_brace).status_code == 400


def test_full_cycle_draft_eval_publish_and_draft_never_live(client, gateway):
    agent = _seeded(client)
    cfg = dict(agent["active_config"], voice="cedar")
    agent = _save(client, agent, cfg).json()["data"]
    draft = agent["draft"]
    assert draft["number"] == 2 and draft["eval"] is None
    # AC04: the draft is not used by live calls
    assert client.get("/api/v1/internal/agents/active", headers=SVC).json()["config"]["voice"] == "marin"
    # AC25: cannot publish before a passing eval
    r = client.post(
        f"/api/v1/agents/{agent['id']}/publish", json={"version_id": draft["id"]}, headers=ADMIN_A
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "EVAL_REQUIRED"
    r = client.post(f"/api/v1/agents/{agent['id']}/draft/eval", headers=ADMIN_A)
    assert r.status_code == 202 and r.json()["data"]["eval"]["status"] == "running"
    assert gateway[0]["json"]["config_hash"] == config_hash(cfg)
    assert gateway[0]["headers"]["X-Service-Token"] == "test-service-token"
    assert _report(client, draft["id"], cfg).json()["accepted"] is True
    ok = client.post(
        f"/api/v1/agents/{agent['id']}/publish", json={"version_id": draft["id"]}, headers=ADMIN_A
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["active_version"]["number"] == 2
    assert client.get("/api/v1/internal/agents/active", headers=SVC).json()["config"]["voice"] == "cedar"


def test_failed_eval_blocks_publish(client, gateway):
    agent = _seeded(client)
    cfg = dict(agent["active_config"], vad_silence_ms=800)
    agent = _save(client, agent, cfg).json()["data"]
    client.post(f"/api/v1/agents/{agent['id']}/draft/eval", headers=ADMIN_A)
    _report(client, agent["draft"]["id"], cfg, passed=False)
    r = client.post(
        f"/api/v1/agents/{agent['id']}/publish", json={"version_id": agent["draft"]["id"]}, headers=ADMIN_A
    )
    assert r.status_code == 422


def test_editing_after_eval_invalidates_it(client, gateway):
    agent = _seeded(client)
    cfg = dict(agent["active_config"], vad_silence_ms=700)
    agent = _save(client, agent, cfg).json()["data"]
    client.post(f"/api/v1/agents/{agent['id']}/draft/eval", headers=ADMIN_A)
    _report(client, agent["draft"]["id"], cfg)
    agent = client.get(f"/api/v1/agents/{agent['id']}", headers=ADMIN_A).json()["data"]
    edited = dict(cfg, vad_silence_ms=750)
    agent = _save(client, agent, edited).json()["data"]
    assert agent["draft"]["eval"]["valid_for_current_config"] is False
    r = client.post(
        f"/api/v1/agents/{agent['id']}/publish", json={"version_id": agent["draft"]["id"]}, headers=ADMIN_A
    )
    assert r.status_code == 422
    # a late result for the old config is ignored
    assert _report(client, agent["draft"]["id"], cfg).json()["accepted"] is False


def test_greeting_must_disclose_ai_and_recording(client, gateway):
    agent = _seeded(client)
    cfg = dict(agent["active_config"], greeting="Dạ, {business_name} xin nghe, em có thể giúp gì ạ?")
    agent = _save(client, agent, cfg).json()["data"]
    client.post(f"/api/v1/agents/{agent['id']}/draft/eval", headers=ADMIN_A)
    _report(client, agent["draft"]["id"], cfg)
    r = client.post(
        f"/api/v1/agents/{agent['id']}/publish", json={"version_id": agent["draft"]["id"]}, headers=ADMIN_A
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "COMPLIANCE_GREETING"
    assert len(r.json()["error"]["field_errors"]["greeting"]) == 2


def test_rollback_publishes_copy_of_earlier_version(client, gateway):
    agent = _seeded(client)
    v1 = agent["active_version"]
    cfg = dict(agent["active_config"], voice="cedar")
    agent = _save(client, agent, cfg).json()["data"]
    client.post(f"/api/v1/agents/{agent['id']}/draft/eval", headers=ADMIN_A)
    _report(client, agent["draft"]["id"], cfg)
    client.post(
        f"/api/v1/agents/{agent['id']}/publish", json={"version_id": agent["draft"]["id"]}, headers=ADMIN_A
    )
    r = client.post(f"/api/v1/agents/{agent['id']}/rollback", json={"version_id": v1["id"]}, headers=ADMIN_A)
    data = r.json()["data"]
    assert data["active_version"]["number"] == 3
    assert data["active_version"]["eval"]["rolled_back_from"] == 1
    assert [v["number"] for v in data["versions"]] == [3, 2, 1]  # history kept
    assert client.get("/api/v1/internal/agents/active", headers=SVC).json()["config"]["voice"] == "marin"


def test_roles(client, gateway):
    agent = _seeded(client)
    assert _save(client, agent, agent["active_config"], headers=STAFF_A).status_code == 403
    assert (
        client.post(
            f"/api/v1/agents/{agent['id']}/rollback",
            json={"version_id": agent["active_version"]["id"]},
            headers=STAFF_A,
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/agents/{agent['id']}", headers=ADMIN_B).status_code == 404


def test_version_conflict_on_concurrent_draft_edits(client):
    agent = _seeded(client)
    assert _save(client, agent, agent["active_config"]).status_code == 200
    stale = _save(client, agent, dict(agent["active_config"], voice="ash"))  # same old agent version
    assert stale.status_code == 409


def test_gateway_unreachable_reports_503(client, monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("voiceos.api.routers.agents.httpx.post", boom)
    agent = _seeded(client)
    agent = _save(client, agent, agent["active_config"]).json()["data"]
    r = client.post(f"/api/v1/agents/{agent['id']}/draft/eval", headers=ADMIN_A)
    assert r.status_code == 503 and r.json()["error"]["retryable"] is True


def test_call_records_agent_version(client):
    agent = _seeded(client)
    from voiceos.db import utcnow

    body = {
        "provider": "openai",
        "provider_call_id": "v-1",
        "started_at": utcnow().isoformat(),
        "agent_version_id": agent["active_version"]["id"],
    }
    cid = client.post("/api/v1/internal/calls", json=body, headers=SVC).json()["id"]
    assert (
        client.get(f"/api/v1/calls/{cid}", headers=ADMIN_A).json()["data"]["agent_version_id"]
        == agent["active_version"]["id"]
    )
    assert client.get("/api/v1/agents", headers=ADMIN_A).json()["items"][0]["calls_today"] == 1
