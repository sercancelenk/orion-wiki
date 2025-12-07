from typing import List, Dict, Any, Tuple

from .embeddings import EmbeddingClient
from .chat_client import ChatClient
from .vector_store import FaissIndex, get_index_paths
from .models import LLMConfig
from .prompts import (
    DEEP_RESEARCH_FIRST_ITERATION_PROMPT,
    DEEP_RESEARCH_INTERMEDIATE_ITERATION_PROMPT,
    DEEP_RESEARCH_FINAL_ITERATION_PROMPT,
)


def _load_index(repo_id: str) -> FaissIndex:
    index_path, meta_path = get_index_paths(repo_id)
    return FaissIndex.load(index_path, meta_path)


def _build_contexts(neighbors: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for n in neighbors:
        blocks.append(f"File: {n['path']}\n\n{n['text']}\n---")
    return "\n\n".join(blocks)


def _build_history_text(iterations: List[Dict[str, str]]) -> str:
    """
    Önceki araştırma adımlarını düz metin olarak birleştirir.
    """
    if not iterations:
        return ""
    parts = []
    for it in iterations:
        label = it.get("label", "")
        content = it.get("content", "")
        parts.append(f"{label}\n{content}\n")
    return "\n\n".join(parts)


def _build_messages(
    stage: str,
    iteration: int,
    question: str,
    contexts: str,
    history_text: str,
    llm: LLMConfig,
) -> List[Dict[str, str]]:
    """
    Deep research için chat mesajlarını hazırlar.

    stage: "first" | "intermediate" | "final"
    """
    if stage == "first":
        system_prompt = DEEP_RESEARCH_FIRST_ITERATION_PROMPT
    elif stage == "final":
        system_prompt = DEEP_RESEARCH_FINAL_ITERATION_PROMPT
    else:
        system_prompt = DEEP_RESEARCH_INTERMEDIATE_ITERATION_PROMPT

    # Basit bir formatlama; sadece ihtiyaç duyulan placeholder'ları dolduruyoruz.
    if stage == "intermediate":
        system_text = system_prompt.format(iteration=iteration)
    else:
        system_text = system_prompt

    user_parts = [
        f"User question:\n{question}\n",
    ]
    if history_text:
        user_parts.append("Previous research iterations:\n")
        user_parts.append(history_text)
    if contexts:
        user_parts.append("\nRelevant repository contexts:\n")
        user_parts.append(contexts)

    user_text = "\n".join(user_parts)

    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]


def run_deep_research(
    repo_id: str,
    question: str,
    llm: LLMConfig,
    max_iterations: int = 3,
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Repo üzerinde çok turlu bir araştırma süreci yürütür.

    - Her iterasyonda soru için embedding üretir ve FAISS index'ten bağlam toplar
    - İlk iterasyonda araştırma planı + ilk bulgular
    - Orta iterasyonlarda derinleşen "research update" çıktıları
    - Son iterasyonda kapsamlı bir "final conclusion"
    """
    if max_iterations < 1:
        max_iterations = 1
    if max_iterations > 5:
        max_iterations = 5

    index = _load_index(repo_id)
    embed_client = EmbeddingClient(llm)
    chat_client = ChatClient(llm)

    iterations: List[Dict[str, str]] = []
    final_answer = ""

    for i in range(1, max_iterations + 1):
        if i == 1:
            stage = "first"
            label = f"## Research Plan (iteration {i})"
        elif i == max_iterations:
            stage = "final"
            label = f"## Final Conclusion (iteration {i})"
        else:
            stage = "intermediate"
            label = f"## Research Update ({i})"

        # Her iterasyonda soruya göre embedding + en ilgili context'ler
        q_emb = embed_client.embed_texts([question])[0]
        neighbors = index.search(q_emb, top_k=12)
        contexts = _build_contexts(neighbors)

        history_text = _build_history_text(iterations)
        messages = _build_messages(
            stage=stage,
            iteration=i,
            question=question,
            contexts=contexts,
            history_text=history_text,
            llm=llm,
        )

        content = chat_client.chat(messages)

        iterations.append(
            {
                "stage": stage,
                "label": label,
                "content": content,
            }
        )

        if stage == "final":
            final_answer = content

    if not final_answer and iterations:
        final_answer = iterations[-1]["content"]

    return final_answer, iterations


