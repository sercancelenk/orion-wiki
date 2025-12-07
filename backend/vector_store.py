from pathlib import Path
from typing import List, Tuple, Dict

import faiss
import numpy as np
import json

from .config import FAISS_DIR


class FaissIndex:
    def __init__(self, dim: int, index_path: Path, meta_path: Path):
        self.dim = dim
        self.index_path = index_path
        self.meta_path = meta_path
        self.index = faiss.IndexFlatL2(dim)
        self.metadata: List[Dict] = []

    def add(self, embeddings: List[List[float]], metadatas: List[Dict]):
        vecs = np.array(embeddings, dtype="float32")
        if vecs.shape[1] != self.dim:
            raise ValueError(f"Embedding dimension mismatch: {vecs.shape[1]} != {self.dim}")
        self.index.add(vecs)
        self.metadata.extend(metadatas)

    def save(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.index_path))
        with self.meta_path.open("w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, index_path: Path, meta_path: Path) -> "FaissIndex":
        index = faiss.read_index(str(index_path))
        with meta_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)
        dim = index.d
        obj = cls(dim=dim, index_path=index_path, meta_path=meta_path)
        obj.index = index
        obj.metadata = metadata
        return obj

    def search(self, query_emb: List[float], top_k: int = 8) -> List[Dict]:
        q = np.array([query_emb], dtype="float32")
        distances, indices = self.index.search(q, top_k)
        results: List[Dict] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            item = dict(self.metadata[idx])
            item["score"] = float(dist)
            results.append(item)
        return results


def get_index_paths(repo_id: str) -> Tuple[Path, Path]:
    index_path = FAISS_DIR / f"{repo_id}.index"
    meta_path = FAISS_DIR / f"{repo_id}.meta.json"
    return index_path, meta_path