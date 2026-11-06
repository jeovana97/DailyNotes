import os
import logging
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Tuple
import config
from database.connection import get_connection, get_db
from database.schema import CREATE_IMPORT_HISTORY_TABLE
from services.diary_service import DiaryService
from utils.date_utils import parse_date_from_filename, format_date_br, get_current_timestamp
from utils.text_utils import detect_encoding

logger = logging.getLogger(__name__)


class ConflictResolution(str, Enum):
    SKIP = "skip"          # Ignora o arquivo mantendo o conteúdo existente
    REPLACE = "replace"    # Substitui a anotação existente pelo novo conteúdo
    MERGE = "merge"        # Mescla o conteúdo, anexando com separador datado


class ImportService:
    def __init__(self, diary_service: Optional[DiaryService] = None, db_path: Optional[str] = None):
        self.db_path = db_path or (diary_service.db_path if diary_service else None) or config.DB_PATH
        self.diary_service = diary_service or DiaryService(db_path=self.db_path)
        self._ensure_history_table()

    def _ensure_history_table(self) -> None:
        """Garante que a tabela import_history exista no banco de dados."""
        try:
            with get_db(self.db_path) as conn:
                conn.execute(CREATE_IMPORT_HISTORY_TABLE)
        except Exception as e:
            logger.debug("Aviso ao garantir tabela import_history: %s", e)

    def _record_import(
        self,
        user_id: int,
        filename: str,
        file_path: str,
        entry_date: str,
    ) -> None:
        """Registra no banco de dados o arquivo TXT recém-importado."""
        self._ensure_history_table()
        now_str = get_current_timestamp()
        try:
            with get_db(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO import_history (user_id, filename, file_path, entry_date, imported_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, filename, file_path or "", entry_date, now_str),
                )
        except Exception as e:
            logger.warning("Não foi possível registrar histórico de importação: %s", e)

    def get_last_imported_txt(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Retorna as informações do último arquivo TXT importado pelo usuário:
        - filename: nome do arquivo (ex: '27 10 2026.txt')
        - file_path: caminho completo (se disponível)
        - entry_date: data ISO ('2026-10-27')
        - date_br: data formatada ('27/10/2026')
        - imported_at: data/hora da importação ('YYYY-MM-DD HH:MM:SS')
        """
        self._ensure_history_table()
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT filename, file_path, entry_date, imported_at
                FROM import_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                entry_date = row["entry_date"]
                return {
                    "filename": row["filename"],
                    "file_path": row["file_path"],
                    "entry_date": entry_date,
                    "date_br": format_date_br(entry_date),
                    "imported_at": row["imported_at"],
                }

            # Fallback para diários já existentes caso a importação tenha ocorrido antes da criação da tabela
            cursor.execute(
                """
                SELECT entry_date, updated_at
                FROM diaries
                WHERE user_id = ? AND TRIM(content) != ''
                ORDER BY entry_date DESC
                LIMIT 1
                """,
                (user_id,),
            )
            diary_row = cursor.fetchone()
            if diary_row:
                entry_date = diary_row["entry_date"]
                parts = entry_date.split("-")
                inferred_filename = (
                    f"{parts[2]} {parts[1]} {parts[0]}.txt" if len(parts) == 3 else f"{entry_date}.txt"
                )
                return {
                    "filename": inferred_filename,
                    "file_path": "",
                    "entry_date": entry_date,
                    "date_br": format_date_br(entry_date),
                    "imported_at": diary_row["updated_at"],
                }

            return None
        except Exception as e:
            logger.debug("Erro ao consultar último TXT importado: %s", e)
            return None
        finally:
            conn.close()

    def read_file_content(self, file_path: str) -> Tuple[str, str]:
        """
        Lê o conteúdo do arquivo preservando acentos, caracteres especiais e quebras de linha.
        Detecta a codificação automaticamente. Retorna (conteudo, codificacao_usada).
        """
        encoding = detect_encoding(file_path)
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            content = f.read()
        return content, encoding

    def import_file(
        self,
        file_path: str,
        user_id: int,
        conflict_resolution: ConflictResolution = ConflictResolution.SKIP,
        explicit_date_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Importa um único arquivo TXT.
        Retorna dicionário de status com:
        - status: 'imported', 'skipped', 'error', 'conflict_needed'
        - message: explicação do resultado
        - date_iso: data identificada
        - filename: nome do arquivo
        """
        filename = os.path.basename(file_path)

        # 1. Determina a data da anotação
        date_iso = explicit_date_iso or parse_date_from_filename(filename)
        if not date_iso:
            return {
                "status": "error",
                "filename": filename,
                "file_path": file_path,
                "date_iso": None,
                "message": "Nome do arquivo não segue o padrão de data (ex: '01 10 2026.txt').",
            }

        # 2. Lê o conteúdo do arquivo
        try:
            content, enc = self.read_file_content(file_path)
        except Exception as e:
            return {
                "status": "error",
                "filename": filename,
                "file_path": file_path,
                "date_iso": date_iso,
                "message": f"Erro ao ler arquivo ({str(e)}).",
            }

        if not content.strip():
            return {
                "status": "skipped",
                "filename": filename,
                "file_path": file_path,
                "date_iso": date_iso,
                "message": "Arquivo ignorado: conteúdo vazio.",
            }

        # 3. Verifica existência de anotação anterior para o mesmo dia e usuário
        existing_entry = self.diary_service.get_entry_by_date(user_id, date_iso)

        if existing_entry and existing_entry.content.strip():
            # Há duplicidade / conflito
            if conflict_resolution == ConflictResolution.SKIP:
                return {
                    "status": "skipped",
                    "filename": filename,
                    "file_path": file_path,
                    "date_iso": date_iso,
                    "message": f"Anotação de {format_date_br(date_iso)} já existe. Arquivo ignorado conforme escolha.",
                }
            elif conflict_resolution == ConflictResolution.REPLACE:
                self.diary_service.save_entry(user_id, date_iso, content)
                self._record_import(user_id, filename, file_path, date_iso)
                return {
                    "status": "imported",
                    "filename": filename,
                    "file_path": file_path,
                    "date_iso": date_iso,
                    "message": f"Anotação de {format_date_br(date_iso)} substituída com sucesso.",
                }
            elif conflict_resolution == ConflictResolution.MERGE:
                now_str = get_current_timestamp()
                merged_content = (
                    f"{existing_entry.content.rstrip()}\n\n"
                    f"--- CONTEÚDO IMPORTADO ({filename} em {now_str}) ---\n\n"
                    f"{content.strip()}"
                )
                self.diary_service.save_entry(user_id, date_iso, merged_content)
                self._record_import(user_id, filename, file_path, date_iso)
                return {
                    "status": "imported",
                    "filename": filename,
                    "file_path": file_path,
                    "date_iso": date_iso,
                    "message": f"Anotação de {format_date_br(date_iso)} mesclada com sucesso.",
                }

        # Não havia anotação anterior: salva diretamente
        self.diary_service.save_entry(user_id, date_iso, content)
        self._record_import(user_id, filename, file_path, date_iso)
        return {
            "status": "imported",
            "filename": filename,
            "file_path": file_path,
            "date_iso": date_iso,
            "message": f"Anotação de {format_date_br(date_iso)} importada com sucesso.",
        }

    def import_folder(
        self,
        folder_path: str,
        user_id: int,
        default_conflict: ConflictResolution = ConflictResolution.SKIP,
        conflict_callback: Optional[Callable[[str, str], ConflictResolution]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Importa todos os arquivos .txt de uma pasta em lote.
        Não interrompe todo o processamento se um arquivo falhar.
        Gera relatório completo ao final.
        """
        if not os.path.isdir(folder_path):
            raise ValueError(f"O caminho informado não é uma pasta válida: {folder_path}")

        txt_files = [
            f for f in os.listdir(folder_path)
            if f.lower().endswith(".txt") and os.path.isfile(os.path.join(folder_path, f))
        ]
        # Ordena cronologicamente pela data do arquivo para que o último processado seja o mais recente
        txt_files.sort(key=lambda fname: (parse_date_from_filename(fname) or "", fname.lower()))

        total_files = len(txt_files)
        imported_count = 0
        skipped_count = 0
        error_count = 0
        details: List[Dict[str, Any]] = []

        global_resolution = default_conflict if not conflict_callback else None

        for idx, filename in enumerate(txt_files, start=1):
            file_path = os.path.join(folder_path, filename)
            if progress_callback:
                progress_callback(idx, total_files, filename)

            date_iso = parse_date_from_filename(filename)
            if not date_iso:
                error_count += 1
                details.append({
                    "filename": filename,
                    "status": "error",
                    "date": None,
                    "message": "Padrão de data não reconhecido no nome do arquivo.",
                })
                continue

            # Verifica conflito prévio
            existing = self.diary_service.get_entry_by_date(user_id, date_iso)
            resolution = global_resolution

            if existing and existing.content.strip():
                if resolution is None and conflict_callback:
                    # Pergunta ao usuário via callback
                    resolution = conflict_callback(filename, date_iso)
                elif resolution is None:
                    resolution = ConflictResolution.SKIP

            try:
                res = self.import_file(
                    file_path=file_path,
                    user_id=user_id,
                    conflict_resolution=resolution or ConflictResolution.SKIP,
                    explicit_date_iso=date_iso,
                )
                if res["status"] == "imported":
                    imported_count += 1
                elif res["status"] == "skipped":
                    skipped_count += 1
                else:
                    error_count += 1

                details.append({
                    "filename": filename,
                    "status": res["status"],
                    "date": format_date_br(date_iso),
                    "message": res["message"],
                })
            except Exception as e:
                error_count += 1
                details.append({
                    "filename": filename,
                    "status": "error",
                    "date": format_date_br(date_iso) if date_iso else "N/A",
                    "message": f"Erro inesperado: {str(e)}",
                })

        return {
            "total": total_files,
            "imported": imported_count,
            "skipped": skipped_count,
            "errors": error_count,
            "details": details,
        }
