# backend/main.py

from pathlib import Path
import json
import logging
import shutil

from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    GenerateWikiRequest,
    GenerateWikiResponse,
    GenerateWikiEphemeralResponse,
    GetWikiPageRequest,
    GetWikiPageResponse,
    AskRequest,
    AskResponse,
    WikiSection,
    WikiPage,
    DeepResearchRequest,
    DeepResearchResponse,
    DeepResearchIteration,
)
from .repo_analyzer import clone_or_update_repo, clone_repo_temp, normalize_repo_id
from .wiki_generator import (
    prepare_repo_index,
    generate_wiki_outline,
    generate_wiki_page,
    build_full_wiki_html,
    build_in_memory_index,
    generate_wiki_outline_ephemeral,
    generate_wiki_page_ephemeral,
    build_full_wiki_html_ephemeral,
)
from .rag_qa import ask_repo
from .config import WIKI_DIR
from .vector_store import FaissIndex, get_index_paths
from .deep_research import run_deep_research

# Logging
logger = logging.getLogger("deepwiki")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

app = FastAPI(title="OrionWiki API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # demo için açık; üretimde daraltılmalı
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/generate", response_model=GenerateWikiResponse)
def generate_wiki(req: GenerateWikiRequest, request: Request):
    """
    Repo'yu klonlar / günceller, FAISS index oluşturur,
    seçilen LLM ayarlarıyla wiki outline üretir ve
    TÜM wiki sayfalarından tek bir HTML çıktı oluşturur.

    Ağır işlemler (embedding, outline, wiki page üretimi) sadece burada yapılır.
    """
    logger.info("POST /api/generate repo_url=%s client=%s", req.repo_url, request.client)
    try:
        repo_path = clone_or_update_repo(req.repo_url, git_token=req.git_token)
        repo_id = normalize_repo_id(req.repo_url)

        # Embedding + FAISS index
        prepare_repo_index(repo_id, repo_path, req.llm)

        # Outline
        sections = generate_wiki_outline(repo_id, repo_path, req.llm)

        # Full HTML wiki (tek sefer)
        build_full_wiki_html(repo_id, sections, req.llm)

        logger.info("Wiki generated successfully for repo_id=%s", repo_id)
        return GenerateWikiResponse(
            repo_id=repo_id,
            sections=sections,
        )
    except Exception as e:
        logger.exception("Error in /api/generate for repo_url=%s", req.repo_url)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate_ephemeral", response_model=GenerateWikiEphemeralResponse)
def generate_wiki_ephemeral(req: GenerateWikiRequest, request: Request):
    """
    Stateless / in-memory MVP endpoint'i.

    - Repo'yu geçici bir dizine klonlar
    - FAISS index'i sadece memory'de kurar
    - Wiki outline ve sayfaları üretir
    - Tam HTML çıktısını JSON içinde döndürür
    - Diskte kalıcı hiçbir veri bırakmaz.
    """
    logger.info("POST /api/generate_ephemeral repo_url=%s client=%s", req.repo_url, request.client)
    tmp_repo = None
    try:
        tmp_repo = clone_repo_temp(req.repo_url, git_token=req.git_token)
        repo_id = normalize_repo_id(req.repo_url)

        # In-memory index
        index, metadatas = build_in_memory_index(tmp_repo, req.llm)

        # Outline (cache'siz)
        sections = generate_wiki_outline_ephemeral(tmp_repo, req.llm)

        # Tüm section'lar için markdown üret
        pages_md: list[str] = []
        for section in sections:
            page = generate_wiki_page_ephemeral(section, req.llm, index, metadatas)
            pages_md.append(page.markdown)

        html = build_full_wiki_html_ephemeral(repo_id, sections, pages_md)

        logger.info("Ephemeral wiki generated successfully for repo_id=%s", repo_id)
        return GenerateWikiEphemeralResponse(
            repo_id=repo_id,
            sections=sections,
            html=html,
        )
    except Exception as e:
        logger.exception("Error in /api/generate_ephemeral for repo_url=%s", req.repo_url)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_repo and tmp_repo.exists():
            try:
                shutil.rmtree(tmp_repo, ignore_errors=True)
            except Exception:
                logger.warning("Failed to cleanup temp repo at %s", tmp_repo)


@app.post("/api/wiki_page", response_model=GetWikiPageResponse)
def get_wiki_page(req: GetWikiPageRequest):
    """
    Tek bir wiki section'ı için markdown sayfası döner.
    Sayfa daha önce üretilmişse cache'ten okur,
    değilse seçilen LLM ile üretip diske yazar.

    Not: UI'de artık tam HTML preview kullanıyoruz; bu endpoint
    şimdilik geri uyumluluk / ileride section-bazlı görüntüleme için duruyor.
    """
    repo_id = req.repo_id
    section_id = req.section_id
    llm = req.llm

    outline_path = WIKI_DIR / f"{repo_id}_outline.json"
    if not outline_path.exists():
        raise HTTPException(status_code=404, detail="Outline not found for repo")

    outline_data = json.loads(outline_path.read_text(encoding="utf-8"))
    sections = [WikiSection(**s) for s in outline_data]
    section = next((s for s in sections if s.id == section_id), None)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    page_path = WIKI_DIR / f"{repo_id}_{section_id}.md"

    index_path, meta_path = get_index_paths(repo_id)
    if not index_path.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail="Index not found for repo")
    index = FaissIndex.load(index_path, meta_path)

    if page_path.exists():
        markdown = page_path.read_text(encoding="utf-8")
        page = WikiPage(section=section, markdown=markdown)
    else:
        page = generate_wiki_page(repo_id, section, llm, index)

    return GetWikiPageResponse(
        repo_id=repo_id,
        section_id=section_id,
        page=page,
    )


@app.get("/api/wiki_html/{repo_id}")
def get_wiki_html(repo_id: str, request: Request):
    """
    Repo için önceden üretilmiş tam HTML wiki çıktısını döner.

    Burada:
    - Hiçbir LLM çağrısı yok
    - Hiçbir embedding / index işlemi yok
    Sadece diskten WIKI_DIR/{repo_id}_wiki.html okunur.
    """
    logger.info("GET /api/wiki_html repo_id=%s client=%s", repo_id, request.client)
    html_path = WIKI_DIR / f"{repo_id}_wiki.html"
    if not html_path.exists():
        logger.warning("HTML wiki not found for repo_id=%s", repo_id)
        raise HTTPException(status_code=404, detail="HTML wiki not found for repo")

    html = html_path.read_text(encoding="utf-8")
    logger.info("HTML wiki served for repo_id=%s", repo_id)
    return Response(content=html, media_type="text/html")


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request):
    """
    RAG ile "ask the repo" endpoint'i.
    """
    logger.info("POST /api/ask repo_id=%s client=%s", req.repo_id, request.client)
    try:
        answer, used_paths = ask_repo(
            repo_id=req.repo_id,
            question=req.question,
            llm=req.llm,
            conversation_history=req.conversation_history or [],
        )
        logger.info(
            "Ask completed for repo_id=%s, used_paths_count=%d",
            req.repo_id,
            len(used_paths),
        )
        return AskResponse(
            answer=answer,
            used_section_ids=used_paths,
        )
    except Exception as e:
        logger.exception("Error in /api/ask for repo_id=%s", req.repo_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/deep_research", response_model=DeepResearchResponse)
def deep_research(req: DeepResearchRequest, request: Request):
    """
    Çok turlu, daha derinlemesine bir araştırma modu.

    - Aynı RAG index'ini kullanır
    - Birden fazla iterasyon halinde araştırma planı, güncellemeler ve
      final bir sonuç üretir
    """
    logger.info(
        "POST /api/deep_research repo_id=%s max_iterations=%d client=%s",
        req.repo_id,
        req.max_iterations,
        request.client,
    )
    try:
        final_answer, raw_iterations = run_deep_research(
            repo_id=req.repo_id,
            question=req.question,
            llm=req.llm,
            max_iterations=req.max_iterations,
        )
        iterations = [
            DeepResearchIteration(**it) for it in raw_iterations
        ]
        logger.info(
            "Deep research completed for repo_id=%s iterations=%d",
            req.repo_id,
            len(raw_iterations),
        )
        return DeepResearchResponse(
            final_answer=final_answer,
            iterations=iterations,
        )
    except Exception as e:
        logger.exception("Error in /api/deep_research for repo_id=%s", req.repo_id)
        raise HTTPException(status_code=500, detail=str(e))