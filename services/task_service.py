"""
Serviço principal do Gerenciador de Tarefas (tabela tarefas).
Orquestra CRUD de tarefas, controle de status (com registro automático de conclusão
e reabertura), pesquisa por título/descrição/histórico, filtros, ordenação,
indicadores de produtividade e integração com histórico e lembretes.
"""

import datetime
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import config
from database.connection import get_connection
from models.task import (
    PRIORITY_ORDER,
    STATUS_LABELS,
    Task,
    TaskHistoryEntry,
    normalize_priority,
    normalize_status,
)
from services.task_history_service import TaskHistoryService
from services.task_reminder_service import TaskReminderService
from utils.date_utils import get_current_timestamp
from utils.text_utils import normalize_text


class TaskService:
    """Regras de negócio do Gerenciador de Tarefas."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DB_PATH
        self.history_service = TaskHistoryService(db_path=self.db_path)
        self.reminder_service = TaskReminderService(db_path=self.db_path)

    @staticmethod
    def _validate_optional_date(date_iso: str, label: str) -> Tuple[bool, str]:
        raw = (date_iso or "").strip()
        if not raw:
            return True, ""
        try:
            datetime.datetime.strptime(raw, "%Y-%m-%d")
            return True, raw
        except ValueError:
            return False, f"{label} inválida. Use o formato DD/MM/AAAA."

    @staticmethod
    def _validate_optional_time(time_str: str) -> Tuple[bool, str]:
        raw = (time_str or "").strip()
        if not raw:
            return True, ""
        parts = raw.split(":")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            return False, "Horário inválido. Use o formato HH:MM (ex: 14:30)."
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return False, "Horário inválido. A hora deve estar entre 00 e 23 e os minutos entre 00 e 59."
        return True, f"{h:02d}:{m:02d}"

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        keys = set(row.keys())
        return Task(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            description=row["description"] or "",
            start_date=row["start_date"] or "",
            due_date=row["due_date"] or "",
            due_time=row["due_time"] or "",
            priority=normalize_priority(row["priority"]),
            status=normalize_status(row["status"]),
            category=row["category"] or "",
            reminder_enabled=bool(row["reminder_enabled"]),
            completed_at=row["completed_at"],
            legacy_schedule_id=row["legacy_schedule_id"] if "legacy_schedule_id" in keys else None,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            last_update_note=(row["last_update_note"] or "") if "last_update_note" in keys else "",
            last_update_at=(row["last_update_at"] or "") if "last_update_at" in keys else "",
            history_count=int(row["history_count"] or 0) if "history_count" in keys else 0,
            active_reminders_count=int(row["active_reminders_count"] or 0) if "active_reminders_count" in keys else 0,
        )

    def create_task(
        self,
        user_id: int,
        title: str,
        description: str = "",
        start_date: str = "",
        due_date: str = "",
        due_time: str = "",
        priority: str = "media",
        status: str = "pendente",
        category: str = "",
        reminder_enabled: bool = False,
        reminders: Optional[List[Dict[str, Any]]] = None,
        now: Optional[datetime.datetime] = None,
    ) -> Tuple[Optional[Task], str]:
        """Cria uma nova tarefa, grava registro inicial no histórico e configura lembretes."""
        clean_title = (title or "").strip()
        if not clean_title:
            return None, "Informe um título para a tarefa."

        ok_sd, norm_start = self._validate_optional_date(start_date, "Data de início")
        if not ok_sd:
            return None, norm_start

        ok_dd, norm_due = self._validate_optional_date(due_date, "Data prevista")
        if not ok_dd:
            return None, norm_due

        ok_tm, norm_time = self._validate_optional_time(due_time)
        if not ok_tm:
            return None, norm_time

        ref_dt = now or datetime.datetime.now()
        now_ts = ref_dt.strftime("%Y-%m-%d %H:%M:%S")
        if not norm_start:
            norm_start = ref_dt.strftime("%Y-%m-%d")

        norm_priority = normalize_priority(priority)
        norm_status = normalize_status(status)
        clean_desc = (description or "").strip()
        clean_cat = (category or "").strip()
        completed_at = now_ts if norm_status == "concluida" else None

        # Se reminder_enabled=True mas nenhum lembrete explícito foi passado, cria um padrão útil
        effective_reminders = reminders
        if reminder_enabled and effective_reminders is None and norm_due:
            effective_reminders = [
                {
                    "reminder_type": "custom",
                    "remind_date": norm_due,
                    "remind_time": norm_time or "09:00",
                    "repeat_interval": "none",
                    "is_active": True,
                }
            ]
        elif not reminder_enabled and effective_reminders is None:
            effective_reminders = []

        has_active_reminder = bool(reminder_enabled and effective_reminders)

        conn = get_connection(self.db_path)
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO tarefas (
                        user_id, title, title_normalized, description, description_normalized,
                        start_date, due_date, due_time, priority, status,
                        category, category_normalized, reminder_enabled,
                        completed_at, legacy_schedule_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        user_id,
                        clean_title,
                        normalize_text(clean_title),
                        clean_desc,
                        normalize_text(clean_desc),
                        norm_start,
                        norm_due,
                        norm_time,
                        norm_priority,
                        norm_status,
                        clean_cat,
                        normalize_text(clean_cat),
                        1 if has_active_reminder else 0,
                        completed_at,
                        now_ts,
                        now_ts,
                    ),
                )
                task_id = cur.lastrowid

                # Registro automático inicial no histórico
                self.history_service.add_entry(
                    task_id=task_id,
                    note="Tarefa cadastrada.",
                    status_at_time=norm_status,
                    created_at=now_ts,
                    conn=conn,
                    update_task_timestamp=False,
                )

                # Configura lembretes vinculados
                if effective_reminders is not None:
                    ok_rem, rem_msg = self.reminder_service.sync_reminders(
                        task_id=task_id,
                        reminder_configs=effective_reminders if reminder_enabled else [],
                        task_status=norm_status,
                        now_ts=now_ts,
                        conn=conn,
                    )
                    if not ok_rem:
                        raise ValueError(rem_msg)

            created_task = self.get_task_by_id(task_id, user_id, include_details=True)
            return created_task, "Tarefa cadastrada com sucesso!"
        except ValueError as ve:
            return None, str(ve)
        except Exception as exc:
            return None, f"Erro ao cadastrar tarefa: {exc}"
        finally:
            conn.close()

    def update_task(
        self,
        task_id: int,
        user_id: int,
        title: str,
        description: str = "",
        start_date: str = "",
        due_date: str = "",
        due_time: str = "",
        priority: str = "media",
        status: str = "pendente",
        category: str = "",
        reminder_enabled: bool = False,
        reminders: Optional[List[Dict[str, Any]]] = None,
        now: Optional[datetime.datetime] = None,
    ) -> Tuple[bool, str]:
        """
        Atualiza os dados principais de uma tarefa preservando 100% do histórico
        anterior e registrando automaticamente mudanças de status.
        """
        clean_title = (title or "").strip()
        if not clean_title:
            return False, "Informe um título para a tarefa."

        ok_sd, norm_start = self._validate_optional_date(start_date, "Data de início")
        if not ok_sd:
            return False, norm_start

        ok_dd, norm_due = self._validate_optional_date(due_date, "Data prevista")
        if not ok_dd:
            return False, norm_due

        ok_tm, norm_time = self._validate_optional_time(due_time)
        if not ok_tm:
            return False, norm_time

        ref_dt = now or datetime.datetime.now()
        now_ts = ref_dt.strftime("%Y-%m-%d %H:%M:%S")
        norm_priority = normalize_priority(priority)
        norm_status = normalize_status(status)
        clean_desc = (description or "").strip()
        clean_cat = (category or "").strip()

        conn = get_connection(self.db_path)
        try:
            existing = conn.execute(
                "SELECT * FROM tarefas WHERE id = ? AND user_id = ?",
                (task_id, user_id),
            ).fetchone()
            if not existing:
                return False, "Tarefa não encontrada."

            old_status = normalize_status(existing["status"])
            completed_at = existing["completed_at"]

            if norm_status == "concluida" and old_status != "concluida":
                completed_at = now_ts
            elif norm_status != "concluida" and old_status == "concluida":
                completed_at = None

            if not norm_start:
                norm_start = existing["start_date"] or existing["created_at"][:10]

            rem_flag = 1 if reminder_enabled else 0
            if reminders is not None and not reminders:
                rem_flag = 0

            with conn:
                conn.execute(
                    """
                    UPDATE tarefas
                    SET title = ?, title_normalized = ?,
                        description = ?, description_normalized = ?,
                        start_date = ?, due_date = ?, due_time = ?,
                        priority = ?, status = ?,
                        category = ?, category_normalized = ?,
                        reminder_enabled = ?, completed_at = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        clean_title,
                        normalize_text(clean_title),
                        clean_desc,
                        normalize_text(clean_desc),
                        norm_start,
                        norm_due,
                        norm_time,
                        norm_priority,
                        norm_status,
                        clean_cat,
                        normalize_text(clean_cat),
                        rem_flag,
                        completed_at,
                        now_ts,
                        task_id,
                        user_id,
                    ),
                )

                # Registra no histórico caso o status tenha sido alterado durante a edição
                if norm_status != old_status:
                    if norm_status == "concluida":
                        hist_txt = "Tarefa marcada como concluída."
                    elif old_status in ("concluida", "cancelada") and norm_status in ("pendente", "em_andamento"):
                        hist_txt = f"Tarefa reaberta com status {STATUS_LABELS[norm_status]}."
                    else:
                        hist_txt = f"Status alterado de {STATUS_LABELS[old_status]} para {STATUS_LABELS[norm_status]}."

                    self.history_service.add_entry(
                        task_id=task_id,
                        note=hist_txt,
                        status_at_time=norm_status,
                        created_at=now_ts,
                        conn=conn,
                        update_task_timestamp=False,
                    )

                # Sincroniza lembretes sem perder controle de envios anteriores
                if reminders is not None:
                    ok_rem, rem_msg = self.reminder_service.sync_reminders(
                        task_id=task_id,
                        reminder_configs=reminders if reminder_enabled else [],
                        task_status=norm_status,
                        now_ts=now_ts,
                        conn=conn,
                    )
                    if not ok_rem:
                        raise ValueError(rem_msg)
                else:
                    self.reminder_service.set_task_reminders_active(
                        task_id=task_id,
                        active=bool(reminder_enabled and norm_status in ("pendente", "em_andamento")),
                        now_ts=now_ts,
                        conn=conn,
                    )

            return True, "Tarefa atualizada com sucesso!"
        except ValueError as ve:
            return False, str(ve)
        except Exception as exc:
            return False, f"Erro ao atualizar tarefa: {exc}"
        finally:
            conn.close()

    def change_status(
        self,
        task_id: int,
        user_id: int,
        new_status: str,
        note: str = "",
        now: Optional[datetime.datetime] = None,
    ) -> Tuple[bool, str]:
        """
        Altera o status de uma tarefa diretamente (listagem ou tela de detalhes):
        - Ao concluir, registra automaticamente data e hora em `completed_at`.
        - Ao reabrir, limpa `completed_at` e mantém todo o histórico.
        - Sempre acrescenta uma entrada cronológica em `historico_tarefas`.
        """
        norm_status = normalize_status(new_status)
        ref_dt = now or datetime.datetime.now()
        now_ts = ref_dt.strftime("%Y-%m-%d %H:%M:%S")

        conn = get_connection(self.db_path)
        try:
            existing = conn.execute(
                "SELECT * FROM tarefas WHERE id = ? AND user_id = ?",
                (task_id, user_id),
            ).fetchone()
            if not existing:
                return False, "Tarefa não encontrada."

            old_status = normalize_status(existing["status"])
            if old_status == norm_status and not (note or "").strip():
                return True, f"A tarefa já está com status {STATUS_LABELS[norm_status]}."

            completed_at = existing["completed_at"]
            if norm_status == "concluida":
                completed_at = now_ts
            elif old_status == "concluida":
                completed_at = None

            custom_note = (note or "").strip()
            if custom_note:
                hist_note = custom_note
            elif norm_status == "concluida":
                hist_note = "Tarefa concluída."
            elif old_status in ("concluida", "cancelada") and norm_status in ("pendente", "em_andamento"):
                hist_note = f"Tarefa reaberta ({STATUS_LABELS[norm_status]})."
            elif norm_status == "cancelada":
                hist_note = "Tarefa cancelada."
            else:
                hist_note = f"Status alterado de {STATUS_LABELS[old_status]} para {STATUS_LABELS[norm_status]}."

            with conn:
                conn.execute(
                    """
                    UPDATE tarefas
                    SET status = ?, completed_at = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (norm_status, completed_at, now_ts, task_id, user_id),
                )

                self.history_service.add_entry(
                    task_id=task_id,
                    note=hist_note,
                    status_at_time=norm_status,
                    created_at=now_ts,
                    conn=conn,
                    update_task_timestamp=False,
                )

                self.reminder_service.set_task_reminders_active(
                    task_id=task_id,
                    active=bool(existing["reminder_enabled"] and norm_status in ("pendente", "em_andamento")),
                    now_ts=now_ts,
                    conn=conn,
                )

            return True, f"Status atualizado para {STATUS_LABELS[norm_status]}."
        except Exception as exc:
            return False, f"Erro ao alterar status da tarefa: {exc}"
        finally:
            conn.close()

    def complete_task(
        self,
        task_id: int,
        user_id: int,
        note: str = "",
        now: Optional[datetime.datetime] = None,
    ) -> Tuple[bool, str]:
        return self.change_status(task_id, user_id, "concluida", note=note, now=now)

    def reopen_task(
        self,
        task_id: int,
        user_id: int,
        target_status: str = "pendente",
        note: str = "",
        now: Optional[datetime.datetime] = None,
    ) -> Tuple[bool, str]:
        dest = normalize_status(target_status)
        if dest not in ("pendente", "em_andamento"):
            dest = "pendente"
        return self.change_status(task_id, user_id, dest, note=note, now=now)

    def add_progress_update(
        self,
        task_id: int,
        user_id: int,
        note: str,
        new_status: Optional[str] = None,
        now: Optional[datetime.datetime] = None,
    ) -> Tuple[Optional[TaskHistoryEntry], str]:
        """
        Registra uma nova atualização de andamento dentro da tarefa sem sobrescrever
        as anteriores. Opcionalmente altera o status da tarefa no mesmo passo.
        """
        clean_note = (note or "").strip()
        if not clean_note:
            return None, "Digite uma informação ou observação de andamento."

        ref_dt = now or datetime.datetime.now()
        now_ts = ref_dt.strftime("%Y-%m-%d %H:%M:%S")

        conn = get_connection(self.db_path)
        try:
            existing = conn.execute(
                "SELECT * FROM tarefas WHERE id = ? AND user_id = ?",
                (task_id, user_id),
            ).fetchone()
            if not existing:
                return None, "Tarefa não encontrada."

            old_status = normalize_status(existing["status"])
            effective_status = normalize_status(new_status) if new_status else old_status
            completed_at = existing["completed_at"]

            if effective_status != old_status:
                if effective_status == "concluida":
                    completed_at = now_ts
                elif old_status == "concluida":
                    completed_at = None

            with conn:
                conn.execute(
                    """
                    UPDATE tarefas
                    SET status = ?, completed_at = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (effective_status, completed_at, now_ts, task_id, user_id),
                )

                entry, msg = self.history_service.add_entry(
                    task_id=task_id,
                    note=clean_note,
                    status_at_time=effective_status,
                    created_at=now_ts,
                    conn=conn,
                    update_task_timestamp=False,
                )

                if effective_status != old_status:
                    self.reminder_service.set_task_reminders_active(
                        task_id=task_id,
                        active=bool(existing["reminder_enabled"] and effective_status in ("pendente", "em_andamento")),
                        now_ts=now_ts,
                        conn=conn,
                    )

            return entry, msg
        except Exception as exc:
            return None, f"Erro ao adicionar atualização: {exc}"
        finally:
            conn.close()

    def delete_task(self, task_id: int, user_id: int) -> Tuple[bool, str]:
        """Remove a tarefa e seus registros vinculados (histórico e lembretes via CASCADE)."""
        conn = get_connection(self.db_path)
        try:
            with conn:
                cur = conn.execute(
                    "DELETE FROM tarefas WHERE id = ? AND user_id = ?",
                    (task_id, user_id),
                )
            if cur.rowcount == 0:
                return False, "Tarefa não encontrada."
            return True, "Tarefa excluída com sucesso."
        except Exception as exc:
            return False, f"Erro ao excluir tarefa: {exc}"
        finally:
            conn.close()

    def get_task_by_id(
        self,
        task_id: int,
        user_id: int,
        include_details: bool = True,
    ) -> Optional[Task]:
        """Recupera uma tarefa específica, opcionalmente já com histórico e lembretes."""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT
                    t.*,
                    (
                        SELECT h.note FROM historico_tarefas h
                        WHERE h.task_id = t.id
                        ORDER BY h.created_at DESC, h.id DESC LIMIT 1
                    ) AS last_update_note,
                    (
                        SELECT h.created_at FROM historico_tarefas h
                        WHERE h.task_id = t.id
                        ORDER BY h.created_at DESC, h.id DESC LIMIT 1
                    ) AS last_update_at,
                    (
                        SELECT COUNT(*) FROM historico_tarefas h WHERE h.task_id = t.id
                    ) AS history_count,
                    (
                        SELECT COUNT(*) FROM lembretes_tarefas r
                        WHERE r.task_id = t.id AND r.is_active = 1
                    ) AS active_reminders_count
                FROM tarefas t
                WHERE t.id = ? AND t.user_id = ?
                """,
                (task_id, user_id),
            ).fetchone()
            if not row:
                return None
            task = self._row_to_task(row)
        finally:
            conn.close()

        if include_details:
            task.history = self.history_service.list_history(task.id, descending=False)
            task.reminders = self.reminder_service.list_reminders(task.id)
        return task

    def get_task_by_legacy_schedule_id(self, schedule_id: int, user_id: int) -> Optional[Task]:
        """Localiza uma tarefa migrada a partir do ID legado da tabela schedules."""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT id FROM tarefas WHERE legacy_schedule_id = ? AND user_id = ?",
                (schedule_id, user_id),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return self.get_task_by_id(row["id"], user_id, include_details=True)

    def list_tasks(
        self,
        user_id: int,
        tab: str = "todas",
        search_query: str = "",
        status_filter: Optional[str] = None,
        priority_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        date_from: str = "",
        date_to: str = "",
        sort_by: str = "due_date",
        sort_desc: bool = False,
        now: Optional[datetime.datetime] = None,
    ) -> List[Task]:
        """
        Lista tarefas com suporte completo a:
        - Abas: todas, pendentes, em_andamento, concluidas, canceladas, atrasadas, hoje, proximos_dias
        - Pesquisa sem acento em título, descrição, categoria e histórico de andamento
        - Filtros por período (date_from..date_to), status, prioridade e categoria
        - Ordenação por due_date, priority, created_at ou updated_at
        """
        ref_dt = now or datetime.datetime.now()
        today_iso = ref_dt.strftime("%Y-%m-%d")
        now_hm = ref_dt.strftime("%H:%M")

        where_clauses = ["t.user_id = ?"]
        params: List[Any] = [user_id]

        tab_key = (tab or "todas").strip().lower()
        if tab_key == "pendentes":
            where_clauses.append("t.status = 'pendente'")
        elif tab_key == "em_andamento":
            where_clauses.append("t.status = 'em_andamento'")
        elif tab_key == "concluidas":
            where_clauses.append("t.status = 'concluida'")
        elif tab_key == "canceladas":
            where_clauses.append("t.status = 'cancelada'")
        elif tab_key == "hoje":
            where_clauses.append("t.status IN ('pendente', 'em_andamento') AND t.due_date = ?")
            params.append(today_iso)
        elif tab_key == "proximos_dias":
            where_clauses.append("t.status IN ('pendente', 'em_andamento') AND t.due_date != '' AND t.due_date > ?")
            params.append(today_iso)
        elif tab_key == "atrasadas":
            where_clauses.append(
                """
                t.status IN ('pendente', 'em_andamento')
                AND t.due_date != ''
                AND (
                    t.due_date < ?
                    OR (t.due_date = ? AND t.due_time != '' AND t.due_time < ?)
                )
                """
            )
            params.extend([today_iso, today_iso, now_hm])

        if status_filter and status_filter not in ("todos", "todas", ""):
            where_clauses.append("t.status = ?")
            params.append(normalize_status(status_filter))

        if priority_filter and priority_filter not in ("todas", "todos", ""):
            where_clauses.append("t.priority = ?")
            params.append(normalize_priority(priority_filter))

        if category_filter and category_filter not in ("todas", ""):
            where_clauses.append("t.category_normalized = ?")
            params.append(normalize_text(category_filter))

        if date_from and date_from.strip():
            where_clauses.append("t.due_date != '' AND t.due_date >= ?")
            params.append(date_from.strip())

        if date_to and date_to.strip():
            where_clauses.append("t.due_date != '' AND t.due_date <= ?")
            params.append(date_to.strip())

        if search_query and search_query.strip():
            q_norm = normalize_text(search_query.strip())
            like_pat = f"%{q_norm}%"
            where_clauses.append(
                """
                (
                    t.title_normalized LIKE ?
                    OR t.description_normalized LIKE ?
                    OR t.category_normalized LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM historico_tarefas h
                        WHERE h.task_id = t.id AND h.note_normalized LIKE ?
                    )
                )
                """
            )
            params.extend([like_pat, like_pat, like_pat, like_pat])

        sql = f"""
            SELECT
                t.*,
                (
                    SELECT h.note FROM historico_tarefas h
                    WHERE h.task_id = t.id
                    ORDER BY h.created_at DESC, h.id DESC LIMIT 1
                ) AS last_update_note,
                (
                    SELECT h.created_at FROM historico_tarefas h
                    WHERE h.task_id = t.id
                    ORDER BY h.created_at DESC, h.id DESC LIMIT 1
                ) AS last_update_at,
                (
                    SELECT COUNT(*) FROM historico_tarefas h WHERE h.task_id = t.id
                ) AS history_count,
                (
                    SELECT COUNT(*) FROM lembretes_tarefas r
                    WHERE r.task_id = t.id AND r.is_active = 1
                ) AS active_reminders_count
            FROM tarefas t
            WHERE {' AND '.join(where_clauses)}
        """

        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(sql, params).fetchall()
            tasks = [self._row_to_task(r) for r in rows]
        finally:
            conn.close()

        return self._sort_tasks(tasks, sort_by=sort_by, sort_desc=sort_desc)

    @staticmethod
    def _sort_tasks(tasks: List[Task], sort_by: str = "due_date", sort_desc: bool = False) -> List[Task]:
        key_name = (sort_by or "due_date").strip().lower()

        if key_name == "priority":
            # Por padrão (sort_desc=False), maior prioridade (Urgente) aparece primeiro
            if not sort_desc:
                return sorted(
                    tasks,
                    key=lambda t: (
                        -PRIORITY_ORDER.get(t.priority, 2),
                        1 if not t.due_date else 0,
                        t.due_date or "9999-99-99",
                        t.due_time or "99:99",
                        -(t.id or 0),
                    ),
                )
            return sorted(
                tasks,
                key=lambda t: (
                    PRIORITY_ORDER.get(t.priority, 2),
                    1 if not t.due_date else 0,
                    t.due_date or "9999-99-99",
                    t.due_time or "99:99",
                    t.id or 0,
                ),
            )

        if key_name == "created_at":
            return sorted(
                tasks,
                key=lambda t: (t.created_at or "", t.id or 0),
                reverse=sort_desc,
            )

        if key_name == "updated_at":
            return sorted(
                tasks,
                key=lambda t: (t.last_update_at or t.updated_at or t.created_at or "", t.id or 0),
                reverse=sort_desc,
            )

        # Padrão: data prevista ("due_date"), sempre mantendo tarefas sem prazo no final
        with_due = [t for t in tasks if t.due_date]
        without_due = [t for t in tasks if not t.due_date]
        with_due.sort(
            key=lambda t: (
                t.due_date,
                t.due_time or ("99:99" if not sort_desc else "00:00"),
                -PRIORITY_ORDER.get(t.priority, 2) if not sort_desc else PRIORITY_ORDER.get(t.priority, 2),
                t.id or 0,
            ),
            reverse=sort_desc,
        )
        without_due.sort(key=lambda t: (-PRIORITY_ORDER.get(t.priority, 2), t.id or 0))
        return with_due + without_due

    def get_summary_counts(
        self,
        user_id: int,
        now: Optional[datetime.datetime] = None,
    ) -> Dict[str, int]:
        """Retorna indicadores de produtividade para os cards e abas da tela principal."""
        ref_dt = now or datetime.datetime.now()
        today_iso = ref_dt.strftime("%Y-%m-%d")
        now_hm = ref_dt.strftime("%H:%M")

        counts = {
            "total": 0,
            "pendentes": 0,
            "em_andamento": 0,
            "concluidas": 0,
            "canceladas": 0,
            "atrasadas": 0,
            "hoje": 0,
            "proximos_dias": 0,
        }

        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT status, due_date, due_time FROM tarefas WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            for r in rows:
                counts["total"] += 1
                st = normalize_status(r["status"])
                d_date = r["due_date"] or ""
                d_time = r["due_time"] or ""

                if st == "pendente":
                    counts["pendentes"] += 1
                elif st == "em_andamento":
                    counts["em_andamento"] += 1
                elif st == "concluida":
                    counts["concluidas"] += 1
                elif st == "cancelada":
                    counts["canceladas"] += 1

                if st in ("pendente", "em_andamento") and d_date:
                    if d_date < today_iso or (d_date == today_iso and d_time and d_time < now_hm):
                        counts["atrasadas"] += 1
                    if d_date == today_iso:
                        counts["hoje"] += 1
                    elif d_date > today_iso:
                        counts["proximos_dias"] += 1
        finally:
            conn.close()
        return counts

    def list_categories(self, user_id: int) -> List[str]:
        """Retorna as categorias distintas já utilizadas pelo usuário."""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT category FROM tarefas
                WHERE user_id = ? AND category != ''
                ORDER BY category COLLATE NOCASE ASC
                """,
                (user_id,),
            ).fetchall()
            return [r["category"] for r in rows if r["category"]]
        finally:
            conn.close()
