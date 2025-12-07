from pathlib import Path

# Proje temel dizinleri
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
REPO_DIR = STORAGE_DIR / "repos"
FAISS_DIR = STORAGE_DIR / "faiss"
WIKI_DIR = STORAGE_DIR / "wiki"

# Chunk ayarları
CHUNK_SIZE = 800
CHUNK_OVERLAP = 200

# Embedding istekleri için batch boyutu
# (64 chunk * ~500 token ≈ 32k token civarı, gayet güvenli)
EMBEDDING_BATCH_SIZE = 64

# Hangi uzantıları okuyalım?
INCLUDED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".java", ".kt", ".go",
    ".cs", ".cpp", ".c", ".rs", ".php", ".rb",
    ".md", ".txt", ".json", ".yml", ".yaml",
}

# Hariç tutulan klasörler
EXCLUDED_DIRS = {
    ".git", ".github", "node_modules", "dist", "build",
    "__pycache__", ".venv", ".idea", ".vscode",
}