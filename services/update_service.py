"""
Serviço de Verificação e Atualização Automática do DailyNotes via GitHub Releases.
Verifica novas versões disponibilizadas no repositório GitHub sem perder dados locais (SQLite / backups).
"""

import os
import re
import sys
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Tuple

import config

logger = logging.getLogger(__name__)


def parse_semver(version_str: str) -> Tuple[int, int, int]:
    """
    Converte uma string de versão (ex: 'v1.1.0', '1.2.3', 'V2.0') em tupla de inteiros (1, 1, 0)
    para comparação numérica estrita (SemVer).
    """
    clean = re.sub(r"^[^\d]*", "", (version_str or "").strip())
    parts = clean.split(".")
    nums = []
    for p in parts[:3]:
        m = re.match(r"^(\d+)", p)
        nums.append(int(m.group(1)) if m else 0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def is_version_newer(latest_version: str, current_version: str) -> bool:
    """Retorna True se latest_version for estritamente mais recente que current_version."""
    return parse_semver(latest_version) > parse_semver(current_version)


class UpdateService:
    """
    Serviço responsável por consultar a API do GitHub Releases,
    identificar se há uma versão nova e disponibilizar os detalhes de download.
    """

    def __init__(self, current_version: Optional[str] = None):
        self.current_version = current_version or config.APP_VERSION
        self.latest_release_url = config.GITHUB_API_LATEST_RELEASE

    def check_for_updates(self, timeout_sec: int = 5) -> Dict[str, Any]:
        """
        Consulta a API do GitHub Releases para verificar se há uma nova versão disponível.
        Retorna um dicionário:
        {
            "has_update": bool,
            "current_version": str,
            "latest_version": str,
            "release_name": str,
            "release_notes": str,
            "html_url": str,
            "download_url": Optional[str],
            "asset_name": Optional[str],
            "asset_size": int,
            "error": Optional[str]
        }
        """
        result = {
            "has_update": False,
            "current_version": self.current_version,
            "latest_version": self.current_version,
            "release_name": "",
            "release_notes": "",
            "html_url": config.GITHUB_RELEASES_URL,
            "download_url": None,
            "asset_name": None,
            "asset_size": 0,
            "error": None,
        }

        req = urllib.request.Request(
            self.latest_release_url,
            headers={
                "User-Agent": f"DailyNotes-Updater/{self.current_version}",
                "Accept": "application/vnd.github.v3+json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                if resp.status != 200:
                    result["error"] = f"Resposta inesperada do GitHub (HTTP {resp.status})"
                    return result
                data = json.loads(resp.read().decode("utf-8"))

            tag_name = data.get("tag_name", "")
            latest_ver = tag_name.lstrip("vV")
            if not latest_ver:
                return result

            result["latest_version"] = latest_ver
            result["release_name"] = data.get("name") or f"Versão {latest_ver}"
            result["release_notes"] = data.get("body") or ""
            result["html_url"] = data.get("html_url") or config.GITHUB_RELEASES_URL

            # Localiza o executável instalador nos assets da release (.exe)
            assets = data.get("assets", [])
            chosen_asset = None
            for asset in assets:
                name = asset.get("name", "")
                if name.lower().endswith(".exe"):
                    # Dá prioridade para o Instalador/Setup
                    if "setup" in name.lower() or "instalador" in name.lower():
                        chosen_asset = asset
                        break
                    elif chosen_asset is None:
                        chosen_asset = asset

            if chosen_asset:
                result["download_url"] = chosen_asset.get("browser_download_url")
                result["asset_name"] = chosen_asset.get("name")
                result["asset_size"] = chosen_asset.get("size", 0)

            # Compara semanticamente as versões
            if is_version_newer(latest_ver, self.current_version):
                result["has_update"] = True

        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Nenhuma release publicada ainda no repositório
                result["error"] = "Nenhuma release publicada no repositório GitHub ainda."
            else:
                result["error"] = f"Erro ao consultar GitHub (HTTP {e.code})"
            logger.debug("Verificação de atualização: %s", result["error"])
        except urllib.error.URLError as e:
            result["error"] = f"Sem conexão com a internet ou GitHub inacessível ({e.reason})"
            logger.debug("Verificação de atualização: %s", result["error"])
        except Exception as e:
            result["error"] = str(e)
            logger.warning("Falha ao checar atualização: %s", e)

        return result

    def download_installer(
        self,
        download_url: str,
        dest_path: str,
        progress_callback=None,
        cancel_event=None,
    ) -> bool:
        """
        Baixa o instalador (.exe) da release diretamente para dest_path com reporte de progresso.
        Retorna True se concluído com sucesso.
        """
        try:
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": f"DailyNotes-Updater/{self.current_version}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                block_size = 64 * 1024  # 64 KB

                os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
                with open(dest_path, "wb") as f:
                    while True:
                        if cancel_event and cancel_event.is_set():
                            return False
                        chunk = resp.read(block_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            progress_callback(pct, downloaded, total_size)

            return True
        except Exception as e:
            logger.error("Erro ao baixar instalador da nova versão: %s", e)
            if os.path.isfile(dest_path):
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            return False

