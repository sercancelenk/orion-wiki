import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

from .config import REPO_DIR, INCLUDED_EXTENSIONS, EXCLUDED_DIRS


def normalize_repo_id(repo_url: str) -> str:
    """
    https://github.com/owner/repo(.git) -> owner_repo
    """
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    parts = repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    return f"{owner}_{repo}"


def _inject_git_token(repo_url: str, git_token: Optional[str]) -> str:
    """
    HTTPS tabanlı git URL'lerine access token enjekte eder.

    Örnek (GitLab):
        https://gitlab.xxx.com/group/repo.git
        + git_token -> https://oauth2:<token>@gitlab.xxx.com/group/repo.git

    Not: Sadece http/https URL'ler için uygulanır; ssh URL'ler aynen bırakılır.
    """
    if not git_token:
        return repo_url

    parsed = urlparse(repo_url)
    if parsed.scheme not in ("http", "https"):
        return repo_url

    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""

    # GitLab için oauth2 kullanıcı adı öneriliyor; diğer host'larda basit token kullan.
    if "gitlab" in host.lower():
        userinfo = f"oauth2:{git_token}"
    else:
        userinfo = git_token

    netloc = f"{userinfo}@{host}{port}"
    new_parsed = parsed._replace(netloc=netloc)
    return urlunparse(new_parsed)


def clone_or_update_repo(repo_url: str, git_token: Optional[str] = None) -> Path:
    repo_id = normalize_repo_id(repo_url)
    target_dir = REPO_DIR / repo_id
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if target_dir.exists():
        subprocess.run(["git", "-C", str(target_dir), "pull"], check=True)
    else:
        clone_url = _inject_git_token(repo_url, git_token)
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(target_dir)],
            check=True,
        )

    return target_dir


def clone_repo_temp(repo_url: str, git_token: Optional[str] = None) -> Path:
    """
    Stateless / in-memory MVP için:
    - Repo'yu geçici bir dizine klonlar
    - Kullanan kod, iş bitince bu dizini silmelidir.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="repo_"))
    clone_url = _inject_git_token(repo_url, git_token)
    subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(tmp_dir)],
        check=True,
    )
    return tmp_dir


def iter_repo_files(repo_path: Path) -> List[Path]:
    """
    Basit dosya tarayıcı: EXCLUDED_DIRS'ı atlar, sadece INCLUDED_EXTENSIONS uzantılarını alır.
    """
    files: List[Path] = []
    for path in repo_path.rglob("*"):
        if path.is_dir():
            # rglob zaten derin iner, burada isim filtreliyoruz
            if path.name in EXCLUDED_DIRS:
                continue
            else:
                continue
        if path.suffix.lower() in INCLUDED_EXTENSIONS:
            files.append(path)
    return files


def build_file_tree_summary(repo_path: Path, max_entries: int = 200) -> str:
    """
    Prompt içinde kullanmak için basit bir tree çıktısı.
    """
    files = iter_repo_files(repo_path)
    lines = []
    root_len = len(str(repo_path)) + 1
    count = 0
    for p in sorted(files):
        rel = str(p)[root_len:]
        lines.append(rel)
        count += 1
        if count >= max_entries:
            lines.append("... (truncated)")
            break
    return "\n".join(lines)