import streamlit as st
from openai import OpenAI
from anthropic import Anthropic
import requests
from bs4 import BeautifulSoup

def read_url_content(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.get_text()
    except requests.RequestException as e:
        print(f"Error reading {url}: {e}")
        return None

st.title("HW 2 - URL Summarizer")

# Sidebar: summary type options
summary_type = st.sidebar.radio(
    "Choose a summary type:",
    (
        "Summarize the document in 100 words",
        "Summarize the document in 2 connecting paragraphs",
        "Summarize the document in 5 bullet points",
    ),
)

# Sidebar: LLM provider
provider = st.sidebar.selectbox("LLM provider:", ("OpenAI", "Claude"))

# Sidebar: model choice
use_advanced = st.sidebar.checkbox("Use advanced model")
if provider == "OpenAI":
    if use_advanced:
        model = st.sidebar.selectbox("Advanced model:", ("gpt-5.4", "o3"))
    else:
        model = "gpt-5-nano"
else:
    if use_advanced:
        model = st.sidebar.selectbox("Advanced model:", ("claude-fable-5-1", "claude-opus-5", "claude-sonnet-5"))
    else:
        model = "claude-haiku-4-5-20251001"

# Sidebar: output language
language = st.sidebar.selectbox(
    "Output language:",
    ("English", "French", "Spanish", "German"),
)

# Check that the key for the selected provider exists and looks right
key_name = "OPENAI_API_KEY" if provider == "OpenAI" else "ANTHROPIC_API_KEY"
key_prefix = "sk-" if provider == "OpenAI" else "sk-ant-"
api_key = st.secrets.get(key_name)
if not api_key or not api_key.startswith(key_prefix):
    st.error(f"No valid {key_name} found in secrets.")
    st.stop()

url = st.text_input("Enter a URL to summarize:")

if url:
    document = read_url_content(url)
    if document is None:
        st.error("Could not read that URL.")
        st.stop()

    prompt = f"Here's a document: {document} \n\n---\n\n {summary_type}. Write the summary in {language}."

    st.caption(f"Using {provider} — {model}")

    try:
        if provider == "OpenAI":
            client = OpenAI(api_key=api_key)
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            st.write_stream(stream)
        else:
            client = Anthropic(api_key=api_key)
            def claude_stream():
                with client.messages.stream(
                    model=model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                ) as s:
                    for text in s.text_stream:
                        yield text
            st.write_stream(claude_stream())
    except Exception as e:
        st.error(f"{provider} request failed — check that your API key is valid. ({e})")
