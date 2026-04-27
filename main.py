import streamlit as st


if __name__ == "__main__":
    if not st.runtime.exists():
        print("This is a Streamlit app. Run it with: uv run streamlit run main.py")
    else:
        from src.adapters.ui.streamlit_dashboard import render

        render()
