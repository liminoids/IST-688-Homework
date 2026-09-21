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
    "HW 4 \u00b7 a RAG chatbot over the 'Cuse Activities org pages. "
    "Ask who does what, where they meet, and how to join."
)

openai_api_key = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=openai_api_key)

# The ~500 org pages (one HTML file per organization, saved from
# syracuse.campuslabs.com) live in su_orgs/ next to this file.
HTML_FOLDER = os.path.join(os.path.dirname(__file__), "su_orgs")

# The vector DB is written to disk here. Unlike Lab 4 (in-memory client,
# rebuilt every session), a PersistentClient keeps the collection between
# reruns and restarts, so we only pay for embeddings once.
DB_PATH = os.path.join(os.path.dirname(__file__), "HW4_ChromaDB")
COLLECTION_NAME = "HW4Collection"
EMBEDDING_MODEL = "text-embedding-3-small"
CHUNKS_PER_DOC = 2


# ---------- Reading the HTML pages ----------
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


# ---------- Chunking ----------
# CHUNKING METHOD: section-based (structural) chunking, two chunks per page.
#
# Every campuslabs org page has the same layout: a top section (name, About
# blurb, contact email) and, under the heading "Additional Information", the
# profile-question section (description, website, meeting day/time/location,
# officer names, advisor, how to join, then events / officers / documents).
# We split each page at that "Additional Information" heading:
#
#   chunk 1 ("about")   = what the org IS   - name, type, summary, About text, email
#   chunk 2 ("details") = how the org RUNS  - meetings, officers, membership process, events
#
# Why this instead of a fixed-size split (e.g. every N characters or tokens):
#  - These pages are short (a few hundred to ~2,000 characters), so fixed-size
#    chunks would mostly be either the whole page or cuts mid-sentence.
#  - The two sections answer two different kinds of question ("what does X
#    do?" vs "when does X meet / who runs it / how do I join?"), so splitting
#    on the page's own structure keeps each chunk semantically coherent and
#    makes retrieval more precise than an arbitrary character boundary.
#  - The org name is repeated at the top of both chunks so a "details" chunk
#    still embeds as being about that organization.
# If a page is missing the heading (shouldn't happen, but just in case), we
# fall back to splitting the lines at the midpoint.
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
    # The 403 retry is for OpenAI's allowed-models change still propagating,
    # same as in Lab 4.
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


# ---------- The vector DB ----------
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


def create_hw4_vectordb(collection):
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

# Step 2b: create the vector DB only if it does not already exist.
# "Exists" = the folder is on disk AND it holds every chunk we expect
# (the second half of the check finishes a build that was cut short).
if collection.count() < EXPECTED_CHUNKS:
    with st.spinner(
        f"Building the vector database from {len(html_files)} org pages "
        "(first run only)..."
    ):
        create_hw4_vectordb(collection)


# ---------- The chatbot ----------
MODEL = "gpt-6-astra"
BUFFER_TURNS = 5   # step 3a: remember up to the last 5 interactions (user/assistant pairs)
N_RESULTS = 5      # chunks handed to the LLM per question

SYSTEM_PROMPT = (
    "You are a helpful assistant for Syracuse University's iSchool that answers "
    "questions about student organizations. The app you run inside has already "
    "searched a vector database of ~500 'Cuse Activities organization pages (one "
    "page per org) and pasted the closest excerpts below; you do not run that "
    "search yourself. Excerpts kept from the previous question are included too, "
    "so follow-ups like 'links to those' have something to point at.\n"
    "Answer from the excerpts when they apply and name the organization(s) you "
    "drew on. Every excerpt header carries that org's page URL - give it when the "
    "user asks for a link. Retrieval happens per question, so an org discussed "
    "earlier may simply not appear in this turn's excerpts; that does not mean it "
    "doesn't exist or wasn't in the pages, so don't retract earlier answers - just "
    "say it wasn't retrieved this time. Many pages are sparse: if the excerpts "
    "don't contain the detail asked for (a meeting time, an officer), say the page "
    "doesn't list it rather than guessing. If you answer from general knowledge, "
    "label it as such."
)

URL_PREFIX = "syracuse.campuslabs.com_engage_organization_"


def org_url(filename):
    # The saved filename encodes the page's address:
    #   syracuse.campuslabs.com_engage_organization_<slug>.html
    slug = filename[len(URL_PREFIX):] if filename.startswith(URL_PREFIX) else filename
    slug = slug[:-5] if slug.lower().endswith(".html") else slug
    return f"https://syracuse.campuslabs.com/engage/organization/{slug}"


def retrieve(question, n=N_RESULTS):
    # The RAG step: embed the question, get the n closest chunks from Chroma.
    results = collection.query(query_embeddings=embed_many([question]), n_results=n)
    return [
        {"label": f"{m['org']} ({m['part']})", "url": org_url(m["filename"]), "text": text}
        for m, text in zip(results["metadatas"][0], results["documents"][0])
    ]


st.sidebar.caption(
    f"{len(html_files)} organizations / {collection.count()} chunks loaded"
)

if "HW4_messages" not in st.session_state:
    st.session_state.HW4_messages = []

# Wipe the memory buffer (the DB is untouched)
if st.sidebar.button("Clear conversation"):
    st.session_state.HW4_messages = []
    st.session_state.HW4_last_hits = []
    st.rerun()

# Show the conversation so far (with the sources each answer used)
for msg in st.session_state.HW4_messages:
    with st.chat_message(msg["role"], avatar=AVATARS[msg["role"]]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            st.caption("Retrieved: " + ", ".join(msg["sources"]))

if prompt := st.chat_input("Ask about a student organization..."):
    st.session_state.HW4_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(prompt)

    # Retrieval query = this question plus the previous one, so a follow-up
    # like "when do they meet?" still points at the org just discussed.
    earlier = [m["content"] for m in st.session_state.HW4_messages[:-1] if m["role"] == "user"]
    query_text = f"{earlier[-1]}\n{prompt}" if earlier else prompt
    hits = retrieve(query_text)

    # ...and keep last turn's excerpts too (deduped), so "links to those"
    # has a "those". Without this the model only ever sees this turn's hits.
    seen = {h["label"] for h in hits}
    carried = [h for h in st.session_state.get("HW4_last_hits", []) if h["label"] not in seen]
    context = "\n\n".join(
        f"=== {h['label']} | {h['url']} ===\n{h['text']}" for h in hits + carried
    )
    system = SYSTEM_PROMPT + "\n\nOrganization pages:\n\n" + context
    labels = [h["label"] for h in hits]
    if carried:
        labels.append(f"+ {len(carried)} carried from last turn")

    # Memory buffer: the last BUFFER_TURNS user/assistant pairs
    buffer = st.session_state.HW4_messages[-(BUFFER_TURNS * 2):]
    payload = [{"role": "system", "content": system}] + buffer

    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        stream = client.chat.completions.create(
            model=MODEL,
            messages=payload,
            stream=True,
        )
        response = st.write_stream(stream)
        st.caption("Retrieved: " + ", ".join(labels))

    st.session_state.HW4_messages.append(
        {"role": "assistant", "content": response, "sources": labels}
    )
    st.session_state.HW4_last_hits = hits
