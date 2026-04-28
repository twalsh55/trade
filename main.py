import os
import logging

import streamlit as st

from src.env_utils import load_env_file


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    load_env_file()
    logger.info("Starting market crash monitor entrypoint")
    if not st.runtime.exists():
        logger.info("Streamlit runtime not available; printing CLI hint")
        print("This is a Streamlit app. Run it with: uv run streamlit run main.py")
    else:
        logger.info("Streamlit runtime detected; rendering dashboard")
        from src.adapters.ui.streamlit_dashboard import render

        render()
