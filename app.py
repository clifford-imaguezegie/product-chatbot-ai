"""ProductPilot AI — portfolio chat interface for Streamlit Community Cloud."""
from __future__ import annotations
import os
import time
import streamlit as st
from agent import ProductPilotAgent, AgentError, MAX_HISTORY_TURNS, MODEL
from security import SlidingLimit, verify_code, safe_catalog_image

st.set_page_config(page_title="ProductPilot AI | Product Assistant", page_icon="🛍️", layout="wide",
                   initial_sidebar_state="expanded")

STYLE = """
<style>
.stApp {background: #f7f9fc; color: #13223a;}
.block-container {padding-top: 2.1rem; max-width: 1170px;}
.hero {padding: 1.65rem 1.8rem; border-radius: 20px;
       background: linear-gradient(120deg,#10243a,#17476b 65%,#137e85); color: white;
       box-shadow: 0 12px 34px rgba(15,35,65,.15); margin-bottom: 1.35rem;}
.eyebrow {font-size:.78rem; letter-spacing:.16em; text-transform:uppercase; opacity:.72; font-weight:700;}
.hero h1 {font-size:2.35rem; color:#fff; margin:.25rem 0 .4rem; font-weight:780;}
.hero p {font-size:1rem; opacity:.85; margin:0; max-width:660px;}
.small-label {color:#42627e; font-size:.83rem;}
[data-testid="stChatMessage"] {border:1px solid #e3e9f0; border-radius:14px; background:white;}
[data-testid="stSidebar"] {background: #eef4f9;}
[data-testid="stMetric"] {background:#fff; border: 1px solid #e4e9f0; padding:12px; border-radius:12px;}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True) # Static CSS, never user/API content.


def setting(name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value.strip()
    try:
        return str(st.secrets.get(name, "")).strip()
    except (FileNotFoundError, KeyError, AttributeError):
        return ""


@st.cache_resource
def global_limiter():
    return SlidingLimit()


def auth_gate():
    required_code = setting("DEMO_ACCESS_CODE")
    if not required_code:
        st.error("Deployment setup required: DEMO_ACCESS_CODE is not configured in Streamlit Secrets.")
        st.stop() # Fail closed. Do not expose API access to unauthenticated visitors.
    if st.session_state.get("authenticated"):
        return
    st.markdown('<div class="hero"><div class="eyebrow">Private product demonstration</div>'
                '<h1>ProductPilot AI</h1><p>Explore an AI shopping experience powered by live product APIs.</p></div>',
                unsafe_allow_html=True)
    with st.form("access", clear_on_submit=True):
        value = st.text_input("Demo access code", type="password", placeholder="Enter the code provided with the proposal")
        submit = st.form_submit_button("Enter live demo", use_container_width=True, type="primary")
    if submit:
        failures = st.session_state.get("login_failures", 0)
        if failures >= 5:
            st.error("Too many attempts in this browser session. Please reopen the demo later.")
        elif verify_code(value, required_code):
            st.session_state.authenticated = True
            st.session_state.login_failures = 0
            st.rerun()
        else:
            st.session_state.login_failures = failures + 1
            st.error("Invalid access code.")
    st.caption("Access is provided to invited reviewers. No API credentials are requested from visitors.")
    st.stop()


def render_cards(products):
    if not products:
        return
    with st.container():
        st.caption("MATCHING PRODUCTS · LIVE CATALOG")
        cols = st.columns(min(3, len(products)))
        for i, item in enumerate(products[:6]):
            with cols[i % len(cols)]:
                with st.container(border=True):
                    src = safe_catalog_image(item.get("thumbnail"))
                    if src:
                        st.image(src, use_container_width=True)
                    st.caption(item.get("category") or "Product")
                    st.write(item.get("title") or "Product")
                    st.markdown(f"**${float(item.get('price', 0)):,.2f}**")
                    score = item.get("rating")
                    if score is not None:
                        st.caption(f"★ {float(score):.1f}   ·   Product #{item['id']}")
                    text = item.get("description")
                    if text:
                        st.caption(text[:125] + ("…" if len(text) > 125 else ""))
                    st.link_button("Product details", f"https://dummyjson.com/products/{int(item['id'])}",
                                   use_container_width=True)


def show_turn(turn):
    with st.chat_message("user", avatar="🧑"):
        st.write(turn["question"])
    with st.chat_message("assistant", avatar="🛍️"):
        st.write(turn["answer"])
        render_cards(turn.get("products", []))
        trace = turn.get("trace", [])
        if trace:
            with st.expander("Tool activity", expanded=False):
                st.json(trace, expanded=False)
        if turn.get("elapsed_s") is not None:
            st.caption(f"{turn['elapsed_s']:.1f}s · {turn.get('llm_calls', 0)} model call(s)")


auth_gate()
api_key = setting("OPENROUTER_API_KEY")
if not api_key:
    st.error("The model API key has not been configured. Add OPENROUTER_API_KEY to Streamlit Secrets.")
    st.stop()

if "turns" not in st.session_state:
    st.session_state.turns = []
if "request_timestamps" not in st.session_state:
    st.session_state.request_timestamps = []

with st.sidebar:
    st.title("🛍️ ProductPilot AI")
    st.caption("AI-powered product discovery")
    st.divider()
    st.markdown("**Assistant**")
    st.write("GPT-6 Luna · Low reasoning")
    st.markdown("**Product source**")
    st.write("DummyJSON REST API")
    st.markdown("**Conversation**")
    st.write(f"Remembers up to {MAX_HISTORY_TURNS} recent exchanges")
    st.caption("Conversation content stays in this browser session and is sent to the model provider to answer your questions.")
    if st.button("↺  New conversation", use_container_width=True):
        st.session_state.turns = []
        st.session_state.pending_prompt = None
        st.rerun()
    st.divider()
    st.caption("ProductPilot showcases API-grounded AI agent capabilities. Product search and product-detail tools are read-only.")

st.markdown('<div class="hero"><div class="eyebrow">AI commerce · Agentic customer experience</div>'
            '<h1>Find the right product. Just ask.</h1>'
            '<p>Explore products, compare options and ask follow-up questions in natural English — backed by a live product catalog.</p></div>',
            unsafe_allow_html=True)

st.caption("● GPT-6 Luna · Live catalog integration · Conversational memory")

if not st.session_state.turns:
    st.write("**Try a customer question**")
    suggestions = ["Find three laptops under $1,000", "Recommend a smartphone below $500", "Show me fragrances under $100"]
    cols = st.columns(3)
    for index, text in enumerate(suggestions):
        if cols[index].button(text, key=f"example_{index}", use_container_width=True):
            st.session_state.pending_prompt = text
            st.rerun()

for turn in st.session_state.turns:
    show_turn(turn)

question = st.chat_input("Ask about products, prices, ratings or warranty…", max_chars=500)
if not question:
    question = st.session_state.pop("pending_prompt", None)

if question:
    now = time.monotonic()
    recent = [t for t in st.session_state.request_timestamps if t > now - 900]
    if len(recent) >= 12:
        st.warning("This session has reached its 15-minute demo request allowance.")
    elif not global_limiter().accept(120, 24 * 3600):
        st.warning("The shared demo is at its daily request allowance. Please try again later.")
    else:
        st.session_state.request_timestamps = recent + [now]
        with st.chat_message("user", avatar="🧑"):
            st.write(question)
        with st.chat_message("assistant", avatar="🛍️"):
            with st.spinner("Checking product information…"):
                try:
                    agent = ProductPilotAgent(api_key)
                    result = agent.ask(question, st.session_state.turns)
                except (AgentError, Exception):
                    # Do not expose stack traces or upstream error bodies to visitors.
                    st.error("This request couldn't be completed. Please try again or simplify the question.")
                else:
                    turn = {"question": question, "answer": result.answer,
                            "products": result.products, "trace": result.trace,
                            "llm_calls": result.llm_calls, "elapsed_s": result.elapsed_s}
                    st.session_state.turns.append(turn)
                    st.write(turn["answer"])
                    render_cards(turn["products"])
                    if result.trace:
                        with st.expander("Tool activity"):
                            st.json(result.trace, expanded=False)
                    st.caption(f"{result.elapsed_s:.1f}s · {result.llm_calls} model call(s)")

st.divider()
st.caption("Powered by a live product API and GPT-6 Luna. Products and catalog data are supplied by DummyJSON; checkout and ordering are not enabled.")
