from typing import List, Dict
from pathlib import Path


def split_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Çok basit bir karakter bazlı splitter.
    Lite versiyon için yeterli; ileride token-bazlı hale getirilebilir.
    """
    chunks: List[str] = []
    start = 0
    n = len(text)

    if n == 0:
        return chunks

    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]
        chunks.append(chunk)
        if end == n:
            break
        start = end - overlap
        if start < 0:
            start = 0

    return chunks


def build_documents_from_files(files) -> List[Dict]:
    """
    Dosyalardan doküman listesi üretir:
    [{"id": ..., "path": ..., "text": ...}, ...]
    """
    docs = []
    for idx, path in enumerate(files):
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        docs.append(
            {
                "id": f"doc_{idx}",
                "path": str(path),
                "text": text,
            }
        )
    return docs