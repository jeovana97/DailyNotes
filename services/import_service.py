import os
import logging
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Tuple
import config
from database.connection import get_connection, get_db
from database.schema import CREATE_IMPORT_HISTORY_TABLE
from services.diary_service import DiaryService
from services.note_service import NoteService
from utils.date_utils import parse_date_from_filename, format_date_br, get_current_timestamp
from utils.text_utils import detect_encoding

logger = logging.getLogger(__name__)


class ConflictResolution(str, Enum):
    SKIP = "skip"          # Ignora o arquivo mantendo o conteúdo existente
    REPLACE = "replace"    # Substitui a anotação/nota existente pelo novo conteúdo
    MERGE = "merge"        # Mescla o conteúdo, anexando com separador datado


SUPPORTED_NOTE_EXTENSIONS: Tuple[str, ...] = (".txt", ".xml", ".bat", ".sql")


class ImportService:
    def __init__(
        self,
        diary_service: Optional[DiaryService] = None,
        note_service: Optional[NoteService] = None,
        db_path: Optional[str] = None,
    ):
        self.db_path = (
            db_path
            or (diary_service.db_path if diary_service else None)
            or (note_service.db_path if note_service else None)
            or config.DB_PATH
        )
        self.diary_service = diary_service or DiaryService(db_path=self.db_path)
        self.note_service = note_service or NoteService(db_path=self.db_path)
        self._ensure_history_table()

    def _ensure_history_table(self) -> None:
        """Garante que a tabela import_history e suas colunas existam no banco de dados."""
        try:
            with get_db(self.db_path) as conn:
                conn.execute(CREATE_IMPORT_HISTORY_TABLE)
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(import_history)")
                existing_cols = {row["name"] for row in cursor.fetchall()}

                migrations = [
                    ("target_type", "ALTER TABLE import_history ADD COLUMN target_type TEXT NOT NULL DEFAULT 'note'"),
                    ("folder_id", "ALTER TABLE import_history ADD COLUMN folder_id INTEGER DEFAULT NULL"),
                    ("folder_name", "ALTER TABLE import_history ADD COLUMN folder_name TEXT NOT NULL DEFAULT ''"),
                    ("note_id", "ALTER TABLE import_history ADD COLUMN note_id INTEGER DEFAULT NULL"),
                ]
                for col_name, sql in migrations:
                    if col_name not in existing_cols:
                        try:
                            conn.execute(sql)
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("Aviso ao garantir tabela import_history: %s", e)

    def _record_import(
        self,
        user_id: int,
        filename: str,
        file_path: str,
        entry_date: str = "",
        target_type: str = "note",
        folder_id: Optional[int] = None,
        folder_name: str = "",
        note_id: Optional[int] = None,
    ) -> None:
        """Registra no banco de dados o arquivo TXT recém-importado."""
        self._ensure_history_table()
        now_str = get_current_timestamp()
        try:
            with get_db(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO import_history (
                        user_id, filename, file_path, entry_date,
                        target_type, folder_id, folder_name, note_id, imported_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        filename,
                        file_path or "",
                        entry_date or "",
                        target_type,
                        folder_id,
                        folder_name or "",
                        note_id,
                        now_str,
                    ),
                )
        except Exception as e:
            logger.warning("Não foi possível registrar histórico de importação: %s", e)

    def get_last_imported_txt(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Retorna as informações do último arquivo TXT importado pelo usuário:
        - filename: nome do arquivo (ex: 'Consulta SQL.txt' ou '27 10 2026.txt')
        - file_path: caminho completo (se disponível)
        - target_type: 'note' ou 'diary'
        - folder_id: ID da pasta (se target_type == 'note')
        - folder_name: Nome/caminho da pasta (se target_type == 'note')
        - note_id: ID da nota criada/atualizada
        - entry_date: data ISO ('2026-10-27', se target_type == 'diary')
        - date_br: data formatada ('27/10/2026', se target_type == 'diary')
        - imported_at: data/hora da importação ('YYYY-MM-DD HH:MM:SS')
        """
        self._ensure_history_table()
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT filename, file_path, entry_date, target_type, folder_id, folder_name, note_id, imported_at
                FROM import_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                entry_date = row["entry_date"] or ""
                target_type = row["target_type"] or ("diary" if entry_date else "note")
                folder_name = row["folder_name"] or "Raiz (Sem pasta)"
                return {
                    "filename": row["filename"],
                    "file_path": row["file_path"],
                    "target_type": target_type,
                    "folder_id": row["folder_id"],
                    "folder_name": folder_name,
                    "note_id": row["note_id"],
                    "entry_date": entry_date,
                    "date_br": format_date_br(entry_date) if entry_date else "",
                    "imported_at": row["imported_at"],
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

    # =========================================================================
    # Importação de Notas para Pastas (Sem exigência de formato de data)
    # =========================================================================

    def import_note_file(
        self,
        file_path: str,
        user_id: int,
        folder_id: Optional[int] = None,
        conflict_resolution: ConflictResolution = ConflictResolution.SKIP,
    ) -> Dict[str, Any]:
        """
        Importa um arquivo TXT para uma pasta do módulo 'Notas & Pastas'.
        Não exige formato de data no nome do arquivo: o nome do arquivo (sem extensão)
        torna-se o título da nota dentro da pasta escolhida.
        """
        filename = os.path.basename(file_path)
        note_title = os.path.splitext(filename)[0].strip() or filename

        path_map = self.note_service.get_folder_path_map(user_id)
        folder_label = (
            path_map.get(folder_id, "Raiz (Sem pasta)")
            if folder_id is not None
            else "Raiz (Sem pasta)"
        )

        # 1. Lê o conteúdo do arquivo
        try:
            content, _enc = self.read_file_content(file_path)
        except Exception as e:
            return {
                "status": "error",
                "filename": filename,
                "file_path": file_path,
                "note_id": None,
                "folder_id": folder_id,
                "folder_name": folder_label,
                "message": f"Erro ao ler arquivo ({str(e)}).",
            }

        if not content.strip():
            return {
                "status": "skipped",
                "filename": filename,
                "file_path": file_path,
                "note_id": None,
                "folder_id": folder_id,
                "folder_name": folder_label,
                "message": "Arquivo ignorado: conteúdo vazio.",
            }

        # 2. Verifica se já existe nota com o mesmo título na pasta selecionada
        existing_note = self.note_service.get_note_by_title_in_folder(
            user_id=user_id,
            title=note_title,
            folder_id=folder_id,
        )

        if existing_note is not None:
            if conflict_resolution == ConflictResolution.SKIP:
                return {
                    "status": "skipped",
                    "filename": filename,
                    "file_path": file_path,
                    "note_id": existing_note.id,
                    "folder_id": folder_id,
                    "folder_name": folder_label,
                    "message": f"Nota '{note_title}' já existe em '{folder_label}'. Ignorado conforme escolha.",
                }
            elif conflict_resolution == ConflictResolution.REPLACE:
                saved = self.note_service.save_note(
                    user_id=user_id,
                    title=note_title,
                    content=content,
                    folder_id=folder_id,
                    note_id=existing_note.id,
                )
                self._record_import(
                    user_id=user_id,
                    filename=filename,
                    file_path=file_path,
                    target_type="note",
                    folder_id=folder_id,
                    folder_name=folder_label,
                    note_id=saved.id,
                )
                return {
                    "status": "imported",
                    "filename": filename,
                    "file_path": file_path,
                    "note_id": saved.id,
                    "folder_id": folder_id,
                    "folder_name": folder_label,
                    "message": f"Nota '{note_title}' substituída com sucesso na pasta '{folder_label}'.",
                }
            elif conflict_resolution == ConflictResolution.MERGE:
                now_str = get_current_timestamp()
                merged_content = (
                    f"{(existing_note.content or '').rstrip()}\n\n"
                    f"--- CONTEÚDO IMPORTADO ({filename} em {now_str}) ---\n\n"
                    f"{content.strip()}"
                )
                saved = self.note_service.save_note(
                    user_id=user_id,
                    title=note_title,
                    content=merged_content,
                    folder_id=folder_id,
                    note_id=existing_note.id,
                )
                self._record_import(
                    user_id=user_id,
                    filename=filename,
                    file_path=file_path,
                    target_type="note",
                    folder_id=folder_id,
                    folder_name=folder_label,
                    note_id=saved.id,
                )
                return {
                    "status": "imported",
                    "filename": filename,
                    "file_path": file_path,
                    "note_id": saved.id,
                    "folder_id": folder_id,
                    "folder_name": folder_label,
                    "message": f"Nota '{note_title}' mesclada com sucesso na pasta '{folder_label}'.",
                }

        # 3. Cria nova nota na pasta escolhida
        saved = self.note_service.save_note(
            user_id=user_id,
            title=note_title,
            content=content,
            folder_id=folder_id,
        )
        self._record_import(
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            target_type="note",
            folder_id=folder_id,
            folder_name=folder_label,
            note_id=saved.id,
        )
        return {
            "status": "imported",
            "filename": filename,
            "file_path": file_path,
            "note_id": saved.id,
            "folder_id": folder_id,
            "folder_name": folder_label,
            "message": f"Nota '{note_title}' importada com sucesso na pasta '{folder_label}'.",
        }

    def import_folder_to_notes(
        self,
        folder_path: str,
        user_id: int,
        target_folder_id: Optional[int] = None,
        default_conflict: ConflictResolution = ConflictResolution.SKIP,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Importa todos os arquivos suportados (.txt, .xml, .bat, .sql) de um diretório do computador
        diretamente para a pasta escolhida em 'Notas & Pastas', sem exigir formato de data no nome dos arquivos.
        """
        if not os.path.isdir(folder_path):
            raise ValueError(f"O caminho informado não é uma pasta válida: {folder_path}")

        note_files = [
            f for f in os.listdir(folder_path)
            if f.lower().endswith(SUPPORTED_NOTE_EXTENSIONS) and os.path.isfile(os.path.join(folder_path, f))
        ]
        note_files.sort(key=lambda fname: fname.lower())

        path_map = self.note_service.get_folder_path_map(user_id)
        folder_label = (
            path_map.get(target_folder_id, "Raiz (Sem pasta)")
            if target_folder_id is not None
            else "Raiz (Sem pasta)"
        )

        total_files = len(note_files)
        imported_count = 0
        skipped_count = 0
        error_count = 0
        last_note_id: Optional[int] = None
        details: List[Dict[str, Any]] = []

        for idx, filename in enumerate(note_files, start=1):
            file_path = os.path.join(folder_path, filename)
            if progress_callback:
                progress_callback(idx, total_files, filename)

            try:
                res = self.import_note_file(
                    file_path=file_path,
                    user_id=user_id,
                    folder_id=target_folder_id,
                    conflict_resolution=default_conflict,
                )
                if res["status"] == "imported":
                    imported_count += 1
                    last_note_id = res.get("note_id") or last_note_id
                elif res["status"] == "skipped":
                    skipped_count += 1
                else:
                    error_count += 1

                details.append({
                    "filename": filename,
                    "status": res["status"],
                    "folder_name": folder_label,
                    "note_id": res.get("note_id"),
                    "message": res["message"],
                })
            except Exception as e:
                error_count += 1
                details.append({
                    "filename": filename,
                    "status": "error",
                    "folder_name": folder_label,
                    "note_id": None,
                    "message": f"Erro inesperado: {str(e)}",
                })

        return {
            "total": total_files,
            "imported": imported_count,
            "skipped": skipped_count,
            "errors": error_count,
            "target_folder_id": target_folder_id,
            "target_folder_name": folder_label,
            "last_note_id": last_note_id,
            "details": details,
        }

    # =========================================================================
    # Importação por Data para o Diário (Mantido para compatibilidade)
    # =========================================================================

    def import_file(
        self,
        file_path: str,
        user_id: int,
        conflict_resolution: ConflictResolution = ConflictResolution.SKIP,
        explicit_date_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Importa um único arquivo TXT datado para o Diário."""
        filename = os.path.basename(file_path)

        date_iso = explicit_date_iso or parse_date_from_filename(filename)
        if not date_iso:
            return {
                "status": "error",
                "filename": filename,
                "file_path": file_path,
                "date_iso": None,
                "message": "Nome do arquivo não segue o padrão de data (ex: '01 10 2026.txt').",
            }

        try:
            content, _enc = self.read_file_content(file_path)
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

        existing_entry = self.diary_service.get_entry_by_date(user_id, date_iso)

        if existing_entry and existing_entry.content.strip():
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
                self._record_import(user_id, filename, file_path, entry_date=date_iso, target_type="diary")
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
                self._record_import(user_id, filename, file_path, entry_date=date_iso, target_type="diary")
                return {
                    "status": "imported",
                    "filename": filename,
                    "file_path": file_path,
                    "date_iso": date_iso,
                    "message": f"Anotação de {format_date_br(date_iso)} mesclada com sucesso.",
                }

        self.diary_service.save_entry(user_id, date_iso, content)
        self._record_import(user_id, filename, file_path, entry_date=date_iso, target_type="diary")
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
        """Importa todos os arquivos .txt datados de uma pasta para o Diário."""
        if not os.path.isdir(folder_path):
            raise ValueError(f"O caminho informado não é uma pasta válida: {folder_path}")

        txt_files = [
            f for f in os.listdir(folder_path)
            if f.lower().endswith(".txt") and os.path.isfile(os.path.join(folder_path, f))
        ]
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

            existing = self.diary_service.get_entry_by_date(user_id, date_iso)
            resolution = global_resolution

            if existing and existing.content.strip():
                if resolution is None and conflict_callback:
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
