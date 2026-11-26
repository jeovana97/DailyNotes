"""
Serviço dedicado ao Histórico de Andamento de Tarefas (tabela historico_tarefas).
Garante preservação cronológica de todas as observações e mudanças de status sem
nunca sobrescrever registros anteriores.
"""

import sqlite3
from typing import List, Optional, Tuple
import config
from database.connection import get_connection
from models.task import TaskHistoryEntry, normalize_status
from utils.date_utils import get_current_timestamp
from utils.text_utils import normalize_text


class TaskHistoryService:
    """Gerencia a persistência e consulta do histórico cronológico das tarefas."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DB_PATH

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> TaskHistoryEntry:
        return TaskHistoryEntry(
            id=row["id"],
            task_id=row["task_id"],
            status_at_time=row["status_at_time"],
            note=row["note"],
            created_at=row["created_at"],
        )

    def add_entry(
        self,
        task_id: int,
        note: str,
        status_at_time: str = "pendente",
        created_at: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
        update_task_timestamp: bool = True,
    ) -> Tuple[Optional[TaskHistoryEntry], str]:
        """
        Registra uma nova atualização/observação no histórico da tarefa.
        Nunca sobrescreve nem apaga registros anteriores.
        """
        clean_note = (note or "").strip()
        if not clean_note:
            return None, "Informe o texto da atualização de andamento."

        norm_status = normalize_status(status_at_time)
        ts = (created_at or "").strip() or get_current_timestamp()
        note_norm = normalize_text(clean_note)

        owns_conn = conn is None
        active_conn = conn or get_connection(self.db_path)
        try:
            if owns_conn:
                with active_conn:
                    entry_id = self._insert_entry(
                        active_conn, task_id, norm_status, clean_note, note_norm, ts, update_task_timestamp
                    )
            else:
                entry_id = self._insert_entry(
                    active_conn, task_id, norm_status, clean_note, note_norm, ts, update_task_timestamp
                )

            return (
                TaskHistoryEntry(
                    id=entry_id,
                    task_id=task_id,
                    status_at_time=norm_status,
                    note=clean_note,
                    created_at=ts,
                ),
                "Atualização registrada no histórico.",
            )
        except Exception as exc:
            return None, f"Erro ao registrar histórico da tarefa: {exc}"
        finally:
            if owns_conn:
                active_conn.close()

    @staticmethod
    def _insert_entry(
        conn: sqlite3.Connection,
        task_id: int,
        status_at_time: str,
        note: str,
        note_norm: str,
        ts: str,
        update_task_timestamp: bool,
    ) -> int:
        cur = conn.execute(
            """
            INSERT INTO historico_tarefas (
                task_id, status_at_time, note, note_normalized, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, status_at_time, note, note_norm, ts),
        )
        if update_task_timestamp:
            conn.execute(
                "UPDATE tarefas SET updated_at = ? WHERE id = ?",
                (ts, task_id),
            )
        return cur.lastrowid

    def list_history(self, task_id: int, descending: bool = False) -> List[TaskHistoryEntry]:
        """Retorna todas as atualizações de uma tarefa ordenadas cronologicamente."""
        order_sql = "DESC" if descending else "ASC"
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                f"""
                SELECT * FROM historico_tarefas
                WHERE task_id = ?
                ORDER BY created_at {order_sql}, id {order_sql}
                """,
                (task_id,),
            ).fetchall()
            return [self._row_to_entry(r) for r in rows]
        finally:
            conn.close()

    def get_latest_entry(self, task_id: int) -> Optional[TaskHistoryEntry]:
        """Retorna a atualização mais recente de uma tarefa."""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT * FROM historico_tarefas
                WHERE task_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
            return self._row_to_entry(row) if row else None
        finally:
            conn.close()
