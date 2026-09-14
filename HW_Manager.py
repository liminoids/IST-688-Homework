import streamlit as st

st.set_page_config(page_title="HW Manager")

hw1 = st.Page("HW/HW1.py", title="HW 1")
hw2 = st.Page("HW/HW2.py", title="HW 2")
hw3 = st.Page("HW/HW3.py", title="HW 3", default=True)

pg = st.navigation([hw1, hw2, hw3])
pg.run()
