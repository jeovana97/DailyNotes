# Controle Centralizado de Versão e Atualizações do DailyNotes
# Padrão SemVer (Semantic Versioning): MAJOR.MINOR.PATCH

import os
import sys


def read_version_file(default: str = "1.5.0") -> str:
    """Lê a versão atual a partir do arquivo VERSION (suporta execução normal e PyInstaller)."""
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(os.path.join(meipass, "VERSION"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "VERSION"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION"))

    for path in candidates:
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    val = f.read().strip().lstrip("vV")
                    if val:
                        return val
            except Exception:
                pass
    return default


APP_NAME = "Diário de Anotações Inteligente"
APP_SHORT_NAME = "Diário de Anotações"
APP_VERSION = read_version_file()
APP_AUTHOR = "DAILYNotes"

# Repositório oficial do GitHub para verificação e download de atualizações
GITHUB_REPO_OWNER = "jeovana97"
GITHUB_REPO_NAME = "DailyNotes"
GITHUB_API_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases"

