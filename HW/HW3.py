import streamlit as st
from openai import OpenAI
from anthropic import Anthropic
import requests
from bs4 import BeautifulSoup

# --- Reused from HW2 ---
def read_url_content(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.get_text()
    except requests.RequestException as e:
        print(f"Error reading {url}: {e}")
        return None

# Fetch each URL once and keep the text in session_state, so we don't
# re-download the page every time a message is sent.
def fetch(url):
    cache = st.session_state.setdefault("url_cache", {})
    if url not in cache:
        text = read_url_content(url)
        if text is None:
            return None
        cache[url] = text
    return cache[url]


st.title("HW 3 - Streaming URL Chatbot")

st.write(
    "This chatbot answers questions about up to two web pages. Paste one or two URLs "
    "in the sidebar and pick a model (OpenAI or Anthropic, each at its current top model). "
    "The text of each page is loaded into a **system prompt** that is sent with every "
    "message and is never dropped, so the documents are always in front of the model. "
    "**Conversation memory is a buffer of 6 messages:** the bot remembers your last 3 "
    "exchanges (3 questions and 3 answers) and sends them along with your new question. "
    "Anything older falls out of the buffer, but the documents stay. The bot is told to "
    "answer from the documents first and to say so when it is drawing on general "
    "knowledge instead."
)

# Sidebar: up to two URLs
st.sidebar.header("Documents")
url1 = st.sidebar.text_input("URL 1")
url2 = st.sidebar.text_input("URL 2 (optional)")

# Sidebar: model choice — two vendors, their premium model
MODELS = {
    "OpenAI - gpt-6-astra": ("OpenAI", "gpt-6-astra"),
    "Anthropic - claude-fable-5-1": ("Claude", "claude-fable-5-1"),
}
st.sidebar.header("Model")
choice = st.sidebar.selectbox("LLM:", list(MODELS))
provider, model = MODELS[choice]

# Sidebar: reset the chat (useful for running the evaluation scenarios)
if st.sidebar.button("Clear conversation"):
    st.session_state.messages = []

# Check that the key for the selected provider exists and looks right
key_name = "OPENAI_API_KEY" if provider == "OpenAI" else "ANTHROPIC_API_KEY"
key_prefix = "sk-" if provider == "OpenAI" else "sk-ant-"
api_key = st.secrets.get(key_name)
if not api_key or not api_key.startswith(key_prefix):
    st.error(f"No valid {key_name} found in secrets.")
    st.stop()

# Build the system prompt from whichever URLs were given
docs = []
for label, url in (("Document 1", url1), ("Document 2", url2)):
    if url:
        text = fetch(url)
        if text is None:
            st.sidebar.error(f"Could not read {label}.")
        else:
            st.sidebar.caption(f"{label}: {len(text):,} characters loaded")
            docs.append(f"### {label} ({url})\n{text}")

if not docs:
    st.info("Add at least one URL in the sidebar to start chatting.")
    st.stop()

SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions about the document(s) below. "
    "Base your answers on the documents. If the documents do not contain the answer, "
    "say so clearly before adding anything from your general knowledge.\n\n"
    + "\n\n".join(docs)
)

# Conversation buffer: how many past messages to send (3 user + 3 assistant)
BUFFER_MESSAGES = 6

if "messages" not in st.session_state:
    st.session_state.messages = []

# Show the conversation so far
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask about the document(s)"):
    # Memory = the last 3 exchanges from before this question
    buffer = st.session_state.messages[-BUFFER_MESSAGES:]

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # What the model sees: system prompt (always) + buffer + the new question
    history = buffer + [{"role": "user", "content": prompt}]

    with st.chat_message("assistant"):
        try:
            if provider == "OpenAI":
                client = OpenAI(api_key=api_key)
                stream = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
                    stream=True,
                )
                response = st.write_stream(stream)
            else:
                client = Anthropic(api_key=api_key)
                def claude_stream():
                    with client.messages.stream(
                        model=model,
                        max_tokens=2048,
                        system=SYSTEM_PROMPT,
                        messages=history,
                    ) as s:
                        for text in s.text_stream:
                            yield text
                response = st.write_stream(claude_stream())
        except Exception as e:
            st.error(f"{provider} request failed — check that your API key is valid. ({e})")
            st.session_state.messages.pop()  # drop the unanswered question so history stays paired
            st.stop()

    st.session_state.messages.append({"role": "assistant", "content": response})
