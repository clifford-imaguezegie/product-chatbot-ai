# ProductPilot AI — GPT-6 Luna · Live Streamlit Demo

A polished API-grounded shopping assistant with **live product retrieval, bounded LLM tool calling, product cards, follow-up conversations and layered demo safeguards**.

**Stack:** Python · Streamlit · OpenRouter Responses API · GPT-6 Luna (low reasoning) · DummyJSON Products API.

## Features

- Customer-facing Streamlit chat and visual product cards
- Search and category browsing; price and stock filters; product-detail lookup
- Four strictly allowlisted, read-only product tools
- Eight-exchange conversational context; full on-screen session transcript
- GPT-6 Luna `openai/gpt-6-luna` using **OpenRouter Responses API**, `reasoning.effort=low`
- Tool activity trace, bounded tool loops, bounded outputs and user-friendly errors
- Gated prospect access, server-side secrets, per-session + shared in-process rate limits
- API-host restriction and product-data sanitization to mitigate injection risks

## Run locally

Requires Python 3.10+.

```bash
python -m pip install -r requirements.txt
mkdir -p .streamlit
# Create .streamlit/secrets.toml from .streamlit/secrets.toml.example
streamlit run app.py
```

Create **`.streamlit/secrets.toml`** with:

```toml
OPENROUTER_API_KEY = "your-own-openrouter-api-key"
DEMO_ACCESS_CODE = "a-long-private-reviewer-access-code"
```

The real secrets file is excluded by `.gitignore`. **Never add it to GitHub, a notebook, screenshots, or a README.**

## Publish and deploy on Streamlit Community Cloud (free hosting)

1. Create a **new GitHub repository** (suggested name: `productpilot-ai-streamlit`).
2. Upload the project files, preserving the `.streamlit/config.toml` directory. Do **not** upload a real `secrets.toml`.
3. Open **https://share.streamlit.io**, connect your GitHub account, and choose **Create app**.
4. Select the repository, `main` branch and **entrypoint `app.py`**.
5. Choose **Advanced settings → Secrets** and paste the two TOML key/value entries from above using your *real* private values.
6. Deploy. Open the generated `*.streamlit.app` link and enter the demo access code.
7. Share the app URL and **access code separately** with the prospect. The GitHub URL shows source code, not the credentials.

Streamlit Community Cloud hosting is free, but **GPT-6 Luna OpenRouter inference is usage-billed**. DummyJSON is the catalog provider used by this demonstration.

### Strongly recommended spending protection

- Create a **dedicated OpenRouter API key for this app**, separate from your notebook/project keys.
- Set a **hard credit/spending limit on that key in OpenRouter's dashboard**. This is much stronger than in-app request limits.
- Put only that dedicated key into Streamlit Secrets; rotate it after the bid/demo if needed.
- Configure a long, unpredictable `DEMO_ACCESS_CODE`, and share only with intended reviewers.
- Monitor OpenRouter usage daily while the app is publicly accessible.

## Safety boundaries and limitations

| Control | How it works |
|---|---|
| API key | Server-side `st.secrets`; never rendered to clients |
| Demo access | Access code checked server side; basic session retry cap |
| API egress | Fixed host `https://dummyjson.com`; no arbitrary HTTP URL tools |
| Tool permissions | Four read-only allowlisted operations; schema and value validation |
| Prompt injection | System instructions, untrusted-data tagging, overt injection filtering |
| Product integrity | API-derived structured product cards and product IDs, no model-generated pricing in cards |
| Tool/model usage | Limited rounds, output tokens, tools per round; low reasoning effort |
| Request limits | 12 requests/15 minutes per browser session; 120 per 24 hours per process |
| Memory/privacy | Chat history kept in Streamlit session, not saved to disk; recent 8 turns sent to provider |

**These are portfolio-demo controls, not a comprehensive production security guarantee.** In-process rate limits can reset on server restarts and do not cover replicas or multiple instances. An access code is a lightweight gate, not user identity management. For production, add provider-side spending caps, robust authentication, distributed rate limiting, content-safety evaluations, security review, managed logs, privacy notice and incident response.

The model may still make an incorrect statement. The product cards are generated from validated API records, but natural-language model output requires evaluation. The catalog's product links are information endpoints, not purchasing pages. No orders, payments or shipping actions occur.

## Project contents

```text
app.py                       Streamlit frontend, session history, access gate
agent.py                     GPT-6 Luna Responses API HTTP integration + tool loop
catalog.py                   Product API adapter + tool schemas/dispatcher
security.py                  Input cleanup, access verification, limits
requirements.txt             Dependencies
.streamlit/config.toml       UI theme
.streamlit/secrets.toml.example  Secrets template only
.gitignore                   Prevent committing credentials
 tests/test_productpilot.py   Offline regression tests
```

## Tests

```bash
python -m pip install pytest
python -m pytest -q
```

Unit tests use simulated HTTP and model responses; **real OpenRouter tool-calling and public Streamlit deployment must be verified after configuring credentials**.

## Quick bid demonstration

Ask these questions in one conversation:

1. `Show me laptops under $1,000. Which are worth considering?`
2. `Which of those has the highest rating?`
3. `Tell me about its warranty and return policy.`
4. `Now show me smartphones under $500.`
5. `Can you order the best one for me?`

Expected: live product retrieval, correct context on follow-ups, grounded product facts, appropriate guardrails for unsupported purchasing.

## Optional follow-up architecture

The Streamlit MVP demonstrates the shared assistant core. A future commercial version can move the orchestration to FastAPI, use a proper user/customer identity layer, persist approved customer conversations and add official WhatsApp, Instagram and Messenger connectors.
