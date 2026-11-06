import logging
from typing import Optional, Set, List, Tuple
from database.connection import get_connection, get_db
from models.diary import DiaryEntry
from utils.date_utils import get_current_timestamp, is_valid_iso_date
from utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


class DiaryService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def get_entry_by_date(self, user_id: int, entry_date: str) -> Optional[DiaryEntry]:
        """
        Recupera a anotação existente para o usuário e data informados.
        """
        if not is_valid_iso_date(entry_date):
            return None

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT d.*, u.full_name, u.username
                FROM diaries d
                JOIN users u ON d.user_id = u.id
                WHERE d.user_id = ? AND d.entry_date = ?
                """,
                (user_id, entry_date),
            )
            row = cursor.fetchone()
            if row:
                return DiaryEntry.from_row(row)
            return None
        finally:
            conn.close()

    def get_or_create_entry(self, user_id: int, entry_date: str) -> DiaryEntry:
        """
        Obtém a anotação existente ou retorna um novo objeto DiaryEntry não salvo.
        """
        existing = self.get_entry_by_date(user_id, entry_date)
        if existing:
            return existing

        now = get_current_timestamp()
        return DiaryEntry(
            id=None,
            user_id=user_id,
            entry_date=entry_date,
            content="",
            content_normalized="",
            created_at=now,
            updated_at=now,
        )

    def save_entry(self, user_id: int, entry_date: str, content: str) -> DiaryEntry:
        """
        Salva ou atualiza a anotação diária no banco de dados.
        Atualiza o texto normalizado e os timestamps de alteração.
        Garante que nunca haja duplicidade de anotações para o mesmo usuário e data.
        """
        if not is_valid_iso_date(entry_date):
            raise ValueError(f"Data inválida no formato ISO: {entry_date}")

        now = get_current_timestamp()
        norm_content = normalize_text(content)

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO diaries (user_id, entry_date, content, content_normalized, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, entry_date) DO UPDATE SET
                    content = excluded.content,
                    content_normalized = excluded.content_normalized,
                    updated_at = excluded.updated_at
                """,
                (user_id, entry_date, content, norm_content, now, now),
            )

        saved = self.get_entry_by_date(user_id, entry_date)
        if not saved:
            raise RuntimeError("Falha ao recuperar a anotação após salvamento.")
        return saved

    def get_dates_with_notes(self, user_id: int, year: int, month: int) -> Set[str]:
        """
        Retorna o conjunto de datas (formato 'YYYY-MM-DD') que possuem anotações não vazias
        para o usuário no ano e mês especificados.
        """
        month_prefix = f"{year:04d}-{month:02d}-%"
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT entry_date
                FROM diaries
                WHERE user_id = ? AND entry_date LIKE ? AND TRIM(content) != ''
                """,
                (user_id, month_prefix),
            )
            return {row["entry_date"] for row in cursor.fetchall()}
        finally:
            conn.close()

    def list_entries_by_month(self, user_id: int, year: int, month: int) -> List[DiaryEntry]:
        """
        Lista todas as anotações do mês em ordem cronológica decrescente.
        """
        month_prefix = f"{year:04d}-{month:02d}-%"
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT d.*, u.full_name, u.username
                FROM diaries d
                JOIN users u ON d.user_id = u.id
                WHERE d.user_id = ? AND d.entry_date LIKE ? AND TRIM(d.content) != ''
                ORDER BY d.entry_date DESC
                """,
                (user_id, month_prefix),
            )
            return [DiaryEntry.from_row(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_adjacent_dates(self, user_id: int, current_date: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Retorna as datas mais próximas com anotações antes e depois da data fornecida.
        (data_anterior, data_proxima)
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            # Anterior
            cursor.execute(
                """
                SELECT entry_date
                FROM diaries
                WHERE user_id = ? AND entry_date < ? AND TRIM(content) != ''
                ORDER BY entry_date DESC LIMIT 1
                """,
                (user_id, current_date),
            )
            prev_row = cursor.fetchone()
            prev_date = prev_row["entry_date"] if prev_row else None

            # Próxima
            cursor.execute(
                """
                SELECT entry_date
                FROM diaries
                WHERE user_id = ? AND entry_date > ? AND TRIM(content) != ''
                ORDER BY entry_date ASC LIMIT 1
                """,
                (user_id, current_date),
            )
            next_row = cursor.fetchone()
            next_date = next_row["entry_date"] if next_row else None

            return prev_date, next_date
        finally:
            conn.close()

    def delete_entry(self, user_id: int, entry_date: str) -> bool:
        """Exclui a anotação para a data especificada."""
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM diaries WHERE user_id = ? AND entry_date = ?", (user_id, entry_date))
            return cursor.rowcount > 0
