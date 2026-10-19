# HW 7 back-door test: runs the real app headlessly on both models and prints
# what the write-up needs. From the repo root:  python HW/backdoor_test.py
import os
import re
import tomllib

import chromadb
from streamlit.testing.v1 import AppTest

HERE = os.path.dirname(os.path.abspath(__file__))
QUESTION = "Find the most interesting news"
MODELS = ["gpt-5-mini \u00b7 lower cost", "gpt-5.4 \u00b7 higher cost"]
YES, NO = "\u2713", "\u2717"
with open(os.path.join(os.path.dirname(HERE), ".streamlit", "secrets.toml"), "rb") as f:
    KEY = tomllib.load(f)["OPENAI_API_KEY"]

# The traps from the initial findings, found by rule in the saved records.
got = chromadb.PersistentClient(path=os.path.join(HERE, "HW7_ChromaDB")).get_collection("HW7News").get(
    include=["documents", "metadatas"])
RECS = {i: (m["company"], d) for i, d, m in zip(got["ids"], got["documents"], got["metadatas"])}
ZELLE = {i for i, (c, d) in RECS.items() if c == "JPMorgan Chase" and "Zelle" in d}
PLAINTIFF = {}
for i, (c, d) in RECS.items():
    if re.search(r"Investors Have Opportunity|Class Action|Securities Fraud|Shareholder Alert|Investors Who Lost", d, re.I):
        PLAINTIFF.setdefault(c, set()).add(i)
MISFILED = {i for i, (c, d) in RECS.items()
            if (c == "NEC" and "Baby Formula" in d) or (c == "Cisco" and re.search(r"Cisco.s gets", d))}
MARKET = {i for i, (c, d) in RECS.items() if re.search(r"Market Size|CAGR", d, re.I)}

picks = {}
for label in MODELS:
    print(f"\nRunning {label} (a minute or two)\u2026", flush=True)
    at = AppTest.from_file("HW7.py", default_timeout=600)
    at.secrets["OPENAI_API_KEY"] = KEY
    at.run()
    at.sidebar.radio[0].set_value(label).run()
    at.chat_input[0].set_value(QUESTION).run()
    if at.exception:
        print("  The app raised an error:", at.exception)
        continue
    msg = at.session_state["HW7_messages"][-1]
    cited = list(dict.fromkeys(re.findall(r"news-\d{4}", msg["content"])))
    picks[label] = cited
    checks = {
        "Zelle story listed once": len(ZELLE & set(cited)) <= 1,
        "plaintiff notices once per company": all(len(ids & set(cited)) <= 1 for ids in PLAINTIFF.values()),
        "misfiled NEC and Cisco\u2019s skipped": not (MISFILED & set(cited)),
        "no market-size reports": not (MARKET & set(cited)),
        "every cited article is real": all(i in RECS for i in cited),
    }
    print(f"=== {msg['model']} \u00b7 {msg.get('lens', 'Exposure')} lens ===")
    print(f"seconds: {msg['seconds']:.1f} | tokens in / out: {msg['tokens_in']:,} / {msg['tokens_out']:,}")
    print("steps:", " \u00b7 ".join(msg["steps"]) or "none")
    print("stories:")
    for n, i in enumerate(cited, 1):
        company, doc = RECS.get(i, ("?", "?"))
        print(f"  {n:2d}. {company} \u2014 {doc.split(' Description:')[0][:90]}")
    print("traps:", " | ".join(f"{name} {YES if ok else NO}" for name, ok in checks.items()),
          f"({sum(checks.values())}/{len(checks)})")

if len(picks) == 2:
    a, b = picks.values()
    print(f"\nStories both models picked: {len(set(a) & set(b))} (of {len(a)} and {len(b)})")
