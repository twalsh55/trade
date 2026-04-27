import os
import logging
from pathlib import Path

import streamlit as st


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def load_env_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


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
