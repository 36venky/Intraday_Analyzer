import streamlit as st

st.set_page_config(
    page_title="Intraday Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 Intraday Analyzer")
st.markdown("Use the sidebar to navigate between pages.")

st.sidebar.success("Select a page above.")
