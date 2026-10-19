import os
import streamlit as st

st.set_page_config(page_title="HW Manager", page_icon=":material/school:")

hw1 = st.Page("HW/HW1.py", title="HW 1")
hw2 = st.Page("HW/HW2.py", title="HW 2")
hw3 = st.Page("HW/HW3.py", title="HW 3")
hw4 = st.Page("HW/HW4.py", title="HW 4")
hw5 = st.Page("HW/HW5.py", title="HW 5")
hw7 = st.Page("HW/HW7.py", title="HW 7", default=True)

pages = [hw1, hw2, hw3, hw4, hw5, hw7]
# The HW 7 Lab only shows up on Diva's Mac, where Blue/HW7.1.py lives;
# the deployed app never lists it.
if os.path.exists(os.path.expanduser("~/Blue/HW7.1.py")):
    pages.append(st.Page("HW/HW7_lab.py", title="HW 7 Lab"))

pg = st.navigation(pages)
pg.run()
