# ProductPilot AI — WhatsApp Cloud API Sandbox (Test Only)

This is an additive WhatsApp integration for the existing GitHub repository, **not** a replacement for the live Streamlit application. It reuses existing `agent.py`, `catalog.py`, and `security.py`, including GPT-6 Luna Low and read-only catalog tools.

## Costs and prerequisites

- Meta's developer sandbox and test phone number: free for development/testing. Normal production WhatsApp messaging has separate pricing.
- Cloudflare Quick Tunnel: free temporary HTTPS endpoint, no account required.
- GPT-6 Luna through OpenRouter: usage-billed; use a dedicated capped key.
- Your own WhatsApp-enabled mobile number must be approved as a sandbox test recipient in Meta (typically up to five test recipient numbers).

Meta developer start: https://whatsappbusiness.com/developers/developer-hub/

## First: Verify Meta's sandbox before coding

1. Go to https://developers.facebook.com/apps/ and create a developer app with the **WhatsApp / Connect with customers through WhatsApp** use case (dashboard wording may vary).
2. In the WhatsApp **API Setup / Start using the API** section, find your **test business phone number**, **Phone Number ID**, and **temporary access token**.
3. Add and verify your personal WhatsApp number under test recipients (enter full country code, no leading `+` in our config).
4. Use Meta's dashboard **Send message** option to send the preapproved `hello_world` test message to your phone. Confirm you receive it. No ProductPilot code is needed for this connectivity test.

## Second: Run the ProductPilot webhook locally (Windows PowerShell)

Copy `whatsapp_poc/` into the root of your existing `product-chatbot-ai` repository:

```text
product-chatbot-ai/
  agent.py
  catalog.py
  security.py
  app.py                    # unchanged Streamlit frontend
  whatsapp_poc/
    server.py
    requirements.txt
    .env.example
    .env                    # created locally; NEVER commit
```

From PowerShell, in `C:\Users\Hp\projects\product-chatbot-ai`:

```powershell
python -m pip install -r whatsapp_poc/requirements.txt
Copy-Item whatsapp_poc/.env.example whatsapp_poc/.env
notepad whatsapp_poc/.env
```

Fill in the `.env` values:

- `OPENROUTER_API_KEY`: a dedicated OpenRouter key with a spending limit.
- `WHATSAPP_ACCESS_TOKEN`: sandbox temporary token from Meta's WhatsApp API Setup; it will expire and need renewing.
- `WHATSAPP_PHONE_NUMBER_ID`: the numeric **Phone Number ID** of Meta's test business number (not the display number).
- `WHATSAPP_VERIFY_TOKEN`: a strong arbitrary value you choose; you'll enter **exactly the same text** in Meta's webhook configuration.
- `META_APP_SECRET`: the Meta developer **App Secret** (in app basic settings; do not confuse it with the verify token).
- `ALLOWED_WHATSAPP_SENDERS`: your approved personal WhatsApp number, country code and digits only, e.g. `447XXXXXXXXX`. You can comma-separate multiple verified test numbers.
- `META_GRAPH_VERSION`: defaults to `v26.0`.

**Never put the real `.env` in GitHub or send these tokens in chat.** Your existing `.gitignore` ignores `.env` and `.env.*`.

Validate that all required configuration values are present (this never prints credentials):

```powershell
python -m whatsapp_poc.check_config
```

Start the server:

```powershell
python -m uvicorn whatsapp_poc.server:app --host 127.0.0.1 --port 8000
```

Check locally at http://127.0.0.1:8000/health (the response should show `status: ok`).

In a **second PowerShell window**, install and start Cloudflare's free temporary tunnel:

```powershell
winget install -e --id Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:8000
```

Cloudflare prints a temporary address like `https://random-name.trycloudflare.com`. Keep both terminals open during testing. Do **not** use `--allowed-mail` on this tunnel because Meta's webhook cannot complete interactive email authentication; authenticity is verified using Meta's HMAC signature instead.

## Third: Register Meta's webhook

In the WhatsApp app/dashboard Webhooks settings:

- Callback URL: `https://random-name.trycloudflare.com/webhook`
- Verify token: your `WHATSAPP_VERIFY_TOKEN` value
- Subscribe to the **messages** webhook field (and, if the UI requires it, subscribe your WABA to the app).

Meta calls `GET /webhook` to verify ownership. The server compares the verify token and returns the `hub.challenge`. On incoming messages, Meta signs the POST request; the server verifies `X-Hub-Signature-256` using `META_APP_SECRET`.

## Fourth: Test a real two-way ProductPilot conversation

1. From your approved personal WhatsApp, reply to the Meta test business number (for example): `Hello ProductPilot. Find two smartphones under $200.`
2. The signed Meta webhook should reach the local FastAPI backend.
3. ProductPilot asks GPT-6 Luna to use product tools against DummyJSON.
4. The backend sends its answer through WhatsApp Cloud API back to your number.
5. Follow up in the **same WhatsApp chat**: `Which one is cheaper, and what is its warranty?` to test continuity.
6. Test safe refusal: `Can you place the order and charge my card?` The agent has only read-only tools.

If you receive no reply, check the Meta webhook delivery status, verify your temporary token has not expired, and ensure both PowerShell processes remain running. For free-form replies, first message the test business number to open the customer-service window; business-initiated outreach may require a template.

## Safety and operational boundaries

- Strong webhook challenge verification, signed POST requests with HMAC-SHA256, and a numeric Phone Number ID check.
- Only allowlisted sandbox recipient numbers are served; unlisted senders cannot trigger LLM calls.
- Ignore delivery receipts and unsupported message types; process inbound text only.
- Per-sender conversation memory: most recent **8 exchanges**, in RAM; expires after 1 hour of inactivity.
- Duplicate message-id suppression for 24 hours; per-sender cap **12 messages/hour**, shared cap **40/24h** (in-memory, single process).
- Agent's existing API grounding and prompt-injection precautions apply; these are mitigations, not guarantees.
- Acknowledge incoming webhook quickly, then process and send replies in a background task. This is suitable for a small local test, **not** a durable production queue.
- No automatic outreach, purchases, payments, customer database, or permanent transcript storage.

When finished, stop the tunnel (`Ctrl+C`), stop the FastAPI server (`Ctrl+C`), and delete or rotate the temporary Meta token as appropriate. You can keep the tested code in your repository without committing credentials.

## Test without Meta credentials

From the repository root:

```powershell
python -m pip install pytest httpx
python -m pytest -q tests/test_whatsapp_poc.py
```

The offline tests simulate webhook verification, signatures, deduplication, allowlist controls, tool invocation, and memory without sending messages or incurring API costs.
