from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel


class LLMConfig(BaseModel):
    """
    UI'dan gelen LLM konfigürasyonu.
    Şimdilik sadece provider='openai' destekleniyor;
    ileride 'gemini', 'claude', 'ollama' vs. eklenebilir.
    """
    provider: Literal["openai"]
    chat_model: str        # Ör: "gpt-4.1-mini"
    embed_model: str       # Ör: "text-embedding-3-small"
    api_key: str           # UI'dan gelecek
    base_url: Optional[str] = None  # None -> varsayılan OpenAI URL'i


class GenerateWikiRequest(BaseModel):
    repo_url: str
    llm: LLMConfig
    git_token: Optional[str] = None  # Örn: GitLab/GitHub PAT (private repo erişimi için)


class WikiSection(BaseModel):
    id: str
    title: str
    description: str
    keywords: List[str]


class WikiPage(BaseModel):
    section: WikiSection
    markdown: str


class GenerateWikiResponse(BaseModel):
    repo_id: str               # Ör: "owner_repo"
    sections: List[WikiSection]


class GenerateWikiEphemeralResponse(BaseModel):
    """
    Stateless / in-memory MVP için:
    - Repo analizi yapılır
    - FAISS index sadece memory'de tutulur
    - Tüm wiki HTML çıktısı response body'de döner
    - Diskte hiçbir kalıcı dosya saklanmaz.
    """
    repo_id: str
    sections: List[WikiSection]
    html: str


class GetWikiPageRequest(BaseModel):
    repo_id: str
    section_id: str
    llm: LLMConfig


class GetWikiPageResponse(BaseModel):
    repo_id: str
    section_id: str
    page: WikiPage


class AskRequest(BaseModel):
    repo_id: str
    question: str
    llm: LLMConfig
    conversation_history: Optional[List[Dict[str, Any]]] = None


class AskResponse(BaseModel):
    answer: str
    used_section_ids: List[str]  # Aslında file path'ler; isimlendirme sade bırakıldı


class DeepResearchIteration(BaseModel):
    stage: str          # "first" | "intermediate" | "final"
    label: str          # Örn: "## Research Plan (iteration 1)"
    content: str        # LLM çıktısı


class DeepResearchRequest(BaseModel):
    repo_id: str
    question: str
    llm: LLMConfig
    max_iterations: int = 3


class DeepResearchResponse(BaseModel):
    final_answer: str
    iterations: List[DeepResearchIteration]