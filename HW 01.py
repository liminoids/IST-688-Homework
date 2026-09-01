import streamlit as st
from openai import OpenAI
import fitz


def read_pdf(uploaded_file):
    pdf_doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    text = ""
    for page in pdf_doc:
        text += page.get_text()
    return text


st.title("MY Document question answering")

openai_api_key = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=openai_api_key)

uploaded_file = st.file_uploader(
    "Upload a document (.txt or .pdf)", type=("txt", "pdf")
)

question = st.text_area(
    "Now ask a question about the document!",
    placeholder="Is this course hard?",
    disabled=not uploaded_file,
)

model = st.selectbox(
    "Model",
    ("gpt-3.5-turbo", "gpt-4.1", "gpt-5-chat-latest", "gpt-5-nano"),
)

if uploaded_file and question:
    file_extension = uploaded_file.name.split('.')[-1]
    if file_extension == 'txt':
        document = uploaded_file.read().decode()
    elif file_extension == 'pdf':
        document = read_pdf(uploaded_file)
    else:
        st.error("Unsupported file type.")
        st.stop()

    messages = [
        {
            "role": "user",
            "content": f"Here's a document: {document} \n\n---\n\n {question}",
        }
    ]

    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
    )

    st.write_stream(stream)
