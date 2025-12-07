from typing import List, Dict, Any

from .embeddings import EmbeddingClient
from .chat_client import ChatClient
from .vector_store import FaissIndex, get_index_paths
from .prompts import RAG_SYSTEM_PROMPT, RAG_TEMPLATE
from .models import LLMConfig


def load_index_for_repo(repo_id: str) -> FaissIndex:
    index_path, meta_path = get_index_paths(repo_id)
    return FaissIndex.load(index_path, meta_path)


def create_rag_prompt(
    question: str,
    contexts: List[Dict[str, Any]],
    conversation_history: List[Dict[str, str]] | None,
) -> str:
    history_str = ""
    if conversation_history:
        for turn in conversation_history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            history_str += f"{role.upper()}: {content}\n"

    context_strs = []
    for c in contexts:
        context_strs.append(f"File: {c['path']}\n\n{c['text']}\n---")
    contexts_joined = "\n\n".join(context_strs)

    return RAG_TEMPLATE.format(
        system_prompt=RAG_SYSTEM_PROMPT,
        input_str=question,
        contexts=contexts_joined,
        conversation_history=history_str,
    )


def ask_repo(
    repo_id: str,
    question: str,
    llm: LLMConfig,
    conversation_history: List[Dict[str, str]] | None,
) -> tuple[str, List[str]]:
    index = load_index_for_repo(repo_id)
    embed_client = EmbeddingClient(llm)
    chat_client = ChatClient(llm)

    q_emb = embed_client.embed_texts([question])[0]
    neighbors = index.search(q_emb, top_k=10)

    prompt = create_rag_prompt(question, neighbors, conversation_history)

    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    answer = chat_client.chat(messages)

    used_paths = list({n["path"] for n in neighbors})
    return answer, used_paths