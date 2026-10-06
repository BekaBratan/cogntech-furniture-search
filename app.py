"""Application navigation: room design is the default landing page."""
import streamlit as st

page = st.navigation([
    st.Page("pages/1_Room_design.py",title="Бөлме дизайны",default=True),
    st.Page("views/product_search.py",title="Тауар іздеу",url_path="Search"),
])
page.run()

