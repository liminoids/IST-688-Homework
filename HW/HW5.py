# Streamlit Cloud fix: Chroma needs a newer sqlite3 than the Cloud has.
# pysqlite3-binary only installs on Linux (see requirements.txt), so on the
# Mac this import fails and we just keep the normal sqlite3.
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
import streamlit as st
from openai import OpenAI, PermissionDeniedError
from bs4 import BeautifulSoup
import chromadb

# HW 5 = HW 4, but the model decides when to search.
#
# In HW 4 the app ran a vector search before EVERY question and pasted the
# hits into the system prompt, whether the question needed them or not. Here
# the search is wrapped in a function, relevant_club_info(query), and handed
# to the LLM as a tool. Each turn the model reads the question and decides:
# "hi" -> no call, just answer; "who runs the sailing club?" -> call the tool,
# with a search query it writes itself. The results come back to the model as
# a tool message and it answers from them on a second call (made without the
# tool, so that second call can only answer, not search again).
#
# The page reading, chunking and vector DB are unchanged from HW 4 - and this
# page points at HW 4's Chroma folder and collection on purpose, so the same
# 1,000-ish chunks are reused instead of being embedded a second time.

# ---------- Styling ----------
# The dark base theme lives in .streamlit/config.toml (so every widget,
# button and nav link is dark). This CSS layers Times New Roman and the
# dusty-pink gradient/bubbles on top of it.
STYLE = """
<style>
/* Times New Roman everywhere except Streamlit's icon font and code */
.stApp :not(span[data-testid="stIconMaterial"]):not(.material-symbols-rounded):not(code):not(pre):not(kbd) {
    font-family: "Times New Roman", Times, serif !important;
}
/* page + chrome */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #2b1d26 0%, #3a2433 50%, #2c2034 100%);
}
[data-testid="stHeader"] { background: rgba(43, 29, 38, 0.8); }
[data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] { background: transparent; }
[data-testid="stSidebar"] { background: #33222d; border-right: 1px solid #5a3b4c; }
/* title + captions */
h1 { color: #e8b4c8; font-weight: 600; letter-spacing: 0.01em; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #c48ca6 !important; }
/* chat bubbles */
[data-testid="stChatMessage"] {
    background: rgba(74, 46, 62, 0.85);
    border: 1px solid #7a4f65;
    border-radius: 18px;
    padding: 0.9rem 1.1rem;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
}
[data-testid="stChatMessage"] p { color: #f3e3ea; line-height: 1.55; }
[data-testid="stChatMessage"] a { color: #e8b4c8; }
/* input box */
[data-testid="stChatInput"] {
    background: #3d2836;
    border: 1px solid #8a5a73;
    border-radius: 18px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
}
[data-testid="stChatInput"] textarea { color: #f3e3ea; background: transparent; }
[data-testid="stChatInput"] textarea::placeholder { color: #b78aa0; }
/* buttons */
.stButton > button {
    background: #3d2836; color: #f3e3ea;
    border: 1px solid #8a5a73; border-radius: 12px;
}
.stButton > button:hover { border-color: #e8b4c8; color: #e8b4c8; }
/* the spinner / status text */
[data-testid="stSpinner"] p { color: #e8b4c8; }
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)

AVATARS = {"user": ":material/person:", "assistant": ":material/school:"}

st.title("iSchool Student Organizations")
st.caption(
    "HW 5 \u00b7 the HW 4 chatbot, but the model now decides when to look "
    "things up: it holds relevant_club_info as a tool and calls it only when a "
    "question is about an org. Ask who does what, where they meet, and how to join."
)

openai_api_key = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=openai_api_key)

# The ~500 org pages (one HTML file per organization, saved from
# syracuse.campuslabs.com) live in su_orgs/ next to this file.
HTML_FOLDER = os.path.join(os.path.dirname(__file__), "su_orgs")

# Same on-disk DB and collection as HW 4 (same pages, same chunks), so the
# embeddings are only ever paid for once. If the folder isn't there - as on a
# fresh Streamlit Cloud deploy, since it's gitignored - it gets built below.
DB_PATH = os.path.join(os.path.dirname(__file__), "HW4_ChromaDB")
COLLECTION_NAME = "HW4Collection"
EMBEDDING_MODEL = "text-embedding-3-small"
CHUNKS_PER_DOC = 2


# ---------- Reading the HTML pages (unchanged from HW 4) ----------
def read_html(path):
    # Each campuslabs page carries the org's structured record in a JSON blob
    # (window.initialAppState) plus the rendered page text. The JSON has fields
    # the visible page does NOT show - "summary" and the org type (for example
    # "The School of Information Studies (iSchool)") - so we pull those out and
    # combine them with the visible text.
    html = open(path, encoding="utf-8", errors="ignore").read()

    name = summary = org_type = ""
    match = re.search(r"window\.initialAppState = (\{.*?\});\s*</script>", html, re.S)
    if match:
        try:
            org = json.loads(match.group(1))["preFetchedData"]["organization"]
            name = org.get("name") or ""
            summary = org.get("summary") or ""
            org_type = (org.get("organizationType") or {}).get("name") or ""
        except (ValueError, KeyError, TypeError):
            pass

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    lines = [line for line in lines if len(line) > 1]   # drops blanks + avatar initials
    if lines and lines[0].endswith("- 'Cuse Activities"):
        lines.pop(0)                                    # the browser tab title
    if not name and lines:
        name = lines[0]

    # Most orgs left most of their profile questions blank. Drop each
    # "Label:" + "No Response" pair so the empty fields don't get embedded
    # as if they were content.
    cleaned = []
    for line in lines:
        if line == "No Response":
            if cleaned and cleaned[-1][-1] in ":?.":
                cleaned.pop()
            continue
        cleaned.append(line)

    return name, summary, org_type, cleaned


# ---------- Chunking (unchanged from HW 4) ----------
# Section-based (structural) chunking, two chunks per page, split at the
# page's own "Additional Information" heading:
#   chunk 1 ("about")   = what the org IS   - name, type, summary, About text, email
#   chunk 2 ("details") = how the org RUNS  - meetings, officers, membership process, events
# The two sections answer two different kinds of question, so splitting on
# the page's structure keeps each chunk coherent; the org name is repeated
# at the top of both so a "details" chunk still embeds as being about it.
def chunk_document(name, summary, org_type, lines):
    header = f"Organization: {name}\nType: {org_type}\nSummary: {summary}"
    try:
        cut = lines.index("Additional Information")
    except ValueError:
        cut = len(lines) // 2
    about = header + "\n" + "\n".join(lines[:cut])
    details = f"Organization: {name}\n" + "\n".join(lines[cut:])
    return about, details


def embed_many(texts):
    # One call embeds a whole batch (much faster than one call per chunk).
    # The 403 retry is for OpenAI's allowed-models change still propagating.
    for attempt in range(6):
        try:
            response = client.embeddings.create(
                input=[t[:28000] for t in texts], model=EMBEDDING_MODEL
            )
            return [item.embedding for item in response.data]
        except PermissionDeniedError:
            if attempt == 5:
                raise
            time.sleep(2)


# ---------- The vector DB (unchanged from HW 4) ----------
html_files = (
    sorted(f for f in os.listdir(HTML_FOLDER) if f.lower().endswith(".html"))
    if os.path.isdir(HTML_FOLDER) else []
)
if not html_files:
    st.error("No HTML files found in su_orgs/ - unzip the org pages in first.")
    st.stop()

EXPECTED_CHUNKS = len(html_files) * CHUNKS_PER_DOC


@st.cache_resource(show_spinner=False)
def get_collection():
    # PersistentClient reads the DB from disk if it's there, or creates the
    # folder if it isn't. Either way this is cheap; the expensive part is
    # only the build below, and that only runs when the DB doesn't exist yet.
    chroma_client = chromadb.PersistentClient(path=DB_PATH)
    return chroma_client.get_or_create_collection(name=COLLECTION_NAME)


def create_vectordb(collection):
    # Build the collection from the HTML pages, two chunks per page.
    # Skip any chunk id already in the collection so an interrupted build
    # is finished instead of restarted (and so this is a no-op when the
    # DB already exists).
    already_in = set(collection.get()["ids"])

    ids, docs, metas = [], [], []
    for filename in html_files:
        name, summary, org_type, lines = read_html(os.path.join(HTML_FOLDER, filename))
        about, details = chunk_document(name, summary, org_type, lines)
        for part, text in (("about", about), ("details", details)):
            chunk_id = f"{filename}::{part}"
            if chunk_id in already_in:
                continue
            ids.append(chunk_id)
            docs.append(text)
            metas.append({"org": name, "part": part, "filename": filename})

    # Embed and insert in batches of 100
    for start in range(0, len(ids), 100):
        batch = slice(start, start + 100)
        collection.add(
            ids=ids[batch],
            documents=docs[batch],
            embeddings=embed_many(docs[batch]),
            metadatas=metas[batch],
        )
    return collection


collection = get_collection()

# Create the vector DB only if it does not already exist.
# "Exists" = the folder is on disk AND it holds every chunk we expect
# (the second half of the check finishes a build that was cut short).
if collection.count() < EXPECTED_CHUNKS:
    with st.spinner(
        f"Building the vector database from {len(html_files)} org pages "
        "(first run only)..."
    ):
        create_vectordb(collection)


# ---------- The chatbot ----------
MODEL = "gpt-5-mini"
# Not gpt-6-astra (HW 4's model): on /v1/chat/completions it only takes
# function tools with reasoning switched off, and it doesn't let you switch
# reasoning off - so it can't do this assignment on this endpoint. gpt-5-mini
# is the model Lab 5's tool-calling bot already runs on.
BUFFER_TURNS = 5   # short-term memory: the last 5 interactions (user/assistant pairs)
N_RESULTS = 5      # chunks the tool returns per search

# The system prompt flips from HW 4's "the app has already searched and pasted
# the excerpts below" to "you have a search tool - use it when you need it."
SYSTEM_PROMPT = (
    "You are a helpful assistant for Syracuse University\u2019s iSchool that answers "
    "questions about student organizations. You have one tool, "
    "relevant_club_info(query), which searches a vector database of ~500 "
    "\u2019Cuse Activities organization pages (one page per org) and returns the "
    "closest excerpts; every excerpt header carries the org\u2019s name and its page "
    "URL. Call it whenever a question concerns a student organization or club, "
    "and write the query yourself in plain language (the org\u2019s name, the topic, "
    "or what the user wants to know). Follow-ups count too: excerpts are not kept "
    "between turns, so if the user asks about an org discussed earlier, search "
    "again and name that org in your query. Do not call it for greetings, thanks, "
    "or questions that have nothing to do with student organizations.\n"
    "Answer from the excerpts, name the organization(s) you drew on, and end with "
    "the page URL of every org you answered from. The org pages are your only "
    "source: do not offer to fetch links, check social media, or look anywhere "
    "else. Many pages are sparse: if the "
    "excerpts don\u2019t contain the detail asked for (a meeting time, an officer), "
    "say the page doesn\u2019t list it rather than guessing. If you answer from "
    "general knowledge, label it as such."
)

URL_PREFIX = "syracuse.campuslabs.com_engage_organization_"


def org_url(filename):
    # The saved filename encodes the page's address:
    #   syracuse.campuslabs.com_engage_organization_<slug>.html
    slug = filename[len(URL_PREFIX):] if filename.startswith(URL_PREFIX) else filename
    slug = slug[:-5] if slug.lower().endswith(".html") else slug
    return f"https://syracuse.campuslabs.com/engage/organization/{slug}"


def retrieve(query, n=N_RESULTS):
    # The vector search: embed the query, get the n closest chunks from Chroma.
    results = collection.query(query_embeddings=embed_many([query]), n_results=n)
    return [
        {"label": f"{m['org']} ({m['part']})", "url": org_url(m["filename"]), "text": text}
        for m, text in zip(results["metadatas"][0], results["documents"][0])
    ]


# ---------- Step 3: the tool ----------
# What the model is told about the function. The description is what it uses
# to decide whether a given question calls for a search; the "query" parameter
# is the search string it writes.
TOOLS = [{
    "type": "function",
    "function": {
        "name": "relevant_club_info",
        "description": (
            "Search the \u2019Cuse Activities pages of ~500 Syracuse University student "
            "organizations and return the closest excerpts: the org\u2019s name, type, "
            "summary, meetings, officers, how to join, and its page URL. Call this "
            "whenever the question is about a student organization or club."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A short plain-language search, like an org name plus "
                        "what you want to know (e.g. Sailing meeting times). "
                        "No keyword lists or quotes."
                    ),
                }
            },
            "required": ["query"],
        },
    },
}]


def relevant_club_info(query, n=N_RESULTS):
    # Step 3a: takes the query the LLM wrote, runs the vector search, and
    # returns the relevant information from the ChromaDB collection as one
    # text block (what goes back to the model), plus the chunk labels (what
    # the caption under the answer shows).
    hits = retrieve(query, n)
    text = "\n\n".join(f"=== {h['label']} | {h['url']} ===\n{h['text']}" for h in hits)
    return text, [h["label"] for h in hits]


def source_caption(queries, labels):
    # The line under each answer: what the model searched for and what came
    # back - or that it chose not to search at all.
    if not queries:
        return "Answered without searching"
    searched = "; ".join(f"\u201c{q}\u201d" for q in queries)
    return f"Searched {searched} \u00b7 Retrieved: " + ", ".join(labels)


st.sidebar.caption(
    f"{len(html_files)} organizations / {collection.count()} chunks loaded"
)

if "HW5_messages" not in st.session_state:
    st.session_state.HW5_messages = []

# Wipe the memory buffer (the DB is untouched)
if st.sidebar.button("Clear conversation"):
    st.session_state.HW5_messages = []
    st.rerun()

# Show the conversation so far (with what each answer searched and used)
for msg in st.session_state.HW5_messages:
    with st.chat_message(msg["role"], avatar=AVATARS[msg["role"]]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            st.caption(source_caption(msg.get("queries", []), msg.get("sources", [])))

if prompt := st.chat_input("Ask about a student organization\u2026"):
    st.session_state.HW5_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(prompt)

    # Short-term memory: the last BUFFER_TURNS user/assistant pairs. Only
    # role + content go to the API; the search notes stay in the app.
    buffer = st.session_state.HW5_messages[-(BUFFER_TURNS * 2):]
    payload = [{"role": "system", "content": SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in buffer
    ]

    # Call 1: the model reads the question and decides whether it needs the
    # org pages. Not streamed - we have to look at the reply for a tool call
    # before we know whether there is an answer to show yet.
    with st.spinner("Thinking\u2026"):
        first = client.chat.completions.create(
            model=MODEL, messages=payload, tools=TOOLS, tool_choice="auto"
        )
    reply = first.choices[0].message

    queries, labels = [], []
    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        if reply.tool_calls:
            # Step 3b: run the search(es) the model asked for, show it the
            # results as tool messages, then call again - without the tool
            # this time - for the actual answer.
            payload.append({
                "role": "assistant",
                "content": reply.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in reply.tool_calls
                ],
            })
            for call in reply.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                query = args.get("query", prompt)
                text, hit_labels = relevant_club_info(query)
                queries.append(query)
                labels += [label for label in hit_labels if label not in labels]
                payload.append({"role": "tool", "tool_call_id": call.id, "content": text})

            stream = client.chat.completions.create(
                model=MODEL, messages=payload, stream=True
            )
            response = st.write_stream(stream)
        else:
            # No tool call: the model answered without touching the org pages
            # ("hi", "what can you do?", "thanks").
            response = reply.content or ""
            st.markdown(response)
        st.caption(source_caption(queries, labels))

    st.session_state.HW5_messages.append(
        {"role": "assistant", "content": response, "queries": queries, "sources": labels}
    )
