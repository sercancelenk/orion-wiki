### OrionWiki

OrionWiki is a lightweight, LLM‑powered tool that analyzes a Git repository and generates a rich **architecture wiki** as a single HTML page.

- **Input**: GitHub / GitLab (including on‑prem) repository URL + LLM API key  
- **Pipeline**: Clone repo → scan files → chunk text → embed → RAG‑style wiki sections → single HTML wiki  
- **Output**: Dark themed, left‑nav layout with Mermaid diagrams and downloadable HTML

This project is inspired by [`AsyncFuncAI/deepwiki-open`](https://github.com/AsyncFuncAI/deepwiki-open) but implemented as a **stateless / in‑memory MVP**.

---

### Screenshots

> Note: file names below assume you save your screenshots under a local `screenshots/` folder in the repo root.

**OrionWiki UI (Streamlit front page)**

![OrionWiki UI – repo & LLM settings sidebar](screenshots/orionwiki-ui.png)

**Generated architecture wiki (HTML output)**

![OrionWiki generated wiki – High Level Architecture page](screenshots/orionwiki-wiki.png)

---

### Features

- **Stateless / in‑memory MVP**
  - Each `Generate Wiki` request:
    - Clones the repository into a temporary directory
    - Builds embeddings + a FAISS index in memory only
    - Generates all wiki sections and returns the full HTML in the response
  - No persistent embeddings or wiki files are stored on disk (existing `backend/storage/` is only for the older stateful mode).

- **Mermaid diagram support**
  - `graph TD`, `flowchart` and `sequenceDiagram` blocks are automatically detected and rendered with Mermaid.

- **Private GitLab / GitHub support**
  - The UI exposes a `Git Access Token` field; you can provide a personal access token to clone private repositories.
  - For GitLab, URLs are automatically converted to `https://oauth2:<token>@gitlab.xxx.com/...` format.

- **Modern dark UI**
  - Left sidebar: OrionWiki logo, repo‑specific title, export buttons, and page list.
  - Main area: selected section content, code blocks, and diagrams.

---

### Requirements

- Python 3.12
- Dependencies from `requirements.txt`:
  - `fastapi`, `uvicorn[standard]`, `pydantic`, `requests`
  - `faiss-cpu`, `streamlit`, `openai`, `markdown`
- `git` binary (for `git clone`)

Currently, only **OpenAI‑compatible** LLM endpoints are used (OpenAI itself, or any proxy/OpenRouter‑style endpoint via `base_url`).

---

### Local Setup

```bash
git clone https://github.com/<your-github-username>/orionwiki.git
cd orionwiki

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

#### Run the backend

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

#### Run the UI (Streamlit)

```bash
streamlit run ui/app.py --server.port 3000 --server.address 0.0.0.0
```

Open `http://localhost:3000` in your browser.

---

### Usage

1. **Configure LLM settings**
   - In the sidebar:
     - `Provider`: `openai`
     - `Chat Model`: defaults to `gpt-4-turbo` (you can change it)
     - `Embedding Model`: defaults to `text-embedding-3-small`
     - `API Key`: your OpenAI or OpenAI‑compatible API key

2. **Repository URL**
   - In the `GitHub URL` field, provide:
     - Example GitHub repo: `https://github.com/AsyncFuncAI/deepwiki-open`
     - Or on‑prem GitLab:
       - `https://gitlab.xxx.com/group/private-repo`

3. **Token for private repos (optional)**
   - In the `Git Access Token` field:
     - GitHub PAT, or
     - GitLab personal access token (at least `read_repository` / `api` scope)

4. **Generate the wiki**
   - Click **Generate Wiki**.
   - Backend:
     - Clones the repo into a temp directory
     - Builds an in‑memory FAISS index
     - Generates wiki outline + pages
     - Returns the full HTML document
   - UI:
     - Embeds the HTML and shows the left‑nav wiki interface
     - Provides a **Download wiki HTML** button to save the same file.

> Note: In this stateless MVP, `Ask this repo` and Deep Research endpoints are disabled in the UI. They can be re‑introduced in a future stateful version.

---

### Running with Docker

A `Dockerfile` is provided at the project root.

```bash
# Build the image
docker build -t orionwiki:latest .

# Backend
docker run --rm -p 8001:8001 orionwiki:latest

# UI (separate container, same image)
docker run --rm -p 3000:3000 \
  --env API_BASE="http://host.docker.internal:8001" \
  orionwiki:latest \
  streamlit run ui/app.py --server.port=3000 --server.address=0.0.0.0
```

On Linux you may need to replace `host.docker.internal` with your host IP.

---

### Kubernetes Deployment

For deploying the stateless MVP to Kubernetes, see the detailed guide in `K8S_DEPLOYMENT.md`:

- Build & push the Docker image  
- Backend `Deployment` + `Service`  
- UI `Deployment` + `Service` (same image, different command)  
- Ingress example (`orionwiki.example.com`)  
- Notes for accessing private GitLab/GitHub from worker pods

See: `K8S_DEPLOYMENT.md`

---

### Architecture Notes & Future Work

High‑level design notes are collected in `DEPLOYMENT_NOTES.md`, covering:

- Multi‑tenant storage design (per‑user namespaces)
- Transition to a stateful mode (persistent FAISS index + wiki cache)
- Auth / profile / user management (JWT, OAuth, etc.)

Planned improvements:

- Optional **stateful mode** alongside the stateless mode (cache + RAG + Ask this repo)
- Login / profile and per‑user repo/plan management
- Support for multiple LLM providers (OpenRouter, Gemini, etc.)

---

### License

This project is currently a personal / experimental project.  
You can choose a license (e.g. MIT, Apache‑2.0) when publishing it on your own GitHub account; this README does not include a license statement by itself.
