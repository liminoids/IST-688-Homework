# HW 7 Lab · an experiment page that only runs on Diva's Mac.
#
# It runs the other chat's version, Blue/HW7.1.py, exactly as it is, and puts
# a vibe switch on top: the same page in three looks. HW7.1.py is never
# changed or copied - the lab reads it fresh on every run, so edits to it show
# up here right away. Nothing on this page is part of the submission.

import os
import streamlit as st

SOURCE = os.path.expanduser("~/Blue/HW7.1.py")

if not os.path.exists(SOURCE):
    st.info("The HW 7 Lab only runs on Diva\u2019s Mac, where Blue/HW7.1.py lives.")
    st.stop()

# ---------- The vibes ----------
# Each vibe is one layer of CSS over 7.1's own styling. Its rules carry one
# more id than 7.1's (":has(#hw7-vibe-...)"), so they win without touching
# 7.1. "The Brief" is 7.1 with no layer at all.
SPARKLE = """
<style>
[data-testid="stElementContainer"]:has(#hw7-vibe-sparkle) { display: none; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) {
    --hw7-ink: #4b3a53; --hw7-rose: #c2669a; --hw7-muted: #8f7b9b; --hw7-line: #efd9ec;
    --hw7-paper: #fffaff; --hw7-paper-ink: #4b3a53;
}
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 12% 16%, #ffffff 0 2px, transparent 3px),
        radial-gradient(circle at 82% 10%, #ffffff 0 1.5px, transparent 2.5px),
        radial-gradient(circle at 66% 74%, #ffffff 0 2px, transparent 3px),
        radial-gradient(circle at 28% 86%, #ffffff 0 1.5px, transparent 2.5px),
        linear-gradient(160deg, #fdeef6 0%, #f3ecff 50%, #eaf8f3 100%);
    color-scheme: light;
}
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stHeader"] { background: rgba(253,238,246,.9); }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stBottom"] { background: linear-gradient(0deg, #eef4f6 70%, rgba(238,244,246,0)); }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stSidebar"] { background: #fbf2fa; border-right: 1px solid #efd9ec; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stRadio"] label:has(input:checked) { background: #fde6f1; border-color: #f0b6d2; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stRadioOption"] > div > div:first-child { background: #ffffff; border-color: #e4bcd3; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stSlider"] [role="group"] > div > div:first-child {
    background: linear-gradient(to right, var(--hw7-rose) 0%, var(--hw7-rose) var(--hw7-slider-fill, 50%), #ecdcec var(--hw7-slider-fill, 50%), #ecdcec 100%);
}
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) .stButton > button { background: #ffffff; color: var(--hw7-ink); border-color: #ecc7dc; border-radius: 999px; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) .stButton > button:hover { background: #fff3f9; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) .stButton > button[kind="primary"] { background: #f8c9df; color: #4b3a53; border-color: #f3b3d1; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-baseweb="select"] > div,
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stSelectbox"] [role="group"] { background: #ffffff; border-color: #ecc7dc; border-radius: 999px; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [role="listbox"],
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [role="option"] { background: #ffffff; color: var(--hw7-ink); }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [role="option"]:hover,
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [role="option"][aria-selected="true"] { background: #fde6f1; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stChatMessage"] { background: rgba(255,255,255,.82); border-color: #f1dcec; border-radius: 22px; box-shadow: 0 8px 26px rgba(196,140,180,.14); }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) { background: #f6ecfc; border-color: #e3cdf3; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stChatMessage"] strong { color: #a64f80; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stChatMessageAvatarAssistant"],
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stChatMessageAvatarUser"],
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stChatMessageAvatarCustom"] { background: #fde4f0; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stChatInput"] { background: #ffffff; border-color: #ecc7dc; border-radius: 22px; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stChatInput"] textarea::placeholder { color: #b49cbc; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stExpander"] details { background: #fffafd; border-radius: 16px; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) [data-testid="stStatusWidget"] { background: #ffffff; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) .hw7-empty { background: rgba(255,255,255,.6); border-left-color: #f2b5d2; border-radius: 0 18px 18px 0; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) .hw7-masthead { border-bottom: 2px dotted #eab8d2; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) .hw7-masthead h1::after {
    content: " \\2726"; font-size: .45em; vertical-align: super; color: #e7a6c8;
    animation: hw7-twinkle 2.4s ease-in-out infinite;
}
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) .hw7-kicker::before { content: "\\2727  "; color: #e7a6c8; }
body:has(#hw7-page-marker):has(#hw7-vibe-sparkle) .hw7-source-panel { border-left-color: #f2b5d2; border-radius: 14px; }
@keyframes hw7-twinkle { 0%, 100% { opacity: .35; } 50% { opacity: 1; } }
@media (prefers-reduced-motion: reduce) {
    body:has(#hw7-vibe-sparkle) .hw7-masthead h1::after { animation: none; }
}
</style>
"""

NEWSPRINT = """
<style>
[data-testid="stElementContainer"]:has(#hw7-vibe-newsprint) { display: none; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) {
    --hw7-ink: #1f1b16; --hw7-rose: #8c1d2f; --hw7-muted: #6b6257; --hw7-line: #d6ccbb;
    --hw7-paper: #fffdf7; --hw7-paper-ink: #1f1b16;
}
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stAppViewContainer"] { background: #f4efe4; color-scheme: light; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stHeader"] { background: rgba(244,239,228,.95); }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stBottom"] { background: linear-gradient(0deg, #f4efe4 75%, rgba(244,239,228,0)); }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stSidebar"] { background: #ece5d6; border-right: 1px solid #d6ccbb; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stRadio"] label:has(input:checked) { background: #fffdf7; border-color: #1f1b16; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stRadioOption"] > div > div:first-child { background: #fffdf7; border-color: #8a8073; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stSlider"] [role="group"] > div > div:first-child {
    background: linear-gradient(to right, var(--hw7-rose) 0%, var(--hw7-rose) var(--hw7-slider-fill, 50%), #d6ccbb var(--hw7-slider-fill, 50%), #d6ccbb 100%);
}
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) .stButton > button { background: transparent; color: #1f1b16; border-color: #1f1b16; border-radius: 2px; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) .stButton > button:hover { background: #fffdf7; color: #8c1d2f; border-color: #8c1d2f; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) .stButton > button[kind="primary"] { background: #1f1b16; color: #f4efe4; border-color: #1f1b16; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) .stButton > button[kind="primary"]:hover { background: #8c1d2f; color: #fffdf7; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-baseweb="select"] > div,
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stSelectbox"] [role="group"] { background: #fffdf7; border-color: #8a8073; border-radius: 2px; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [role="listbox"],
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [role="option"] { background: #fffdf7; color: #1f1b16; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [role="option"]:hover,
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [role="option"][aria-selected="true"] { background: #ece5d6; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stChatMessage"] { background: transparent; border: 0; border-top: 1px solid #1f1b16; border-radius: 0; box-shadow: none; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) { background: #ece5d6; border: 0; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stChatMessage"] strong { color: #1f1b16; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stChatMessageAvatarAssistant"],
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stChatMessageAvatarUser"],
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stChatMessageAvatarCustom"] { background: #1f1b16; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stChatInput"] { background: #fffdf7; border-color: #1f1b16; border-radius: 2px; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stChatInput"] textarea::placeholder { color: #8a8073; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stExpander"] details { background: #fffdf7; border-radius: 2px; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) [data-testid="stStatusWidget"] { background: #fffdf7; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) .hw7-empty { background: #fffdf7; border-left-color: #8c1d2f; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) .hw7-masthead { border-bottom: 4px double #1f1b16; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) .hw7-masthead h1 { color: #1f1b16; letter-spacing: -.02em; }
body:has(#hw7-page-marker):has(#hw7-vibe-newsprint) .hw7-source-panel { border-radius: 0; border-left-color: #1f1b16; }
</style>
"""

VIBES = {"The Brief": "", "Sparkle": SPARKLE, "Newsprint": NEWSPRINT}
NAMES = list(VIBES)


def switch_vibe():
    st.session_state.HW7L_vibe = (st.session_state.get("HW7L_vibe", 0) + 1) % len(NAMES)


vibe = NAMES[st.session_state.get("HW7L_vibe", 0)]
st.sidebar.button("\u2726 Switch vibe", on_click=switch_vibe, key="HW7L_switch")
st.sidebar.caption(f"Vibe: {vibe} ({NAMES.index(vibe) + 1} of {len(NAMES)}) \u00b7 lab only")
if VIBES[vibe]:
    slug = vibe.lower()
    st.markdown(f'<div id="hw7-vibe-{slug}"></div>' + VIBES[vibe], unsafe_allow_html=True)

# ---------- Run 7.1 as if it lived at HW/HW7.py ----------
# 7.1 finds its database next to its own file, so it's told its file is
# HW/HW7.py - the folder where HW7_ChromaDB/ actually is.
with open(SOURCE, encoding="utf-8") as f:
    code = compile(f.read(), SOURCE, "exec")
exec(code, {"__name__": "__main__", "__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "HW7.py")})
