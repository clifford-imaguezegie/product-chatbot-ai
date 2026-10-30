"""Offline WhatsApp sandbox tests. No internet, OpenRouter key, or Meta account required."""
import hashlib
import hmac
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from whatsapp_poc.server import Settings, SandboxState, WhatsAppClient, create_app, extract_inbound, valid_signature

SETTINGS = Settings(
    openrouter_api_key="test-do-not-use", whatsapp_access_token="fake-token",
    whatsapp_phone_number_id="101000222333", whatsapp_verify_token="private-webhook-token",
    meta_app_secret="test-meta-secret",
    allowed_senders=frozenset({"447700900123"}),
)


def payload(sender="447700900123", msg_id="wamid.1", content="Show laptops under $500"):
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": SETTINGS.whatsapp_phone_number_id},
        "messages": [{"from": sender, "id": msg_id, "type": "text", "text": {"body": content}}],
    }}]}]}


def signed_post(client, data, secret=SETTINGS.meta_app_secret):
    raw = json.dumps(data, separators=(",", ":")).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=raw, headers={"X-Hub-Signature-256": sig})


def test_challenge_verification():
    client = TestClient(create_app(SETTINGS))
    ok = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": SETTINGS.whatsapp_verify_token,
                                      "hub.challenge": "123456"})
    assert ok.status_code == 200 and ok.text == "123456"
    bad = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "123456"})
    assert bad.status_code == 403


def test_signature_verification_and_size_limit():
    assert valid_signature(b"hello", "sha256=" + hmac.new(b"secret", b"hello", hashlib.sha256).hexdigest(), "secret")
    assert not valid_signature(b"hello", "sha256=123", "secret")
    client = TestClient(create_app(SETTINGS))
    assert client.post("/webhook", json=payload()).status_code == 403
    assert signed_post(client, payload()).status_code == 200
    assert client.post("/webhook", content=b"a" * 70000, headers={"X-Hub-Signature-256": "sha256=1"}).status_code == 413


def test_extract_only_valid_text_for_matching_number():
    assert list(extract_inbound(payload(), SETTINGS.whatsapp_phone_number_id)) == [("wamid.1", "447700900123", "Show laptops under $500")]
    assert list(extract_inbound(payload(), "wrong-number-id")) == []
    assert list(extract_inbound({"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {"statuses": [{"id": "x"}]}}]}]}, SETTINGS.whatsapp_phone_number_id)) == []


def test_end_to_end_mock_inbound_agent_reply_and_followup_memory():
    calls, sent = [], []

    class Agent:
        def ask(self, question, turns):
            calls.append({"question": question, "history": list(turns)})
            return SimpleNamespace(answer=f"Catalog answer: {question}", products=[{"id": 1, "title": "Example"}])

    client = TestClient(create_app(SETTINGS, agent_factory=Agent, send_text=lambda to, txt: sent.append((to, txt))))
    r = signed_post(client, payload(msg_id="wamid.1", content="Find a smartphone under $200"))
    assert r.status_code == 200 and r.json()["queued"] == 1
    r2 = signed_post(client, payload(msg_id="wamid.2", content="What about its warranty?"))
    assert r2.status_code == 200 and r2.json()["queued"] == 1
    assert len(sent) == len(calls) == 2
    assert sent[0][0] == "447700900123"
    assert len(calls[0]["history"]) == 0
    assert calls[1]["history"][0]["question"] == "Find a smartphone under $200"
    assert calls[1]["history"][0]["products"][0]["title"] == "Example"
    duplicate = signed_post(client, payload(msg_id="wamid.2"))
    assert duplicate.json()["queued"] == 0
    assert len(sent) == 2


def test_unverified_sender_denied_without_model_calls():
    called = []
    client = TestClient(create_app(SETTINGS, agent_factory=lambda: called.append(True), send_text=lambda *a: called.append(True)))
    res = signed_post(client, payload(sender="44123456789", msg_id="wamid.other"))
    assert res.status_code == 200 and res.json()["queued"] == 0
    assert not called


def test_per_sender_throttle():
    state = SandboxState()
    for idx in range(12):
        assert state.accept_message(f"wamid.{idx}", "447700900123", now=1000.0)
    assert not state.accept_message("wamid.thirteenth", "447700900123", now=1000.0)
    assert state.accept_message("wamid.after", "447700900123", now=4701.0)


def test_meta_api_send_is_allowlisted_and_uses_secret_header():
    class FakeSession:
        def __init__(self): self.calls = []
        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return SimpleNamespace(raise_for_status=lambda: None)
    session = FakeSession()
    client = WhatsAppClient(SETTINGS, session=session)
    client.send_text("447700900123", "Hello")
    url, kwargs = session.calls[0]
    assert url == "https://graph.facebook.com/v26.0/101000222333/messages"
    assert kwargs["headers"]["Authorization"] == "Bearer fake-token"
    assert kwargs["json"]["text"]["body"] == "Hello"
    try:
        client.send_text("44123456789", "Hello")
    except ValueError:
        pass
    else:
        assert False, "Unlisted recipient must be refused"
    assert len(session.calls) == 1
