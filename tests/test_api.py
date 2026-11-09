from fastapi.testclient import TestClient

from app import api
from app.llm import LLMError
from app.models import AgentResponse, SelfCheck

client = TestClient(api.app)


def test_bad_requests_get_a_422_with_the_reason():
    r = client.post("/agent", json={"request": "hi"})
    assert r.status_code == 422 and "at least 10 characters" in r.text


def test_no_model_available_is_a_503(monkeypatch):
    def down(_):
        raise LLMError("all busy")
    monkeypatch.setattr(api.agent, "run", down)
    assert client.post("/agent", json={"request": "Write meeting minutes for the sync"}).status_code == 503


def test_a_successful_run_returns_a_full_download_link(monkeypatch):
    monkeypatch.setattr(api.agent, "run", lambda _: AgentResponse(
        summary="s", document_type="d", title="t", tasks=[], assumptions=[], conflicts=[],
        self_check=SelfCheck(passed=True), document_url="/documents/0123456789ab", seconds=1.0))
    body = client.post("/agent", json={"request": "Write meeting minutes for the sync"}).json()
    assert body["document_url"] == "http://testserver/documents/0123456789ab"


def test_only_generated_document_ids_can_be_downloaded():
    assert client.get("/documents/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/documents/ffffffffffff").status_code == 404


def test_a_non_document_request_is_declined_with_a_422(monkeypatch):
    def decline(_):
        raise api.agent.NotADocumentRequest("I write business documents; try asking for a report.")
    monkeypatch.setattr(api.agent, "run", decline)
    r = client.post("/agent", json={"request": "What's the weather in Mumbai tomorrow?"})
    assert r.status_code == 422 and "Not a document request" in r.text
