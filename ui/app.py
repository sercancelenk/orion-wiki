# ui/app.py

import streamlit as st
import streamlit.components.v1 as components
import requests

API_BASE = "http://localhost:8001"

st.set_page_config(page_title="OrionWiki", layout="wide")
st.title("OrionWiki")


def get_llm_payload():
    """
    Sidebar'dan girilen LLM konfigürasyonunu tek noktadan üretir.
    """
    return {
        "provider": st.session_state.get("provider", "openai"),
        "chat_model": st.session_state.get("chat_model", "gpt-4-turbo"),
        "embed_model": st.session_state.get("embed_model", "text-embedding-3-small"),
        "api_key": st.session_state.get("api_key", ""),
    }


# === Sidebar ===
with st.sidebar:
    st.header("Repository")
    repo_url = st.text_input(
        "GitHub URL",
        value=st.session_state.get(
            "repo_url", "https://github.com/AsyncFuncAI/deepwiki-open"
        ),
        key="repo_url",
    )

    git_token = st.text_input(
        "Git Access Token (optional, for private GitLab/GitHub)",
        type="password",
        value=st.session_state.get("git_token", ""),
        key="git_token",
    )

    st.subheader("LLM Settings")
    provider = st.selectbox(
        "Provider",
        ["openai"],
        index=0,
        key="provider",
    )

    chat_model = st.text_input(
        "Chat Model",
        value=st.session_state.get("chat_model", "gpt-4.1-mini"),
        key="chat_model",
    )
    embed_model = st.text_input(
        "Embedding Model",
        value=st.session_state.get("embed_model", "text-embedding-3-small"),
        key="embed_model",
    )

    api_key = st.text_input(
        "API Key",
        type="password",
        value=st.session_state.get("api_key", ""),
        key="api_key",
    )

    generate_btn = st.button("Generate Wiki", type="primary")


# === Generate Wiki çağrısı ===
if generate_btn:
    if not repo_url:
        st.error("Please enter a repo URL.")
    elif not api_key:
        st.error("Please enter your API key.")
    else:
        llm_payload = get_llm_payload()
        payload = {
            "repo_url": repo_url,
            "llm": llm_payload,
            # Private repo'lar için opsiyonel git access token
            "git_token": git_token or None,
        }
        with st.spinner("Generating wiki (analysis, embeddings, outline, HTML)..."):
            try:
                # Stateless / in-memory MVP: yeni endpoint kullanılıyor
                resp = requests.post(f"{API_BASE}/api/generate_ephemeral", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state["repo_id"] = data["repo_id"]
                    st.session_state["full_html"] = data.get("html", "")
                    st.success("Wiki generated.")
                else:
                    st.error(f"Error: {resp.status_code} - {resp.text}")
            except Exception as e:
                st.error(f"Request error: {e}")

repo_id = st.session_state.get("repo_id")

# === Ana HTML preview + download ===
with st.container():
    st.subheader("Wiki Preview (HTML)")

    if repo_id:
        full_html = st.session_state.get("full_html")
        if full_html:
            # iFrame benzeri HTML preview
            components.html(full_html, height=800, scrolling=True)

            st.markdown("---")
            st.subheader("Download")
            st.download_button(
                "Download wiki HTML",
                data=full_html,
                file_name=f"{repo_id}_wiki.html",
                mime="text/html",
            )
        else:
            st.info("HTML wiki is not available yet. Please try regenerating the wiki.")
    else:
        st.info("Enter a repository URL and click *Generate Wiki* to create the wiki.")