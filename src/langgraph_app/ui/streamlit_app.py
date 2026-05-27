"""Streamlit entry point — multi-page navigation.

Run with:
    uv run streamlit run src/langgraph_app/ui/streamlit_app.py

Pages
-----
- Chat  : main conversation UI with a sidebar listing saved threads.
- Info  : model, middleware, tool, and API reference details.
"""

from __future__ import annotations

import streamlit as st

from langgraph_app.ui.pages import chat, info


st.set_page_config(
    page_title="LangGraph Agent",
    page_icon="\U0001F47E",  # 👾
    layout="centered",
    initial_sidebar_state="expanded",
)

pg = st.navigation(
    [
        st.Page(chat.render, title="Chat", icon="\U0001F4AC", url_path="chat", default=True),
        st.Page(info.render, title="Info", icon="\U00002139\uFE0F", url_path="info"),
    ]
)

pg.run()
