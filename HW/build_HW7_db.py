# HW 7 · build the news vector DB once, outside the app.
#
# Run it from the repo root, with the venv on:
#     python HW/build_HW7_db.py
#
# It reads news.csv where it already lives in Blue (so no second copy goes
# into the repo), cleans it, embeds every article with text-embedding-3-small,
# and saves the Chroma DB to HW/HW7_ChromaDB/. HW7.py will only *load* that
# folder, so the app starts fast and never pays for embeddings.
# Commit the folder: .gitignore skips HW4_ChromaDB, not this one.
#
# Rerunning rebuilds the DB from scratch (about 11 embedding calls).

import os
import shutil
import time
import tomllib

import chromadb
import pandas as pd
from openai import OpenAI, PermissionDeniedError

HERE = os.path.dirname(os.path.abspath(__file__))    # .../IST-688-Homework/HW
REPO = os.path.dirname(HERE)                          # .../IST-688-Homework
CSV_PATH = os.path.expanduser("~/Blue/1.5/IST 688/Weekly/W7/HW/news.csv")
DB_PATH = os.path.join(HERE, "HW7_ChromaDB")
COLLECTION_NAME = "HW7News"
EMBEDDING_MODEL = "text-embedding-3-small"


def load_articles(path=CSV_PATH):
    # 1,290 rows → 1,082 articles. About 200 rows repeat a story (same URL,
    # or the same text under a second URL), and a few company names carry
    # stray spaces (“ TPG”). Strip and dedupe before anything is embedded,
    # or the top-10 lists the same story twice.
    df = pd.read_csv(path)
    df["company_name"] = df["company_name"].str.strip()
    df = df.drop_duplicates(subset="URL").drop_duplicates(subset="Document")
    return df.reset_index(drop=True)


def get_api_key():
    # The same key the app uses, read from the repo’s secrets file
    # (st.secrets only works inside a running Streamlit app).
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    with open(os.path.join(REPO, ".streamlit", "secrets.toml"), "rb") as f:
        return tomllib.load(f)["OPENAI_API_KEY"]


def embed_many(client, texts):
    # One call per batch. The 403 retry is HW 5’s (allowed-models lag).
    for attempt in range(6):
        try:
            response = client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
            return [item.embedding for item in response.data]
        except PermissionDeniedError:
            if attempt == 5:
                raise
            time.sleep(2)


def build(client, df):
    # Start from an empty folder every run. (Chroma’s delete_collection
    # leaves the old index files on disk, and they’d get committed.)
    shutil.rmtree(DB_PATH, ignore_errors=True)
    db = chromadb.PersistentClient(path=DB_PATH)
    collection = db.create_collection(COLLECTION_NAME)

    ids, docs, metas, texts = [], [], [], []
    for i, row in df.iterrows():
        ids.append(f"news-{i:04d}")
        docs.append(row["Document"])
        metas.append({
            "company": row["company_name"],
            "date": row["Date"][:10],
            "days_since_2000": int(row["days_since_2000"]),
            "url": row["URL"],
        })
        # The company name rides along in what gets embedded, so a search
        # for a client finds its articles even when the snippet never names it.
        texts.append(f"{row['company_name']}: {row['Document']}")

    for start in range(0, len(ids), 100):
        end = start + 100
        collection.add(
            ids=ids[start:end],
            documents=docs[start:end],
            metadatas=metas[start:end],
            embeddings=embed_many(client, texts[start:end]),
        )
        print(f"  embedded {min(end, len(ids))}/{len(ids)}")
    return collection


def test_search(client, collection, query="lawsuit or regulator investigation"):
    # One search, so you can see the DB answer before HW7.py exists.
    hits = collection.query(query_embeddings=embed_many(client, [query]), n_results=5)
    print(f"\nTest search: “{query}”")
    for meta, doc in zip(hits["metadatas"][0], hits["documents"][0]):
        print(f"  · {meta['company']} ({meta['date']}): {doc[:90]}")


if __name__ == "__main__":
    df = load_articles()
    print(
        f"{len(df)} articles from {df['company_name'].nunique()} companies "
        f"({df['Date'].min()[:10]} to {df['Date'].max()[:10]})"
    )
    client = OpenAI(api_key=get_api_key())
    collection = build(client, df)
    print(f"Saved {collection.count()} articles to {DB_PATH}")
    test_search(client, collection)
