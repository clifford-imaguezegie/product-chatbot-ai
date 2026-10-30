"""ProductPilot AI WhatsApp Cloud API sandbox webhook.

Run from the product-chatbot-ai repository root:
    python -m uvicorn whatsapp_poc.server:app --host 127.0.0.1 --port 8000

This proof of concept intentionally keeps memory and message IDs only in RAM.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from agent import AgentError, ProductPilotAgent

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_verify_token: str
    meta_app_secret: str
    allowed_senders: frozenset[str]
    graph_api_version: str = "v26.0"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            whatsapp_access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip(),
            whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            whatsapp_verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip(),
            meta_app_secret=os.getenv("META_APP_SECRET", "").strip(),
            allowed_senders=frozenset(s.strip().lstrip("+") for s in os.getenv("ALLOWED_WHATSAPP_SENDERS", "").split(",") if s.strip()),
            graph_api_version=os.getenv("META_GRAPH_VERSION", "v26.0").strip(),
        )

    def validate(self) -> None:
        for field in ("openrouter_api_key", "whatsapp_access_token", "whatsapp_phone_number_id", "whatsapp_verify_token", "meta_app_secret"):
            if not getattr(self, field):
                raise RuntimeError(f"Missing setting: {field.upper()}")
        if not self.allowed_senders:
            raise RuntimeError("ALLOWED_WHATSAPP_SENDERS must contain at least one verified test number.")
        if not re.fullmatch(r"v\d+\.\d+", self.graph_api_version):
            raise RuntimeError("Invalid META_GRAPH_VERSION")
        if not re.fullmatch(r"\d+", self.whatsapp_phone_number_id):
            raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID must contain digits only")


class WhatsAppClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()

    def send_text(self, recipient: str, content: str) -> None:
        # Only the configured personal test numbers may receive replies.
        if recipient not in self.settings.allowed_senders:
            raise ValueError("Recipient not permitted for the test")
        url = (f"https://graph.facebook.com/{self.settings.graph_api_version}/"
               f"{self.settings.whatsapp_phone_number_id}/messages")
        payload = {"messaging_product": "whatsapp", "to": recipient, "type": "text",
                   "text": {"preview_url": False, "body": content[:3900]}}
        response = self.session.post(
            url, json=payload,
            headers={"Authorization": "Bearer " + self.settings.whatsapp_access_token,
                     "Content-Type": "application/json"},
            timeout=(5, 20),
        )
        # Never return or print Meta's error body: it may contain account details.
        response.raise_for_status()


class SandboxState:
    """Single-process, per-recipient chat context, deduplication and request caps."""
    def __init__(self):
        self.lock = threading.RLock()
        self.turns: dict[str, list[dict]] = {}
        self.last_activity: dict[str, float] = {}
        self.seen_ids: dict[str, float] = {}
        self.per_sender: dict[str, deque[float]] = defaultdict(deque)
        self.global_calls: deque[float] = deque()

    def accept_message(self, msg_id: str, sender: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self.lock:
            self.seen_ids = {k: v for k, v in self.seen_ids.items() if v > now - 86400}
            if msg_id in self.seen_ids:
                return False
            own = self.per_sender[sender]
            while own and own[0] < now - 3600:
                own.popleft()
            while self.global_calls and self.global_calls[0] < now - 86400:
                self.global_calls.popleft()
            if len(own) >= 12 or len(self.global_calls) >= 40:
                return False
            self.seen_ids[msg_id] = now
            own.append(now)
            self.global_calls.append(now)
            return True

    def history(self, sender: str) -> list[dict]:
        with self.lock:
            if time.monotonic() - self.last_activity.get(sender, 0) > 3600:
                self.turns.pop(sender, None)
            return list(self.turns.get(sender, []))

    def remember(self, sender: str, question: str, result: Any) -> None:
        with self.lock:
            prior = self.turns.get(sender, [])
            prior.append({"question": question, "answer": result.answer,
                          "products": result.products})
            self.turns[sender] = prior[-8:]
            self.last_activity[sender] = time.monotonic()


def valid_signature(raw: bytes, signature: str | None, secret: str) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def extract_inbound(payload: Any, expected_phone_id: str):
    """Yield unique inbound text events, never delivery status events."""
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry", [])[:8]:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", [])[:8]:
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict) or value.get("messaging_product") != "whatsapp":
                continue
            if str((value.get("metadata") or {}).get("phone_number_id")) != expected_phone_id:
                continue
            for message in (value.get("messages") or [])[:10]:
                if not isinstance(message, dict) or message.get("type") != "text":
                    continue
                sender = message.get("from")
                msg_id = message.get("id")
                text = (message.get("text") or {}).get("body")
                if (isinstance(sender, str) and sender.isdigit() and
                        isinstance(msg_id, str) and 1 <= len(msg_id) <= 256 and
                        isinstance(text, str) and text.strip()):
                    yield msg_id, sender, text.strip()[:500]


def create_app(
    settings: Settings | None = None,
    *,
    agent_factory: Callable[[], Any] | None = None,
    send_text: Callable[[str, str], None] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="ProductPilot WhatsApp Sandbox", docs_url=None, redoc_url=None)
    app.state.sandbox = SandboxState()

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "whatsapp-sandbox"}

    @app.get("/webhook", response_class=PlainTextResponse)
    async def verify(request: Request):
        qp = request.query_params
        received_token = qp.get("hub.verify_token") or ""
        if (qp.get("hub.mode") != "subscribe" or not settings.whatsapp_verify_token or
                not hmac.compare_digest(received_token, settings.whatsapp_verify_token)):
            raise HTTPException(status_code=403, detail="Webhook verification failed")
        return qp.get("hub.challenge", "")

    def process_message(sender: str, body: str):
        # A test-only single-process handler. For production, use a durable queue.
        if sender not in settings.allowed_senders:
            return
        try:
            agent = agent_factory() if agent_factory is not None else ProductPilotAgent(settings.openrouter_api_key)
            result = agent.ask(body, app.state.sandbox.history(sender))
            reply = result.answer
            if not reply:
                reply = "Please try your product question again."
            app.state.sandbox.remember(sender, body, result)
        except (AgentError, Exception):
            reply = "I couldn't complete that request. Please try another product question."
        try:
            sender_func = send_text if send_text is not None else WhatsAppClient(settings).send_text
            sender_func(sender, reply)
        except Exception:
            # Prevent leaking tokens, phone numbers, or message text to server logs.
            print("WhatsApp test reply could not be sent; check server-side configuration.")

    @app.post("/webhook")
    async def inbound(request: Request, background_tasks: BackgroundTasks):
        if not settings.meta_app_secret:
            raise HTTPException(status_code=503, detail="Webhook not configured")
        raw = await request.body()
        if len(raw) > 65_536:
            raise HTTPException(status_code=413, detail="Payload too large")
        if not valid_signature(raw, request.headers.get("X-Hub-Signature-256"), settings.meta_app_secret):
            raise HTTPException(status_code=403, detail="Invalid signature")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON")
        queued = 0
        for msg_id, sender, text in extract_inbound(payload, settings.whatsapp_phone_number_id):
            if sender in settings.allowed_senders and app.state.sandbox.accept_message(msg_id, sender):
                background_tasks.add_task(process_message, sender, text)
                queued += 1
        return {"status": "accepted", "queued": queued}

    return app


app = create_app()
