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

# ---------- Styling (HW 5's look, plus the expanders) ----------
STYLE = """
<style>
.stApp :not(span[data-testid="stIconMaterial"]):not(.material-symbols-rounded):not(code):not(pre):not(kbd) {
    font-family: "Times New Roman", Times, serif !important;
}
[data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #2b1d26 0%, #3a2433 50%, #2c2034 100%);
}
[data-testid="stHeader"] { background: rgba(43, 29, 38, 0.8); }
[data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] { background: transparent; }
[data-testid="stSidebar"] { background: #33222d; border-right: 1px solid #5a3b4c; }
h1 { color: #e8b4c8; font-weight: 600; letter-spacing: 0.01em; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #c48ca6 !important; }
[data-testid="stChatMessage"] {
    background: rgba(74, 46, 62, 0.85);
    border: 1px solid #7a4f65;
    border-radius: 18px;
    padding: 0.9rem 1.1rem;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { color: #f3e3ea; line-height: 1.6; }
[data-testid="stChatMessage"] li { margin-bottom: 0.7rem; }
[data-testid="stChatMessage"] strong { color: #f7d6e3; }
[data-testid="stChatMessage"] a { color: #e8b4c8; }
[data-testid="stChatInput"] {
    background: #3d2836;
    border: 1px solid #8a5a73;
    border-radius: 18px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
}
[data-testid="stChatInput"] textarea { color: #f3e3ea; background: transparent; }
[data-testid="stChatInput"] textarea::placeholder { color: #b78aa0; }
.stButton > button {
    background: #3d2836; color: #f3e3ea;
    border: 1px solid #8a5a73; border-radius: 12px;
}
.stButton > button:hover { border-color: #e8b4c8; color: #e8b4c8; }
[data-testid="stExpander"] details {
    background: rgba(61, 40, 54, 0.6);
    border: 1px solid #7a4f65;
    border-radius: 14px;
}
[data-testid="stSpinner"] p { color: #e8b4c8; }
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


def show_sources(ids):
    # The three-part split: the bot's reading is the answer above; here are
    # the saved records it read, and the original publisher's page.
    if not ids:
        return
    with st.expander(f"Saved records behind this answer ({len(ids)})"):
        for i in ids:
            a = ARTICLES[i]
            st.markdown(f"**{a['headline']}** \u2014 {a['company']} \u00b7 {pretty_date(a['date'])}")
            st.caption(a["text"])
            st.markdown(f"[Original article \u2197]({a['url']})")


# ---------- The page ----------
st.title("Client News Brief")
st.caption(
    f"HW 7 \u00b7 A news desk for a global law firm. It answers only from "
    f"{len(ARTICLES):,} saved articles about {len(COMPANIES)} clients ({SPAN}). "
    f"Ask for the most interesting news, or for news about a client or topic. "
    f"The lens in the sidebar sets what \u201cinteresting\u201d is for."
)

st.sidebar.markdown("**Model**")
model_label = st.sidebar.radio(
    "Model", list(MODELS), label_visibility="collapsed",
    help="Ask the same question on both to compare them (step 4).",
)
st.sidebar.markdown("**Lens**")
lens = st.sidebar.radio(
    "Lens", list(LENSES), label_visibility="collapsed",
    help="Each lens gives \u201cinteresting\u201d one specific goal.",
)
st.sidebar.caption(f"Goal: {LENSES[lens]['goal']}")
top_n = st.sidebar.slider("Stories in a brief", 5, 15, 10)
st.sidebar.caption(f"{len(ARTICLES):,} articles \u00b7 {len(COMPANIES)} clients \u00b7 loaded from HW7_ChromaDB/")

if "HW7_messages" not in st.session_state:
    st.session_state.HW7_messages = []

if st.sidebar.button("Clear conversation"):
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
left, right = st.columns(2)
left.button("\u2726 Most interesting this week", on_click=ask, args=("Find the most interesting news",))
right.selectbox(
    "News about a client", COMPANIES, index=None, key="HW7_client",
    placeholder="News about a client\u2026", on_change=ask_client, label_visibility="collapsed",
)


def footer(msg):
    parts = [msg["model"]] + ([f"{msg['lens']} lens"] if msg.get("lens") else []) + msg["steps"]
    parts.append(f"{msg['tokens_in']:,} tokens in / {msg['tokens_out']:,} out")
    parts.append(f"{msg['seconds']:.1f} s")
    return " \u00b7 ".join(parts)


for msg in st.session_state.HW7_messages:
    with st.chat_message(msg["role"], avatar=AVATARS[msg["role"]]):
        if msg["role"] == "assistant":
            st.markdown(linkify(msg["content"]))
            st.caption(footer(msg))
            show_sources(cited_ids(msg["content"]))
        else:
            st.markdown(msg["content"])

prompt = st.chat_input("Ask for the most interesting news, or news about a client or topic\u2026")
if not prompt and st.session_state.get("HW7_pending"):
    prompt = st.session_state.pop("HW7_pending")

if prompt:
    st.session_state.HW7_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(prompt)

    model = MODELS[model_label]
    buffer = st.session_state.HW7_messages[-(BUFFER_TURNS * 2):]
    payload = [{"role": "system", "content": system_prompt(top_n, lens)}] + [
        {"role": m["role"], "content": m["content"]} for m in buffer
    ]

    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        started = time.perf_counter()
        try:
            with st.status("Reading the news file\u2026", expanded=False) as status:
                answer, steps, usage = ask_model(model, payload, status)
                status.update(label=" \u00b7 ".join(steps) or "Answered directly", state="complete")
        except Exception as error:
            st.error(f"The model call failed: {error}")
            st.stop()
        msg = {
            "role": "assistant", "content": answer, "model": model, "lens": lens, "steps": steps,
            "tokens_in": usage["in"], "tokens_out": usage["out"],
            "seconds": time.perf_counter() - started,
        }
        st.markdown(linkify(answer))
        st.caption(footer(msg))
        show_sources(cited_ids(answer))
    st.session_state.HW7_messages.append(msg)
