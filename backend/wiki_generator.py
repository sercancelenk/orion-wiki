# backend/wiki_generator.py

import json
import re
import html as html_lib
from pathlib import Path
from typing import List, Dict, Any, Tuple

import markdown as md
import faiss
import numpy as np

from .config import WIKI_DIR, CHUNK_SIZE, CHUNK_OVERLAP
from .repo_analyzer import build_file_tree_summary, iter_repo_files
from .text_splitter import build_documents_from_files, split_text
from .embeddings import EmbeddingClient
from .chat_client import ChatClient
from .prompts import (
    WIKI_OUTLINE_SYSTEM_PROMPT,
    WIKI_OUTLINE_USER_TEMPLATE,
    WIKI_PAGE_SYSTEM_PROMPT,
    WIKI_PAGE_USER_TEMPLATE,
)
from .models import WikiSection, WikiPage, LLMConfig
from .vector_store import FaissIndex, get_index_paths
from .deep_research import run_deep_research


def prepare_repo_index(repo_id: str, repo_path: Path, llm: LLMConfig) -> None:
    """
    Repo dosyalarını okuyup chunk'lar, embedding üretir ve FAISS index kaydeder.
    """
    files = iter_repo_files(repo_path)
    docs = build_documents_from_files(files)
    if not docs:
        raise ValueError("No documents found in repository")

    chunks: List[str] = []
    metadatas: List[Dict] = []

    for doc in docs:
        doc_chunks = split_text(doc["text"], CHUNK_SIZE, CHUNK_OVERLAP)
        for i, ch in enumerate(doc_chunks):
            chunks.append(ch)
            metadatas.append(
                {
                    "doc_id": doc["id"],
                    "chunk_id": i,
                    "path": doc["path"],
                    "text": ch[:5000],
                }
            )

    embed_client = EmbeddingClient(llm)
    embeddings = embed_client.embed_texts(chunks)
    if not embeddings:
        raise ValueError("No embeddings created for repository")

    dim = len(embeddings[0])

    index_path, meta_path = get_index_paths(repo_id)
    index = FaissIndex(dim=dim, index_path=index_path, meta_path=meta_path)
    index.add(embeddings, metadatas)
    index.save()


def build_in_memory_index(
    repo_path: Path,
    llm: LLMConfig,
) -> Tuple[faiss.IndexFlatL2, List[Dict[str, Any]]]:
    """
    Stateless / in-memory MVP için:
    - Repo dosyalarını okuyup chunk'lar
    - Embedding üretir
    - FAISS index'i sadece memory'de kurar ve metadata listesiyle birlikte döner.
    """
    files = iter_repo_files(repo_path)
    docs = build_documents_from_files(files)
    if not docs:
        raise ValueError("No documents found in repository")

    chunks: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for doc in docs:
        doc_chunks = split_text(doc["text"], CHUNK_SIZE, CHUNK_OVERLAP)
        for i, ch in enumerate(doc_chunks):
            chunks.append(ch)
            metadatas.append(
                {
                    "doc_id": doc["id"],
                    "chunk_id": i,
                    "path": doc["path"],
                    "text": ch[:5000],
                }
            )

    embed_client = EmbeddingClient(llm)
    embeddings = embed_client.embed_texts(chunks)
    if not embeddings:
        raise ValueError("No embeddings created for repository")

    dim = len(embeddings[0])
    vecs = np.array(embeddings, dtype="float32")

    index = faiss.IndexFlatL2(dim)
    index.add(vecs)

    return index, metadatas


def _ensure_high_level_architecture_section(
    sections: List[WikiSection],
) -> List[WikiSection]:
    """
    Outline'da 'High Level Architecture' isimli bir section yoksa,
    önden özel bir section ekler.
    """
    for s in sections:
        if s.id == "high-level-architecture":
            return sections
        if s.title.strip().lower() == "high level architecture":
            return sections

    special = WikiSection(
        id="high-level-architecture",
        title="High Level Architecture",
        description=(
            "High-level architecture of the repository: main components, services, "
            "and data/control flows between them."
        ),
        keywords=["architecture", "components", "services", "data flow", "overview"],
    )
    # Menüde üstte görünmesi için başa ekliyoruz
    return [special] + sections


def _parse_outline_response(raw: str) -> List[Dict[str, Any]]:
    """
    LLM'den gelen outline cevabını güvenli biçimde JSON'a parse etmeye çalışır.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    cleaned = raw.strip()

    # ```json ... ``` veya ``` ... ``` code fence'lerini temizle
    lines = cleaned.splitlines()
    if lines and lines[0].strip().startswith("```"):
        if lines[-1].strip().startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        cleaned = "\n".join(lines).strip()

    # İçerideki ilk '[' ve son ']' arasını al
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and start < end:
        candidate = cleaned[start : end + 1]
    else:
        candidate = cleaned

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        snippet = raw.strip().replace("\n", "\\n")[:300]
        raise ValueError(
            f"Failed to parse wiki outline JSON. "
            f"JSONDecodeError: {e}. Raw response starts with: {snippet!r}"
        ) from e


def generate_wiki_outline(
    repo_id: str,
    repo_path: Path,
    llm: LLMConfig,
) -> List[WikiSection]:
    """
    Repo dosya ağacını kullanarak LLM'den wiki outline (section listesi) üretir.
    """
    file_tree = build_file_tree_summary(repo_path)
    repo_name = repo_path.name

    user_prompt = WIKI_OUTLINE_USER_TEMPLATE.format(
        repo_name=repo_name,
        description="",
        file_tree=file_tree,
    )

    chat_client = ChatClient(llm)

    messages = [
        {"role": "system", "content": WIKI_OUTLINE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    raw = chat_client.chat(messages)

    data = _parse_outline_response(raw)
    sections: List[WikiSection] = [WikiSection(**item) for item in data]
    sections = _ensure_high_level_architecture_section(sections)

    cache_path = WIKI_DIR / f"{repo_id}_outline.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps([s.model_dump() for s in sections], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return sections


def generate_wiki_outline_ephemeral(
    repo_path: Path,
    llm: LLMConfig,
) -> List[WikiSection]:
    """
    Stateless / in-memory kullanım için outline üretir.
    Disk'e herhangi bir cache yazmaz.
    """
    file_tree = build_file_tree_summary(repo_path)
    repo_name = repo_path.name

    user_prompt = WIKI_OUTLINE_USER_TEMPLATE.format(
        repo_name=repo_name,
        description="",
        file_tree=file_tree,
    )

    chat_client = ChatClient(llm)

    messages = [
        {"role": "system", "content": WIKI_OUTLINE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    raw = chat_client.chat(messages)

    data = _parse_outline_response(raw)
    sections: List[WikiSection] = [WikiSection(**item) for item in data]
    sections = _ensure_high_level_architecture_section(sections)

    return sections


def generate_wiki_page(
    repo_id: str,
    section: WikiSection,
    llm: LLMConfig,
    index: FaissIndex,
) -> WikiPage:
    """
    Tek bir wiki section için markdown sayfası üretir.
    """
    embed_client = EmbeddingClient(llm)
    chat_client = ChatClient(llm)

    query = " ".join([section.title] + section.keywords)
    q_emb = embed_client.embed_texts([query])[0]
    neighbors = index.search(q_emb, top_k=12)

    context_blocks = []
    for n in neighbors:
        context_blocks.append(f"File: {n['path']}\n\n{n['text']}\n---")

    contexts = "\n\n".join(context_blocks)

    user_prompt = WIKI_PAGE_USER_TEMPLATE.format(
        section_json=json.dumps(section.model_dump(), ensure_ascii=False),
        contexts=contexts,
    )

    messages = [
        {"role": "system", "content": WIKI_PAGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    markdown = chat_client.chat(messages)

    page = WikiPage(section=section, markdown=markdown)
    cache_path = WIKI_DIR / f"{repo_id}_{section.id}.md"
    cache_path.write_text(markdown, encoding="utf-8")
    return page


def generate_wiki_page_ephemeral(
    section: WikiSection,
    llm: LLMConfig,
    index: faiss.IndexFlatL2,
    metadatas: List[Dict[str, Any]],
) -> WikiPage:
    """
    Stateless / in-memory kullanım için tek bir wiki section üretir.
    Disk'e markdown yazmaz.
    """
    embed_client = EmbeddingClient(llm)
    chat_client = ChatClient(llm)

    query = " ".join([section.title] + section.keywords)
    q_emb = embed_client.embed_texts([query])[0]

    q = np.array([q_emb], dtype="float32")
    distances, indices = index.search(q, top_k=12)

    neighbors: List[Dict[str, Any]] = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0 or idx >= len(metadatas):
            continue
        item = dict(metadatas[idx])
        item["score"] = float(dist)
        neighbors.append(item)

    context_blocks = []
    for n in neighbors:
        context_blocks.append(f"File: {n['path']}\n\n{n['text']}\n---")

    contexts = "\n\n".join(context_blocks)

    user_prompt = WIKI_PAGE_USER_TEMPLATE.format(
        section_json=json.dumps(section.model_dump(), ensure_ascii=False),
        contexts=contexts,
    )

    messages = [
        {"role": "system", "content": WIKI_PAGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    markdown = chat_client.chat(messages)

    page = WikiPage(section=section, markdown=markdown)
    return page


def _generate_high_level_architecture_markdown(
    repo_id: str,
    llm: LLMConfig,
) -> str:
    """
    Deep research benzeri çok turlu bir süreçle, repo'nun high-level mimarisini
    çıkaran özel bir içerik üretir.
    """
    question = (
        "Provide a high-level architecture overview of this repository. Describe "
        "the main components, services, data flows and how they interact. "
        "If helpful, include a single Mermaid diagram (flow chart or sequence "
        "diagram) using the allowed templates to visualise the overall architecture."
    )
    final_answer, _ = run_deep_research(
        repo_id=repo_id,
        question=question,
        llm=llm,
        max_iterations=3,
    )
    return final_answer


def _nav_dot_class(section: WikiSection) -> str:
    """
    DeepWiki'deki gibi farklı page tipleri için farklı renkler.
    Basit bir heuristic: title'a göre renk seçiyoruz.
    """
    title = (section.title or "").lower()
    if "architecture" in title or "design" in title:
        return "dw-dot-orange"
    if "api" in title or "endpoint" in title:
        return "dw-dot-blue"
    return "dw-dot-green"


def _convert_mermaid_code_blocks(html_text: str) -> str:
    """
    Markdown'dan gelen <pre><code> bloklarını tarar.
    İçeriği Mermaid'e benziyorsa (graph TD, graph LR, sequenceDiagram, flowchart vs.)
    bu blokları:

        <div class="dw-mermaid-wrapper"><div class="mermaid">...</div></div>

    şeklinde değiştirir.

    Ayrıca code içindeki HTML entity'lerini (örn. &gt;) unescape eder.
    """
    pattern = re.compile(r"<pre><code[^>]*>(.*?)</code></pre>", re.DOTALL)

    def repl(match: re.Match) -> str:
        raw_code = match.group(1)
        # HTML entity'lerini çözüyoruz
        decoded = html_lib.unescape(raw_code.strip())
        if not decoded.strip():
            return match.group(0)

        first_line = decoded.lstrip().splitlines()[0].strip()

        # Yalnızca temel Mermaid diyagram tiplerini (graph/flowchart/sequenceDiagram)
        # otomatik olarak mermaid wrapper'ına alıyoruz. İçeriğin kendisini
        # Mermaid'in parser'ına bırakıyoruz; hatalıysa kendi hata mesajını
        # gösterecek.
        if (
            first_line.startswith("graph ")
            or first_line.startswith("flowchart ")
            or first_line == "sequenceDiagram"
        ):
            return (
                '<div class="dw-mermaid-wrapper">'
                '<div class="mermaid">\n'
                f"{decoded}\n"
                "</div></div>"
            )
        return match.group(0)

    return pattern.sub(repl, html_text)


def build_full_wiki_html(
    repo_id: str,
    sections: List[WikiSection],
    llm: LLMConfig,
) -> str:
    """
    Tüm section'lar için wiki sayfalarını üretir (gerekirse) ve
    DeepWiki tarzı bir layout ile tek bir HTML dosyası halinde birleştirir.

    Sol menüde "Pages" listesi vardır, her satıra tıklayınca sadece o section
    sağ tarafta görünür (tek sayfa görünümü).
    Mermaid diagram blokları otomatik olarak görsel olarak render edilir.
    """
    index_path, meta_path = get_index_paths(repo_id)
    if not index_path.exists() or not meta_path.exists():
        raise ValueError("Index not found for repo while building full HTML")

    index = FaissIndex.load(index_path, meta_path)

    pages_md: List[str] = []
    for section in sections:
        page_path = WIKI_DIR / f"{repo_id}_{section.id}.md"
        if page_path.exists():
            markdown_text = page_path.read_text(encoding="utf-8")
        else:
            # High Level Architecture için özel, deep-research tabanlı içerik
            if section.id == "high-level-architecture":
                markdown_text = _generate_high_level_architecture_markdown(
                    repo_id, llm
                )
                page = WikiPage(section=section, markdown=markdown_text)
                page_path.write_text(markdown_text, encoding="utf-8")
            else:
                page = generate_wiki_page(repo_id, section, llm, index)
                markdown_text = page.markdown
        pages_md.append(markdown_text)

    if not pages_md:
        raise ValueError("No wiki pages generated to build HTML")

    full_html = _render_full_wiki_html(repo_id, sections, pages_md)

    # Stateful sürüm için HTML'i diske yazıyoruz
    html_path = WIKI_DIR / f"{repo_id}_wiki.html"
    html_path.write_text(full_html, encoding="utf-8")

    return full_html


def _render_full_wiki_html(
    repo_id: str,
    sections: List[WikiSection],
    pages_md: List[str],
) -> str:
    """
    Verilen section listesi ve markdown içeriklerinden tek bir HTML wiki çıktısı üretir.
    Bu fonksiyon disk erişimi yapmaz; sadece HTML string döner.
    """
    # Header tarafında kullanmak için proje adı
    if "_" in repo_id:
        owner, repo_name = repo_id.split("_", 1)
    else:
        repo_name = repo_id
    project_title = f"{repo_name} Wiki"
    project_desc = "powered by ai"

    # Her section için markdown'u ayrı HTML'e çevirip Mermaid bloklarını dönüştürüyoruz
    section_html_blocks: List[str] = []
    for section, markdown_text in zip(sections, pages_md):
        section_body = md.markdown(
            markdown_text,
            extensions=["fenced_code", "tables"],
        )
        section_body = _convert_mermaid_code_blocks(section_body)
        section_html = f"""
<section id="section-{section.id}" class="dw-section">
  <div class="dw-section-inner">
    {section_body}
  </div>
</section>
"""
        section_html_blocks.append(section_html)

    body_html = "\n".join(section_html_blocks)

    # Sol taraftaki Pages listesi
    nav_items = []
    for section in sections:
        dot_class = _nav_dot_class(section)
        nav_items.append(
            f"""
<button class="dw-nav-item" data-target="section-{section.id}" onclick="showSection('section-{section.id}')">
  <span class="dw-nav-dot {dot_class}"></span>
  <span class="dw-nav-label">{section.title}</span>
</button>
"""
        )
    nav_items_html = "\n".join(nav_items)

    sidebar_html = f"""
<aside class="dw-sidebar">
  <div class="dw-sidebar-header">
    <div class="dw-brand-row">
      <div class="dw-logo-icon">
        <span class="dw-logo-letter">O</span>
      </div>
      <div class="dw-brand-text">
        <div class="dw-brand-title">{project_title}</div>
        <div class="dw-brand-subtitle">{project_desc}</div>
      </div>
    </div>
    <div class="dw-sidebar-repo">{repo_id}</div>
  </div>
  <div class="dw-sidebar-export">
    <div class="dw-export-title">Export Wiki</div>
    <div class="dw-export-actions">
      <div class="dw-export-btn dw-export-primary">Export as HTML</div>
      <div class="dw-export-btn dw-export-secondary">Export as JSON</div>
    </div>
  </div>
  <div class="dw-sidebar-pages">
    <div class="dw-pages-title">Pages</div>
    <div class="dw-pages-list">
      {nav_items_html}
    </div>
  </div>
</aside>
"""

    layout_html = f"""
<div class="dw-root">
  <div class="dw-layout">
    {sidebar_html}
    <main class="dw-main">
      {body_html}
    </main>
  </div>
</div>
"""

    css = """
:root {
  --dw-bg: #020617;
  --dw-bg-elevated: #020617;
  --dw-bg-main: #020617;
  --dw-sidebar-bg: #020617;
  --dw-border-subtle: #1f2937;
  --dw-border-strong: #334155;
  --dw-accent: #8b5cf6;
  --dw-accent-soft: rgba(139,92,246,0.18);
  --dw-text: #e5e7eb;
  --dw-text-muted: #9ca3af;
  --dw-radius-md: 12px;
  --dw-radius-lg: 16px;
  --dw-radius-xl: 20px;
  --dw-shadow-soft: 0 22px 45px rgba(15,23,42,0.85);
  --dw-font-sans: system-ui,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
  --dw-font-mono: ui-monospace,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 24px 24px 32px 24px;
  background: radial-gradient(circle at top left, #020617 0, #020617 55%, #020617 100%);
  color: var(--dw-text);
  font-family: var(--dw-font-sans);
  -webkit-font-smoothing: antialiased;
}

.dw-root {
  max-width: 1440px;
  margin: 0 auto;
}

.dw-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 18px;
}

/* Sidebar */

.dw-sidebar {
  background: linear-gradient(145deg, #020617, #020617);
  border-radius: var(--dw-radius-xl);
  border: 1px solid rgba(30,64,175,0.55);
  box-shadow: var(--dw-shadow-soft);
  padding: 16px 14px 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dw-sidebar-header {
  padding: 10px 10px 12px 10px;
  border-radius: var(--dw-radius-lg);
  background: radial-gradient(circle at top left, rgba(148,163,184,0.16), transparent 55%), rgba(15,23,42,0.96);
  border: 1px solid rgba(148,163,184,0.4);
}

.dw-brand-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dw-logo-icon {
  width: 32px;
  height: 32px;
  border-radius: 12px;
  background: radial-gradient(circle at 30% 20%, #e5e7eb 0, #c4b5fd 22%, #8b5cf6 55%, #4c1d95 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(15,23,42,0.8);
}

.dw-logo-letter {
  font-size: 18px;
  font-weight: 700;
  color: #f9fafb;
}

.dw-brand-text {
  display: flex;
  flex-direction: column;
}

.dw-brand-title {
  font-size: 15px;
  font-weight: 600;
  color: #f9fafb;
}

.dw-brand-subtitle {
  font-size: 11px;
  color: var(--dw-text-muted);
}

.dw-sidebar-repo {
  margin-top: 8px;
  font-size: 11px;
  color: var(--dw-text-muted);
  opacity: 0.9;
}

/* Export */

.dw-sidebar-export {
  padding: 10px 10px 12px 10px;
  border-radius: var(--dw-radius-lg);
  background: rgba(15,23,42,0.98);
  border: 1px solid rgba(51,65,85,0.9);
}

.dw-export-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--dw-text-muted);
  margin-bottom: 8px;
}

.dw-export-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dw-export-btn {
  font-size: 12px;
  border-radius: 999px;
  padding: 7px 10px;
  text-align: center;
  cursor: default;
  user-select: none;
}

.dw-export-primary {
  background: linear-gradient(135deg, #a855f7, #ec4899);
  color: white;
  font-weight: 500;
}

.dw-export-secondary {
  background: rgba(15,23,42,1);
  border: 1px solid rgba(55,65,81,0.9);
  color: var(--dw-text);
}

/* Pages */

.dw-sidebar-pages {
  padding: 10px 10px 12px 10px;
  border-radius: var(--dw-radius-lg);
  background: rgba(15,23,42,0.98);
  border: 1px solid rgba(55,65,81,0.9);
  flex: 1;
  display: flex;
  flex-direction: column;
}

.dw-pages-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--dw-text-muted);
  margin-bottom: 8px;
}

.dw-pages-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: calc(100vh - 260px);
  overflow-y: auto;
  padding-right: 4px;
}

.dw-nav-item {
  width: 100%;
  border-radius: 999px;
  border: none;
  padding: 7px 10px;
  background: transparent;
  color: #e5e7eb;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s ease-out;
}

.dw-nav-item:hover {
  background: rgba(148,163,184,0.18);
  transform: translateX(1px);
}

.dw-nav-item:active {
  transform: translateX(0);
}

.dw-nav-item-active {
  background: linear-gradient(135deg, #a855f7, #ec4899);
  color: #f9fafb;
  box-shadow: 0 0 0 1px rgba(15,23,42,0.9);
}

.dw-nav-item-active .dw-nav-dot {
  box-shadow: 0 0 0 2px rgba(15,23,42,0.85);
}

.dw-nav-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  flex-shrink: 0;
}

.dw-dot-green {
  background: #22c55e;
}

.dw-dot-orange {
  background: #f97316;
}

.dw-dot-blue {
  background: #38bdf8;
}

.dw-nav-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Main */

.dw-main {
  background: radial-gradient(circle at top left, rgba(148,163,184,0.12), transparent 55%), rgba(15,23,42,0.98);
  border-radius: var(--dw-radius-xl);
  border: 1px solid rgba(30,64,175,0.6);
  box-shadow: var(--dw-shadow-soft);
  padding: 20px 24px 24px 24px;
  max-height: calc(100vh - 48px);
  overflow-y: auto;
}

/* Section görünürlüğü */

.dw-section {
  display: none;
}

.dw-section.dw-section-active {
  display: block;
}

.dw-section-inner {
  padding-bottom: 4px;
}

/* Mermaid wrapper */

.dw-mermaid-wrapper {
  margin: 14px 0 18px 0;
  padding: 14px 16px;
  border-radius: 16px;
  background: #020617;
  border: 1px solid #1f2937;
  box-shadow: 0 14px 40px rgba(15,23,42,0.9);
  overflow: auto;
}

/* Typography */

.dw-main h1,
.dw-main h2,
.dw-main h3,
.dw-main h4 {
  color: #f9fafb;
}

.dw-main h1 {
  font-size: 24px;
  margin-top: 0;
  margin-bottom: 12px;
}

.dw-main h2 {
  font-size: 18px;
  margin-top: 20px;
  margin-bottom: 8px;
}

.dw-main h3 {
  font-size: 15px;
  margin-top: 16px;
  margin-bottom: 6px;
}

.dw-main p {
  font-size: 13px;
  line-height: 1.6;
  margin: 4px 0 8px 0;
  color: var(--dw-text);
}

.dw-main ul,
.dw-main ol {
  padding-left: 20px;
  margin: 6px 0 10px 0;
}

.dw-main li {
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 4px;
}

/* Code blocks */

.dw-main pre {
  background: #020617;
  border-radius: 10px;
  border: 1px solid #1f2937;
  padding: 10px 12px;
  overflow-x: auto;
  margin: 10px 0 14px 0;
}

.dw-main code {
  font-family: var(--dw-font-mono);
  font-size: 12px;
}

.dw-main p code,
.dw-main li code {
  padding: 2px 4px;
  border-radius: 4px;
  background: rgba(15,23,42,0.95);
  border: 1px solid rgba(55,65,81,0.9);
}

/* Tables */

.dw-main table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0 16px 0;
  font-size: 12px;
}

.dw-main th,
.dw-main td {
  border: 1px solid rgba(55,65,81,0.8);
  padding: 6px 8px;
}

.dw-main th {
  background: rgba(15,23,42,0.95);
  font-weight: 600;
}

/* Links */

.dw-main a {
  color: #38bdf8;
  text-decoration: none;
}

.dw-main a:hover {
  text-decoration: underline;
}

/* HR */

.dw-main hr {
  border: none;
  border-top: 1px dashed rgba(55,65,81,0.9);
  margin: 16px 0;
}

/* Responsive */

@media (max-width: 900px) {
  body {
    padding: 16px;
  }

  .dw-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .dw-sidebar {
    order: 0;
  }

  .dw-main {
    order: 1;
    max-height: none;
  }
}
"""

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{repo_id} - OrionWiki</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
{css}
  </style>
  <script src="https://unpkg.com/mermaid@10/dist/mermaid.min.js"></script>
</head>
<body>
{layout_html}
<script>
function showSection(id) {{
  // Section görünürlüğü
  var sections = document.querySelectorAll('.dw-section');
  sections.forEach(function(sec) {{
    if (sec.id === id) {{
      sec.classList.add('dw-section-active');
    }} else {{
      sec.classList.remove('dw-section-active');
    }}
  }});

  // Sidebar aktif state
  var items = document.querySelectorAll('.dw-nav-item');
  items.forEach(function(item) {{
    if (item.getAttribute('data-target') === id) {{
      item.classList.add('dw-nav-item-active');
    }} else {{
      item.classList.remove('dw-nav-item-active');
    }}
  }});
}}

document.addEventListener('DOMContentLoaded', function() {{
  var firstSection = document.querySelector('.dw-section');
  if (firstSection) {{
    showSection(firstSection.id);
  }}
  if (window.mermaid) {{
    mermaid.initialize({{ startOnLoad: true, theme: "dark" }});
  }}
}});
</script>
</body>
</html>
"""

    return full_html


def build_full_wiki_html_ephemeral(
    repo_id: str,
    sections: List[WikiSection],
    pages_md: List[str],
) -> str:
    """
    Stateless / in-memory kullanım için HTML wiki çıktısı üretir.
    Disk'e hiçbir şey yazmaz.
    """
    return _render_full_wiki_html(repo_id, sections, pages_md)