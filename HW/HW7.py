# Streamlit Cloud fix (same as HW 5): Chroma needs a newer sqlite3 than the
# Cloud has. pysqlite3-binary only installs on Linux, so on the Mac this
# import fails and we keep the normal sqlite3.
try:
    __import__("pysqlite3")
    import sys
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

import os
import re
import json
import time
from datetime import date
from html import escape

import streamlit as st
from openai import OpenAI, PermissionDeniedError
import chromadb

# HW 7 = a news desk for a global law firm that answers ONLY from news.csv.
#
# The pieces, and the course week each one comes from:
#   - RAG (W4): the 1,082 articles were embedded ONCE, outside this app, by
#     build_HW7_db.py. This page only opens the saved HW7_ChromaDB/ folder
#     (the assignment's suggestion: the DB just loads, so nobody waits for
#     embeddings).
#   - Tools (W5): the model holds three functions and picks per question:
#       search_news(query, company)  -> "find news about X" (vector search)
#       list_headlines()             -> "most interesting" (every headline,
#                                       so it ranks the whole week, not just
#                                       one search's hits)
#       get_articles(ids)            -> the saved text of the stories it picked
#   - Prompt engineering (W3): the system prompt defines "interesting" and
#     the answer format ("The Brief": headline, company and date, then a
#     paragraph on why it may matter).
#
# The model never writes links. It cites article ids like [news-0042], and
# the app turns those into links from the database - so every source shown
# is a real record, and the saved text sits one click under each answer.

# ---------- The Brief: page-local styling, built on HW 5 ----------
# The marker gates every rule, including widget menus rendered in portals.
# Leaving HW 7 removes the marker and its styling; no shared theme is changed.
STYLE = """
<div id="hw7-page-marker" aria-hidden="true"></div>
<style>
body:has(#hw7-page-marker) {
    --hw7-ink: #f3e3ea;
    --hw7-rose: #e8b4c8;
    --hw7-muted: #c9a7b9;
    --hw7-line: #674558;
    --hw7-paper: #f4e8ed;
    --hw7-paper-ink: #392532;
    -webkit-text-size-adjust: 100%;
    text-size-adjust: 100%;
}
#hw7-page-marker, [data-testid="stElementContainer"]:has(#hw7-page-marker) { display: none; }
body:has(#hw7-page-marker) .stApp :not(span[translate="no"]):not(span[data-testid="stIconMaterial"]):not(.material-symbols-rounded):not(code):not(pre):not(kbd) {
    font-family: "Times New Roman", Times, serif !important;
}
body:has(#hw7-page-marker) [data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse at 82% 0%, #432738 0%, transparent 52%),
                linear-gradient(180deg, #2b1d26 0%, #30202b 60%, #2c2034 100%);
    color: var(--hw7-ink);
    color-scheme: dark;
}
body:has(#hw7-page-marker) [data-testid="stHeader"] { background: rgba(43,29,38,.92); color: var(--hw7-ink); }
body:has(#hw7-page-marker) [data-testid="stMainBlockContainer"] { max-width: 1060px; padding-top: 3.2rem; padding-bottom: 3rem; }
body:has(#hw7-page-marker) [data-testid="stBottom"] > div,
body:has(#hw7-page-marker) [data-testid="stBottomBlockContainer"] { background: transparent; }
body:has(#hw7-page-marker) [data-testid="stBottomBlockContainer"] { max-width: 1060px; }
body:has(#hw7-page-marker) [data-testid="stBottom"] {
    background: linear-gradient(0deg, #2c2034 75%, rgba(44,32,52,0));
    padding-top: .6rem;
}
body:has(#hw7-page-marker) [data-testid="stSidebar"] { background: #2a1d27; border-right: 1px solid #5a3b4c; }
body:has(#hw7-page-marker) [data-testid="stSidebarContent"] { padding-top: 1rem; }
body:has(#hw7-page-marker) [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { color: var(--hw7-ink); }
body:has(#hw7-page-marker) [data-testid="stWidgetLabel"] p,
body:has(#hw7-page-marker) [data-testid="stRadio"] p { color: var(--hw7-ink); }
body:has(#hw7-page-marker) [data-testid="stCaptionContainer"],
body:has(#hw7-page-marker) [data-testid="stCaptionContainer"] p { color: var(--hw7-muted) !important; font-size: .86rem; line-height: 1.55; }
body:has(#hw7-page-marker) [data-testid="stCaptionContainer"] { opacity: 1; }
body:has(#hw7-page-marker) [data-testid="stRadioGroup"],
body:has(#hw7-page-marker) [data-testid="stRadioGroup"] > div { width: 100%; }
body:has(#hw7-page-marker) [data-testid="stRadio"] label[data-baseweb="radio"],
body:has(#hw7-page-marker) [data-testid="stRadioOption"] {
    border: 1px solid transparent; border-radius: 9px; padding: .4rem .6rem;
    margin: 0 0 .2rem; background: rgba(255,255,255,.015); display: flex; width: 100%;
}
body:has(#hw7-page-marker) [data-testid="stRadio"] label:has(input:checked) {
    border-color: #82576e; background: #422b3a;
}
body:has(#hw7-page-marker) [data-testid="stRadioOption"] > div > div:first-child { background: #634557; border-color: #a87b92; }
body:has(#hw7-page-marker) [data-testid="stRadioOption"][data-selected="true"] > div > div:first-child { background: var(--hw7-rose); border-color: var(--hw7-rose); }
body:has(#hw7-page-marker) [data-testid="stRadioOption"][data-selected="true"] > div > div:first-child > div { background: #30212b; }
body:has(#hw7-page-marker) [data-testid="stRadio"] label:has(input:focus-visible) { outline: 2px solid var(--hw7-rose); outline-offset: 2px; }
body:has(#hw7-page-marker) [data-testid="stSlider"] { color: var(--hw7-ink); }
body:has(#hw7-page-marker) [data-testid="stSlider"] [role="slider"] { background: var(--hw7-rose); border-color: var(--hw7-rose); }
body:has(#hw7-page-marker) [data-testid="stSlider"] [role="group"] > div { background: transparent; }
body:has(#hw7-page-marker) [data-testid="stSlider"] [role="group"] > div > div:first-child {
    background: linear-gradient(to right, var(--hw7-rose) 0%, var(--hw7-rose) var(--hw7-slider-fill, 50%), #69495e var(--hw7-slider-fill, 50%), #69495e 100%);
}
body:has(#hw7-page-marker) [data-testid="stSlider"] [role="group"] > div > div:has(input[type="range"]) { background: var(--hw7-rose); }
body:has(#hw7-page-marker) [data-testid="stSlider"] [data-testid="stSliderThumbValue"] p { color: var(--hw7-rose); }
body:has(#hw7-page-marker) h1,
body:has(#hw7-page-marker) h2,
body:has(#hw7-page-marker) h3 { color: var(--hw7-ink); font-weight: 400; }
body:has(#hw7-page-marker) a { color: var(--hw7-rose); text-underline-offset: .2em; }
body:has(#hw7-page-marker) .stButton > button {
    background: #432d3c; color: var(--hw7-ink); border: 1px solid #855a72;
    border-radius: 10px; min-height: 2.85rem; padding: .65rem 1rem;
    transition: background .15s ease, border-color .15s ease;
}
body:has(#hw7-page-marker) .stButton > button:hover { background: #533449; border-color: var(--hw7-rose); color: var(--hw7-rose); }
body:has(#hw7-page-marker) .stButton > button[kind="primary"] {
    background: var(--hw7-rose); color: #30212b; border-color: var(--hw7-rose);
}
body:has(#hw7-page-marker) .stButton > button[kind="primary"]:hover { background: #f2ccdb; color: #30212b; }
body:has(#hw7-page-marker) .stButton > button:focus-visible,
body:has(#hw7-page-marker) [data-baseweb="select"]:focus-within,
body:has(#hw7-page-marker) [data-testid="stSelectbox"] [role="group"]:focus-within,
body:has(#hw7-page-marker) [data-testid="stChatInput"]:focus-within {
    outline: 2px solid var(--hw7-rose); outline-offset: 3px;
}
body:has(#hw7-page-marker) [data-baseweb="select"] > div,
body:has(#hw7-page-marker) [data-testid="stSelectbox"] [role="group"] {
    background: #382631; color: var(--hw7-ink); border-color: #855a72;
    border-radius: 10px; min-height: 2.85rem;
}
body:has(#hw7-page-marker) [data-baseweb="select"] input,
body:has(#hw7-page-marker) [data-testid="stSelectbox"] input { color: var(--hw7-ink); background: transparent; }
body:has(#hw7-page-marker) [data-testid="stSelectbox"] input::placeholder { color: var(--hw7-muted); }
body:has(#hw7-page-marker) [data-baseweb="select"] svg,
body:has(#hw7-page-marker) [data-testid="stSelectbox"] svg { fill: var(--hw7-rose); color: var(--hw7-rose); }
body:has(#hw7-page-marker) [role="listbox"] { background: #382631; color: var(--hw7-ink); font-family: "Times New Roman", Times, serif; }
body:has(#hw7-page-marker) [role="option"] { background: #382631; color: var(--hw7-ink); }
body:has(#hw7-page-marker) [role="option"]:hover,
body:has(#hw7-page-marker) [role="option"][aria-selected="true"] { background: #583b4d; }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] {
    background: rgba(49,32,43,.72); border: 1px solid var(--hw7-line);
    border-radius: 14px; padding: 1.45rem 1.6rem; margin: .65rem 0;
    box-shadow: 0 10px 32px rgba(17,10,16,.12);
}
body:has(#hw7-page-marker) [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {
    background: #432c3a; border-color: #80546c; padding: .85rem 1.2rem;
}
body:has(#hw7-page-marker) [data-testid="stChatMessageAvatarAssistant"],
body:has(#hw7-page-marker) [data-testid="stChatMessageAvatarUser"],
body:has(#hw7-page-marker) [data-testid="stChatMessageAvatarCustom"] { background: #624154; color: var(--hw7-rose); }
body:has(#hw7-page-marker) [data-testid="stIconMaterial"],
body:has(#hw7-page-marker) [data-testid^="stExpanderIcon"] { color: var(--hw7-rose); }
body:has(#hw7-page-marker) [data-testid="stChatMessageContent"] { min-width: 0; }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { color: var(--hw7-ink); }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] p,
body:has(#hw7-page-marker) [data-testid="stChatMessage"] li { color: var(--hw7-ink); font-size: 1.06rem; line-height: 1.72; overflow-wrap: anywhere; }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] ol { padding-left: 2rem; }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] ol > li { padding-left: .55rem; margin: .6rem 0 1.8rem; }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] ol > li + li { border-top: 1px solid var(--hw7-line); padding-top: 1.4rem; }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] ol > li::marker { color: var(--hw7-rose); font-size: 1.55rem; font-weight: 400; }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] strong { color: #f5ccdf; }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] ol > li > p:first-child > strong:first-child {
    font-size: 1.24rem; font-weight: 600; line-height: 1.4;
}
body:has(#hw7-page-marker) [data-testid="stChatMessage"] a { color: var(--hw7-rose); }
body:has(#hw7-page-marker) [data-testid="stChatMessage"] [data-testid="stCaptionContainer"] p { font-size: .8rem; line-height: 1.6; }
body:has(#hw7-page-marker) [data-testid="stChatInput"] {
    background: #3d2836; border: 1px solid #986c83; border-radius: 15px;
    box-shadow: 0 6px 24px rgba(0,0,0,.22);
}
body:has(#hw7-page-marker) [data-testid="stChatInput"] > div { background: transparent; border-color: transparent; }
body:has(#hw7-page-marker) [data-testid="stChatInput"] textarea { color: var(--hw7-ink); background: transparent; font-size: 1.02rem; }
body:has(#hw7-page-marker) [data-testid="stChatInput"] textarea::placeholder { color: #d2afbf; }
body:has(#hw7-page-marker) [data-testid="stChatInputSubmitButton"] { color: var(--hw7-rose); background: transparent; }
body:has(#hw7-page-marker) [data-testid="stExpander"] details {
    background: #36242f; border: 1px solid var(--hw7-line); border-radius: 10px;
}
body:has(#hw7-page-marker) [data-testid="stExpander"] summary { color: var(--hw7-rose); padding: .8rem 1rem; }
body:has(#hw7-page-marker) [data-testid="stStatusWidget"] { border-color: var(--hw7-line); background: #382631; }
body:has(#hw7-page-marker) [data-testid="stSpinner"] p { color: var(--hw7-rose); }
body:has(#hw7-page-marker) [data-testid="stAlert"] p { color: inherit; }
.hw7-masthead { padding: .3rem 0 1.5rem; margin-bottom: .35rem; border-bottom: 4px double var(--hw7-line); }
.hw7-kicker { color: var(--hw7-muted); text-transform: uppercase; letter-spacing: .17em; font-size: .74rem; margin: 0 0 .75rem; }
body:has(#hw7-page-marker) .hw7-masthead .hw7-kicker { font-size: .74rem; }
body:has(#hw7-page-marker) .hw7-masthead h1 { font-size: clamp(3.6rem, 7vw, 5.5rem); line-height: .98; letter-spacing: -.045em; margin: 0; padding: 0 0 .5rem; color: var(--hw7-rose); }
.hw7-deck { color: var(--hw7-ink); font-size: 1.25rem; line-height: 1.5; margin: .4rem 0 1.15rem; }
.hw7-archive { display: flex; flex-wrap: wrap; gap: .35rem 1.25rem; color: var(--hw7-muted); font-size: .88rem; }
.hw7-archive span + span { border-left: 1px solid var(--hw7-line); padding-left: 1.25rem; }
.hw7-sidebar-head { padding: .25rem 0 1rem; border-bottom: 1px solid var(--hw7-line); margin-bottom: .25rem; }
.hw7-sidebar-head h2 { margin: 0 0 .35rem; padding: 0; font-size: 1.6rem; color: var(--hw7-rose); }
.hw7-sidebar-head p { margin: 0; color: var(--hw7-muted); font-size: .86rem; }
.hw7-lens-strip { display: flex; flex-wrap: wrap; align-items: baseline; gap: .3rem .8rem; padding: .9rem 0; margin-bottom: .3rem; border-bottom: 1px solid var(--hw7-line); }
.hw7-lens-strip .hw7-kicker { font-size: .68rem; margin: 0; }
.hw7-lens-strip strong { color: var(--hw7-rose); font-weight: 400; font-size: 1.1rem; }
.hw7-lens-strip .hw7-goal { color: var(--hw7-muted); font-size: .95rem; }
.hw7-empty { margin: 1.35rem 0 2rem; padding: 1.6rem 1.7rem; border-left: 2px solid #bb829e; background: rgba(72,43,60,.3); }
.hw7-empty h2 { padding: 0; margin: 0 0 .6rem; font-size: 1.85rem; line-height: 1.2; }
.hw7-empty p { margin: 0; color: var(--hw7-muted); line-height: 1.65; font-size: 1rem; max-width: 42rem; }
.hw7-answer-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: .5rem; padding: .25rem 0 .85rem; border-bottom: 1px solid var(--hw7-line); margin-bottom: .65rem; }
.hw7-answer-head span { color: var(--hw7-muted); font-size: .75rem; letter-spacing: .12em; text-transform: uppercase; }
.hw7-answer-head .hw7-answer-lens { color: var(--hw7-rose); }
.hw7-source-panel { background: var(--hw7-paper); border: 1px solid #dac0ce; border-left: 3px solid #b27b96; border-radius: 5px; padding: 1.4rem 1.5rem; margin: .6rem 0 0; }
body:has(#hw7-page-marker) .hw7-source-panel .hw7-source-kicker { color: #775667; font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; margin: 0 0 .6rem; }
body:has(#hw7-page-marker) .hw7-source-panel h3 { color: var(--hw7-paper-ink); font-size: 1.35rem; font-weight: 600; line-height: 1.35; padding: 0; margin: 0 0 .5rem; }
body:has(#hw7-page-marker) .hw7-source-panel .hw7-source-meta { color: #755063; font-size: .88rem; margin: 0 0 1rem; }
body:has(#hw7-page-marker) .hw7-source-panel .hw7-source-label { color: #755063; border-top: 1px solid #cfb3c2; padding-top: .9rem; margin: 0 0 .4rem; font-size: .74rem; letter-spacing: .1em; text-transform: uppercase; }
body:has(#hw7-page-marker) .hw7-source-panel .hw7-source-text { color: var(--hw7-paper-ink); font-size: 1.02rem; line-height: 1.7; margin: 0 0 1rem; white-space: pre-wrap; overflow-wrap: anywhere; }
body:has(#hw7-page-marker) .hw7-source-panel a { color: #713b58; font-size: .95rem; font-weight: 600; text-decoration: underline; }
@media (max-width: 640px) {
    body:has(#hw7-page-marker) [data-testid="stMainBlockContainer"] { padding: 4.3rem 1.1rem 3rem; }
    body:has(#hw7-page-marker) [data-testid="stChatMessage"] { padding: 1rem .85rem; }
    body:has(#hw7-page-marker) [data-testid="stChatMessageAvatarCustom"],
    body:has(#hw7-page-marker) [data-testid="stChatMessageAvatarAssistant"],
    body:has(#hw7-page-marker) [data-testid="stChatMessageAvatarUser"] { display: none; }
    body:has(#hw7-page-marker) [data-testid="stChatMessage"] [data-testid="stExpanderDetails"] { padding: .8rem .6rem; }
    body:has(#hw7-page-marker) [data-testid="stChatMessage"] ol { padding-left: 1.5rem; }
    body:has(#hw7-page-marker) [data-testid="stChatMessage"] ol > li { padding-left: .2rem; }
    .hw7-archive { gap: .25rem .9rem; }
    .hw7-archive span + span { border-left: 0; padding-left: 0; }
    .hw7-empty { padding: 1rem; margin: .65rem 0 1rem; }
    .hw7-source-panel { padding: 1.1rem; }
    body:has(#hw7-page-marker) .hw7-source-panel h3 { font-size: 1.2rem; }
}
@media (prefers-reduced-motion: reduce) {
    body:has(#hw7-page-marker) * { scroll-behavior: auto !important; transition: none !important; }
}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)

AVATARS = {"user": ":material/person:", "assistant": ":material/gavel:"}

openai_api_key = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=openai_api_key)

DB_PATH = os.path.join(os.path.dirname(__file__), "HW7_ChromaDB")
COLLECTION_NAME = "HW7News"
EMBEDDING_MODEL = "text-embedding-3-small"

# The two models for step 4 (one lower cost, one higher cost). Both take
# function tools on /v1/chat/completions; gpt-6-astra doesn't (see HW5.py).
MODELS = {
    "gpt-5-mini \u00b7 lower cost": "gpt-5-mini",
    "gpt-5.4 \u00b7 higher cost": "gpt-5.4",
}
BUFFER_TURNS = 5   # short-term memory: the last 5 user/assistant pairs
N_RESULTS = 8      # articles search_news returns
MAX_ROUNDS = 4     # tool rounds before the model has to answer


# ---------- Loading the saved database (no building here) ----------
@st.cache_resource(show_spinner=False)
def get_collection():
    try:
        return chromadb.PersistentClient(path=DB_PATH).get_collection(COLLECTION_NAME)
    except Exception:
        return None


collection = get_collection()
if collection is None:
    st.error("HW7_ChromaDB/ isn\u2019t here yet. Run python HW/build_HW7_db.py first.")
    st.stop()


@st.cache_resource(show_spinner=False)
def load_articles():
    # Every record once, for list_headlines and for turning ids into links.
    got = collection.get(include=["documents", "metadatas"])
    articles = {}
    for article_id, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
        headline = doc.split(" Description:")[0].strip()
        articles[article_id] = {
            "id": article_id,
            "company": meta["company"],
            "date": meta["date"],
            "url": meta["url"],
            "headline": headline,
            "text": doc,
        }
    return dict(sorted(articles.items()))


ARTICLES = load_articles()
COMPANIES = sorted({a["company"] for a in ARTICLES.values()})
DATES = sorted(a["date"] for a in ARTICLES.values())


def pretty_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


SPAN = f"{pretty_date(DATES[0]).rsplit(',', 1)[0]} \u2013 {pretty_date(DATES[-1])}"


def embed_many(texts):
    # Same as HW 5: one call per batch, with the 403 retry.
    for attempt in range(6):
        try:
            response = client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
            return [item.embedding for item in response.data]
        except PermissionDeniedError:
            if attempt == 5:
                raise
            time.sleep(2)


def match_company(name):
    # "JPMorgan" -> "JPMorgan Chase", "disney" -> "Walt Disney". No match -> None.
    if not name:
        return None
    wanted = name.strip().lower()
    for company in COMPANIES:
        if company.lower() == wanted:
            return company
    partial = [c for c in COMPANIES if wanted in c.lower() or c.lower() in wanted]
    return partial[0] if len(partial) == 1 else None


def record(article):
    # How one article is shown to the model.
    return f"[{article['id']}] {article['company']} \u00b7 {article['date']}\n{article['text']}"


# ---------- The three tools ----------
def search_news(query, company=None, n=N_RESULTS):
    # RAG: embed the query and pull the closest articles from Chroma,
    # optionally only from one client's articles.
    match = match_company(company)
    where = {"company": match} if match else None
    results = collection.query(query_embeddings=embed_many([query]), n_results=n, where=where)
    hits = [ARTICLES[i] for i in results["ids"][0] if i in ARTICLES]
    text = "\n\n".join(record(a) for a in hits) or "No articles matched."
    scope = f" in {match}\u2019s articles" if match else ""
    return text, f"Searched \u201c{query}\u201d{scope} \u2192 {len(hits)} articles"


def list_headlines():
    # Every headline (about 22,000 tokens), so a ranking covers the whole week.
    lines = [f"[{a['id']}] {a['company']} ({a['date']}): {a['headline']}" for a in ARTICLES.values()]
    return "\n".join(lines), f"Read all {len(lines):,} headlines"


def get_articles(ids):
    found = [ARTICLES[i] for i in ids if i in ARTICLES]
    missing = [i for i in ids if i not in ARTICLES]
    text = "\n\n".join(record(a) for a in found)
    if missing:
        text += "\n\nNot in the file: " + ", ".join(missing)
    return text, f"Opened {len(found)} saved records"


def run_tool(name, args):
    if name == "search_news":
        return search_news(args.get("query", ""), args.get("company"))
    if name == "list_headlines":
        return list_headlines()
    if name == "get_articles":
        return get_articles(args.get("ids", []))
    return f"Unknown tool: {name}", f"Unknown tool {name}"


TOOLS = [
    {"type": "function", "function": {
        "name": "search_news",
        "description": (
            "Vector search over the firm\u2019s news file. Returns the closest articles "
            "with id, company, date, and saved text. Use it for \u201cfind news about X\u201d "
            "(a client, a topic, an event) and for follow-ups about one story."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "A short plain-language search, like JPMorgan Zelle dispute or layoffs."},
            "company": {"type": "string", "description": "Optional: one client\u2019s name, to search only its articles."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "list_headlines",
        "description": (
            "Every headline in the news file (about 1,082), each with its id, company, "
            "and date. Use it for \u201cmost interesting\u201d requests, so the ranking covers the whole week."
        ),
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_articles",
        "description": (
            "The saved text of specific articles, by id. After list_headlines, open your "
            "candidates with this before writing about them."
        ),
        "parameters": {"type": "object", "properties": {
            "ids": {"type": "array", "items": {"type": "string"}, "description": "Article ids like news-0042."},
        }, "required": ["ids"]},
    }},
]

# ---------- Prompt engineering: what "interesting" means ----------
# The first sentence is Diva's definition, shared by every lens. Each lens
# then gives "interesting" one specific goal - pick one in the sidebar.
INTERESTING = (
    "\u201cInteresting\u201d is not one score. As a word it can be generative of so many "
    "affective, somatic, and cognitive states, and part of your job is to say which ones "
    "a story could invite in a lawyer at the firm."
)

STRICT_CLIENT = (
    "Skip articles that aren\u2019t actually about the named client (for example a "
    "different NEC, or a restaurant called Cisco\u2019s)."
)
LOOSE_CLIENT = (
    "The company an article is filed under is a hint, not a boundary. If an article "
    "isn\u2019t actually about that company, say so in its reading, and keep it only if it "
    "bears on a client or the firm\u2019s work another way: a competitor, a supplier, a "
    "regulator, an industry, or a kind of lawsuit that could reach a client."
)

LENSES = {
    "Exposure": {
        "goal": "Catch legal risk and legal work for a client.",
        "rule": (
            "Rank highest the stories that could create legal exposure or legal work for a "
            "client: lawsuits, investigations, regulators, enforcement, major disputes, and "
            "plaintiff-firm activity. Then transactions that will need lawyers (acquisitions, "
            "mergers, large financings), then sharp changes (leadership exits, layoffs, "
            "crises). Routine product news, market-size reports, promotions, and stock tips "
            "rank low."
        ),
        "client": STRICT_CLIENT,
    },
    "Stakes": {
        "goal": "Size what\u2019s at stake for a client.",
        "rule": (
            "Rank by what is at stake for a client, using the amounts in the saved text: deal "
            "values, financings, fines, settlements, damages, valuations. In each reading say "
            "what the amount is for and whose it is. A market-size forecast, a discount, or a "
            "price is not a stake. When there is no amount, judge the scale the record describes."
        ),
        "client": STRICT_CLIENT,
    },
    "Affect": {
        "goal": "Name what a story could do to the person reading it.",
        "rule": (
            "Rank by how strongly a story could move a lawyer at the firm: the intensity and "
            "mix of affective, somatic, and cognitive responses it invites, such as alarm, "
            "urgency, curiosity, a jolt, unease, or relief. In each reading, name the responses "
            "and what in the saved text invites them; several can coexist, including competing ones."
        ),
        "client": STRICT_CLIENT,
    },
    "Offstage": {
        "goal": "Bring back what the filing leaves out.",
        "rule": (
            "Look past the company each article is filed under. Rank highest the stories that "
            "bear on clients indirectly (through a competitor, a supplier, a regulator, an "
            "industry, or a kind of lawsuit that could reach a client) and the stories filed "
            "under a client they aren\u2019t actually about that still matter to the firm. Say "
            "plainly when an article is misfiled, and why a firm might still care."
        ),
        "client": LOOSE_CLIENT,
    },
}


def system_prompt(top_n, lens):
    return (
        f"You are the news desk for a large global law firm. You report only on the "
        f"firm\u2019s news file: {len(ARTICLES):,} articles about {len(COMPANIES)} client "
        f"companies, from {SPAN}. Never use outside knowledge about these events, and never "
        f"invent articles, quotes, numbers, or links.\n\n"
        f"WHAT \u201cINTERESTING\u201d MEANS HERE\n{INTERESTING}\n"
        f"This brief uses the {lens} lens. Its goal: {LENSES[lens]['goal']} "
        f"{LENSES[lens]['rule']}\n\n"
        f"FOR \u201cMOST INTERESTING\u201d REQUESTS (the brief)\n"
        f"Call list_headlines, pick candidates, open them with get_articles, then rank the "
        f"top {top_n}, most interesting first. One entry per story: if two outlets cover the "
        f"same story, keep one. Treat plaintiff-firm class-action notices about one company "
        f"as a single story. {LENSES[lens]['client']}\n"
        f"Write each entry as a numbered item: the headline in bold, then an em dash, the "
        f"company, a middle dot, the date, and the id in square brackets. Under it, one "
        f"paragraph that begins \u201cReading:\u201d and says why the story may warrant a "
        f"lawyer\u2019s attention: what kind of interesting it is, the responses it could "
        f"invite (affective, somatic, cognitive; several can coexist, including competing "
        f"ones), and what in the saved text supports that reading. Stay proportionate to "
        f"what the record actually says.\n\n"
        f"FOR \u201cNEWS ABOUT X\u201d REQUESTS\n"
        f"Call search_news (pass the client\u2019s name as company when X is a client). "
        f"List the relevant articles newest first in the same entry format, with one or two "
        f"sentences on what each reports. If nothing in the file is about X, say so plainly.\n\n"
        f"ALWAYS\nCite every article by its id in square brackets, exactly as given, like "
        f"[news-0042]; the app turns ids into links, so never write URLs. For anything else, "
        f"answer briefly and say what you can do."
    )


# ---------- One turn: tool rounds, then the answer ----------
def ask_model(model, payload, status):
    steps, usage = [], {"in": 0, "out": 0}

    def count(resp):
        if getattr(resp, "usage", None):
            usage["in"] += resp.usage.prompt_tokens or 0
            usage["out"] += resp.usage.completion_tokens or 0

    for _ in range(MAX_ROUNDS):
        resp = client.chat.completions.create(
            model=model, messages=payload, tools=TOOLS, tool_choice="auto"
        )
        count(resp)
        reply = resp.choices[0].message
        if not reply.tool_calls:
            return reply.content or "", steps, usage
        payload.append({
            "role": "assistant",
            "content": reply.content,
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in reply.tool_calls
            ],
        })
        for c in reply.tool_calls:
            result, step = run_tool(c.function.name, json.loads(c.function.arguments or "{}"))
            steps.append(step)
            status.write(step)
            payload.append({"role": "tool", "tool_call_id": c.id, "content": result})

    # Out of tool rounds: one last call without tools, so it has to answer.
    resp = client.chat.completions.create(model=model, messages=payload)
    count(resp)
    return resp.choices[0].message.content or "", steps, usage


def display_text(text, *, markdown=True, emphasize_reading=False):
    """Curl prose punctuation only; retain code and Markdown targets verbatim."""
    protected = []

    def keep(value):
        protected.append(value)
        return f"\ue000{len(protected) - 1}\ue001"

    if markdown:
        offset = 0
        fence = re.compile(r"(?m)^ {0,3}(`{3,}|~{3,})[^\n]*(?:\n|$)")
        while match := fence.search(text, offset):
            mark = match[1]
            closing = re.search(r"(?m)^ {0,3}" + re.escape(mark[0]) +
                                "{" + str(len(mark)) + r",}[ \t]*(?:\n|$)", text[match.end():])
            end = match.end() + closing.end() if closing else len(text)
            end -= int(end > match.start() and text[end - 1] == "\n")
            token = keep(text[match.start():end])
            text = text[:match.start()] + token + text[end:]
            offset = match.start() + len(token)
        text = re.sub(r"(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)", lambda m: keep(m[0]), text)
        text = re.sub(r"(?m)^ {0,3}\[[^\]\n]+\]:[^\n]*", lambda m: keep(m[0]), text)
        text = re.sub(r"<(?:https?://|mailto:)[^>\n]+>", lambda m: keep(m[0]), text)
        text = re.sub(r"(?<=\])\[[^\]\n]*\]", lambda m: keep(m[0]), text)
        offset = 0
        while match := re.search(r"\]\(", text[offset:]):
            start = offset + match.end() - 1
            end, depth = start + 1, 1
            while end < len(text) and depth:
                if text[end] == "\\":
                    end += 2
                    continue
                depth += (text[end] == "(") - (text[end] == ")")
                end += 1
            if depth:
                offset = start + 1
                continue
            token = keep(text[start:end])
            text = text[:start] + token + text[end:]
            offset = start + len(token)
    if emphasize_reading:
        text = re.sub(r"(?m)^([ \t]*)Reading:", r"\1**Reading:**", text)
    text = re.sub(r'''(^|[\s(\[{*_>—–-])"''', r"\1“", text).replace('"', "”")
    text = re.sub(r"(^|[\s(\[{*_>—–-])'", r"\1‘", text).replace("'", "’")
    for index in range(len(protected) - 1, -1, -1):
        text = text.replace(f"\ue000{index}\ue001", protected[index])
    return text

class ReadingStatus:
    # Keep tool results and stored steps raw while styling their live display.
    def __init__(self, status):
        self.status = status

    def write(self, text):
        self.status.write(display_text(text))


ID_PATTERN = re.compile(r"\[?\b(news-\d{4})\b\]?")


def cited_ids(text):
    seen = []
    for i in ID_PATTERN.findall(text):
        if i in ARTICLES and i not in seen:
            seen.append(i)
    return seen


def linkify(text):
    # [news-0042] -> a link to the original article, from the database.
    def swap(m):
        article = ARTICLES.get(m.group(1))
        return f"[source \u2197]({article['url']})" if article else m.group(0)
    return ID_PATTERN.sub(swap, text)


def show_sources(ids, message_index=0):
    # The three-part split: the bot's reading is the answer above; here are
    # the saved records it read, and the original publisher's page.
    if not ids:
        return
    with st.expander(f"Saved records behind this answer ({len(ids)})"):
        st.caption("Read the saved text, open the original, or follow the company.")
        for number, i in enumerate(ids, 1):
            a = ARTICLES[i]
            # Escape all saved content before putting it on the paper panel.
            # Typography is display-only; ARTICLES and the tool output stay raw.
            st.markdown(
                '<article class="hw7-source-panel">'
                f'<p class="hw7-source-kicker">Saved record {number:02d} · {escape(i)}</p>'
                f'<h3>{escape(display_text(a["headline"], markdown=False))}</h3>'
                f'<p class="hw7-source-meta">{escape(display_text(a["company"], markdown=False))}'
                f' · {escape(pretty_date(a["date"]))}</p>'
                '<p class="hw7-source-label">Saved article text</p>'
                f'<p class="hw7-source-text">{escape(display_text(a["text"], markdown=False))}</p>'
                f'<a href="{escape(a["url"], quote=True)}" target="_blank" '
                'rel="noopener noreferrer">Original article ↗</a>'
                '</article>',
                unsafe_allow_html=True,
            )
            st.button(
                f'More news about {display_text(a["company"])} →',
                key=f"HW7_source_client_{message_index}_{i}",
                on_click=ask, args=(f'Find news about {a["company"]}',),
                use_container_width=True,
            )


# ---------- The page ----------
st.sidebar.markdown(
    '<div class="hw7-sidebar-head"><h2>Shape the reading.</h2>'
    '<p>Settings apply to your next request.</p></div>',
    unsafe_allow_html=True,
)
st.sidebar.markdown("**Model**")
model_label = st.sidebar.radio(
    "Model", list(MODELS), label_visibility="collapsed", key="HW7_model",
    help="Ask the same question on both to compare them (step 4).",
)
st.sidebar.markdown("**Lens**")
lens = st.sidebar.radio(
    "Lens", list(LENSES), label_visibility="collapsed", key="HW7_lens",
    help="Each lens gives \u201cinteresting\u201d one specific goal.",
)
st.sidebar.caption(f"Goal: {LENSES[lens]['goal']}")
top_n = st.sidebar.slider("Stories in a brief", 5, 15, 10, key="HW7_top_n")
st.sidebar.caption(f"{len(ARTICLES):,} articles \u00b7 {len(COMPANIES)} clients \u00b7 loaded from HW7_ChromaDB/")

if "HW7_messages" not in st.session_state:
    st.session_state.HW7_messages = []

if st.sidebar.button("Clear conversation", key="HW7_clear"):
    st.session_state.HW7_messages = []
    st.rerun()


def ask(text):
    st.session_state.HW7_pending = text


def ask_client():
    company = st.session_state.HW7_client
    if company:
        ask(f"Find news about {company}")
    st.session_state.HW7_client = None


# The two ways in: the brief, or one client's news.
st.markdown(
    f'<style>body:has(#hw7-page-marker) {{--hw7-slider-fill: {(top_n - 5) * 10}%;}}</style>'
    '<header class="hw7-masthead">'
    '<p class="hw7-kicker">HW 07 / Client intelligence / Article archive</p>'
    '<h1>The Brief.</h1>'
    '<p class="hw7-deck">A reading of the news, with room for why it matters.</p>'
    '<div class="hw7-archive">'
    f'<span>{len(ARTICLES):,} saved articles</span>'
    f'<span>{len(COMPANIES)} client companies</span>'
    f'<span>{SPAN}</span>'
    '</div></header>',
    unsafe_allow_html=True,
)
left, right = st.columns(2)
left.caption("ACROSS THE ARCHIVE")
left.button(
    "\u2726 Most interesting this week", on_click=ask,
    args=("Find the most interesting news",), key="HW7_brief",
    type="primary", use_container_width=True,
)
right.caption("FOLLOW A CLIENT")
right.selectbox(
    "News about a client", COMPANIES, index=None, key="HW7_client",
    placeholder="News about a client\u2026", on_change=ask_client, label_visibility="collapsed",
    format_func=display_text,
)
st.markdown(
    '<div class="hw7-lens-strip"><span class="hw7-kicker">Next reading</span>'
    f'<strong>{lens}</strong><span class="hw7-goal">{LENSES[lens]["goal"]}</span>'
    '</div>',
    unsafe_allow_html=True,
)
if not st.session_state.HW7_messages and not st.session_state.get("HW7_pending"):
    st.markdown(
        '<section class="hw7-empty"><h2>What deserves your attention?</h2>'
        '<p>Start with a ranked brief, follow a client, or ask about a topic. '
        'Each \u201cReading:\u201d explains what the story could invite in a lawyer, '
        'with the saved article close at hand.</p></section>',
        unsafe_allow_html=True,
    )


def footer(msg):
    parts = [msg["model"]] + ([f"{msg['lens']} lens"] if msg.get("lens") else []) + msg["steps"]
    parts.append(f"{msg['tokens_in']:,} tokens in / {msg['tokens_out']:,} out")
    parts.append(f"{msg['seconds']:.1f} s")
    return " \u00b7 ".join(parts)


def show_answer(msg, message_index):
    # One renderer for new and replayed answers; old answers keep their own lens.
    lens_label = f'{msg["lens"]} lens' if msg.get("lens") else ""
    st.markdown(
        '<div class="hw7-answer-head"><span>From the news file</span>'
        f'<span class="hw7-answer-lens">{escape(lens_label)}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(linkify(display_text(msg["content"], emphasize_reading=True)))
    st.caption(display_text(footer(msg)))
    show_sources(cited_ids(msg["content"]), message_index)


for message_index, msg in enumerate(st.session_state.HW7_messages):
    with st.chat_message(msg["role"], avatar=AVATARS[msg["role"]]):
        if msg["role"] == "assistant":
            show_answer(msg, message_index)
        else:
            st.markdown(display_text(msg["content"]))

prompt = st.chat_input(
    "Ask about a client or topic\u2026",
    key="HW7_chat",
)
if not prompt and st.session_state.get("HW7_pending"):
    prompt = st.session_state.pop("HW7_pending")

if prompt:
    st.session_state.HW7_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(display_text(prompt))

    model = MODELS[model_label]
    buffer = st.session_state.HW7_messages[-(BUFFER_TURNS * 2):]
    payload = [{"role": "system", "content": system_prompt(top_n, lens)}] + [
        {"role": m["role"], "content": m["content"]} for m in buffer
    ]

    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        started = time.perf_counter()
        try:
            with st.status("Reading the news file\u2026", expanded=False) as status:
                answer, steps, usage = ask_model(model, payload, ReadingStatus(status))
                status.update(label=display_text(" \u00b7 ".join(steps)) or "Answered directly", state="complete")
        except Exception as error:
            st.error(display_text(f"The model call failed: {error}"))
            st.stop()
        msg = {
            "role": "assistant", "content": answer, "model": model, "lens": lens, "steps": steps,
            "tokens_in": usage["in"], "tokens_out": usage["out"],
            "seconds": time.perf_counter() - started,
        }
        show_answer(msg, len(st.session_state.HW7_messages))
    st.session_state.HW7_messages.append(msg)
