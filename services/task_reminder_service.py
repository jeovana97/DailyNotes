"""
Serviço dedicado a Lembretes e Notificações de Tarefas (tabela lembretes_tarefas).
Suporta lembretes em data/horário personalizados, aviso no dia do vencimento,
aviso antecipado, lembrete de tarefa atrasada, adiamento (snooze) e controle
rigoroso contra notificações repetidas indevidamente.
"""

import calendar
import datetime
import logging
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Tuple

import config
from database.connection import get_connection
from models.task import (
    REMINDER_TYPES,
    REPEAT_INTERVALS,
    Task,
    TaskReminder,
    format_advance_label,
    format_iso_date_br,
)
from utils.date_utils import get_current_timestamp
from utils.notification_utils import send_windows_notification

logger = logging.getLogger(__name__)


class TaskReminderService:
    """Gerencia lembretes vinculados às tarefas e o disparo de notificações."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DB_PATH

    @staticmethod
    def _row_to_reminder(row: sqlite3.Row) -> TaskReminder:
        return TaskReminder(
            id=row["id"],
            task_id=row["task_id"],
            reminder_type=row["reminder_type"],
            remind_date=row["remind_date"] or "",
            remind_time=row["remind_time"] or "09:00",
            advance_minutes=int(row["advance_minutes"] or 0),
            repeat_interval=row["repeat_interval"] or "none",
            is_active=bool(row["is_active"]),
            is_sent=bool(row["is_sent"]),
            last_notified_date=row["last_notified_date"],
            notified_at=row["notified_at"],
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    @staticmethod
    def validate_time(time_str: str) -> Tuple[bool, str]:
        raw = (time_str or "").strip()
        if not raw:
            return True, "09:00"
        parts = raw.split(":")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            return False, "Horário de lembrete inválido. Use HH:MM (ex: 09:00)."
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return False, "Horário de lembrete inválido. Hora entre 00-23 e minuto entre 00-59."
        return True, f"{h:02d}:{m:02d}"

    @staticmethod
    def validate_date(date_iso: str) -> Tuple[bool, str]:
        raw = (date_iso or "").strip()
        if not raw:
            return False, "Informe a data do lembrete."
        try:
            datetime.datetime.strptime(raw, "%Y-%m-%d")
            return True, raw
        except ValueError:
            return False, "Data do lembrete inválida. Use o formato DD/MM/AAAA."

    @staticmethod
    def _advance_repeat_date(date_iso: str, repeat_interval: str) -> str:
        dt = datetime.datetime.strptime(date_iso, "%Y-%m-%d").date()
        if repeat_interval == "daily":
            next_dt = dt + datetime.timedelta(days=1)
        elif repeat_interval == "weekly":
            next_dt = dt + datetime.timedelta(days=7)
        elif repeat_interval == "monthly":
            month = dt.month + 1
            year = dt.year
            if month > 12:
                month = 1
                year += 1
            max_day = calendar.monthrange(year, month)[1]
            next_dt = datetime.date(year, month, min(dt.day, max_day))
        else:
            next_dt = dt
        return next_dt.strftime("%Y-%m-%d")

    @staticmethod
    def _signature(
        reminder_type: str,
        remind_date: str,
        remind_time: str,
        advance_minutes: int,
        repeat_interval: str,
    ) -> Tuple[str, str, str, int, str]:
        return (
            reminder_type,
            remind_date or "",
            remind_time or "09:00",
            int(advance_minutes or 0),
            repeat_interval or "none",
        )

    def sync_reminders(
        self,
        task_id: int,
        reminder_configs: Optional[List[Dict[str, Any]]],
        task_status: str = "pendente",
        now_ts: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Tuple[bool, str]:
        """
        Sincroniza a lista de lembretes de uma tarefa preservando o estado
        de envio (`is_sent`, `notified_at`, `last_notified_date`) dos lembretes
        inalterados para evitar notificações duplicadas após edições.
        """
        if reminder_configs is None:
            return True, "Lembretes mantidos."

        ts = now_ts or get_current_timestamp()
        task_is_open = task_status in ("pendente", "em_andamento")

        normalized_items: List[Dict[str, Any]] = []
        seen_sigs = set()
        for raw in reminder_configs:
            r_type = str(raw.get("reminder_type", "custom")).strip().lower()
            if r_type not in REMINDER_TYPES:
                return False, f"Tipo de lembrete inválido: {r_type}"

            r_date = str(raw.get("remind_date") or "").strip()
            ok_t, norm_time = self.validate_time(str(raw.get("remind_time") or "09:00"))
            if not ok_t:
                return False, norm_time

            if r_type == "custom":
                ok_d, norm_date = self.validate_date(r_date)
                if not ok_d:
                    return False, norm_date
                r_date = norm_date
            else:
                r_date = ""

            adv_min = max(0, int(raw.get("advance_minutes") or 0))
            if r_type == "advance" and adv_min <= 0:
                adv_min = 60

            rep = str(raw.get("repeat_interval") or "none").strip().lower()
            if rep not in REPEAT_INTERVALS:
                rep = "none"
            if r_type != "custom":
                rep = "none"

            sig = self._signature(r_type, r_date, norm_time, adv_min, rep)
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)

            normalized_items.append(
                {
                    "reminder_type": r_type,
                    "remind_date": r_date,
                    "remind_time": norm_time,
                    "advance_minutes": adv_min,
                    "repeat_interval": rep,
                    "is_active": 1 if (bool(raw.get("is_active", True)) and task_is_open) else 0,
                    "sig": sig,
                }
            )

        owns_conn = conn is None
        active_conn = conn or get_connection(self.db_path)
        try:
            def _apply(c: sqlite3.Connection) -> None:
                existing_rows = c.execute(
                    "SELECT * FROM lembretes_tarefas WHERE task_id = ?",
                    (task_id,),
                ).fetchall()
                existing_by_sig: Dict[Tuple, sqlite3.Row] = {}
                for er in existing_rows:
                    esig = self._signature(
                        er["reminder_type"],
                        er["remind_date"] or "",
                        er["remind_time"] or "09:00",
                        int(er["advance_minutes"] or 0),
                        er["repeat_interval"] or "none",
                    )
                    existing_by_sig[esig] = er

                keep_ids = set()
                for item in normalized_items:
                    matched = existing_by_sig.get(item["sig"])
                    if matched is not None:
                        keep_ids.add(matched["id"])
                        c.execute(
                            """
                            UPDATE lembretes_tarefas
                            SET is_active = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (item["is_active"], ts, matched["id"]),
                        )
                    else:
                        cur = c.execute(
                            """
                            INSERT INTO lembretes_tarefas (
                                task_id, reminder_type, remind_date, remind_time,
                                advance_minutes, repeat_interval, is_active, is_sent,
                                last_notified_date, notified_at, created_at, updated_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, ?, ?)
                            """,
                            (
                                task_id,
                                item["reminder_type"],
                                item["remind_date"],
                                item["remind_time"],
                                item["advance_minutes"],
                                item["repeat_interval"],
                                item["is_active"],
                                ts,
                                ts,
                            ),
                        )
                        keep_ids.add(cur.lastrowid)

                # Remove apenas lembretes que foram removidos pelo usuário
                for er in existing_rows:
                    if er["id"] not in keep_ids:
                        c.execute("DELETE FROM lembretes_tarefas WHERE id = ?", (er["id"],))

            if owns_conn:
                with active_conn:
                    _apply(active_conn)
            else:
                _apply(active_conn)

            return True, "Lembretes configurados com sucesso."
        except Exception as exc:
            return False, f"Erro ao configurar lembretes: {exc}"
        finally:
            if owns_conn:
                active_conn.close()

    def set_task_reminders_active(
        self,
        task_id: int,
        active: bool,
        now_ts: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Ativa ou desativa todos os lembretes vinculados a uma tarefa (ex.: concluir/reabrir)."""
        ts = now_ts or get_current_timestamp()
        owns_conn = conn is None
        active_conn = conn or get_connection(self.db_path)
        try:
            if owns_conn:
                with active_conn:
                    active_conn.execute(
                        "UPDATE lembretes_tarefas SET is_active = ?, updated_at = ? WHERE task_id = ?",
                        (1 if active else 0, ts, task_id),
                    )
            else:
                active_conn.execute(
                    "UPDATE lembretes_tarefas SET is_active = ?, updated_at = ? WHERE task_id = ?",
                    (1 if active else 0, ts, task_id),
                )
        finally:
            if owns_conn:
                active_conn.close()

    def list_reminders(self, task_id: int) -> List[TaskReminder]:
        """Lista todos os lembretes configurados para uma tarefa."""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT * FROM lembretes_tarefas
                WHERE task_id = ?
                ORDER BY
                    CASE reminder_type
                        WHEN 'custom' THEN 1
                        WHEN 'due_day' THEN 2
                        WHEN 'advance' THEN 3
                        WHEN 'overdue' THEN 4
                        ELSE 5
                    END,
                    remind_date ASC,
                    remind_time ASC,
                    id ASC
                """,
                (task_id,),
            ).fetchall()
            return [self._row_to_reminder(r) for r in rows]
        finally:
            conn.close()

    def snooze_task_reminder(
        self,
        task_id: int,
        minutes: int = 10,
        now: Optional[datetime.datetime] = None,
    ) -> Tuple[bool, str]:
        """Adia a notificação da tarefa por `minutes` minutos a partir de agora."""
        mins = max(1, int(minutes or 10))
        ref_dt = now or datetime.datetime.now()
        target_dt = ref_dt + datetime.timedelta(minutes=mins)
        new_date = target_dt.strftime("%Y-%m-%d")
        new_time = target_dt.strftime("%H:%M")
        ts = ref_dt.strftime("%Y-%m-%d %H:%M:%S")

        conn = get_connection(self.db_path)
        try:
            task_row = conn.execute(
                "SELECT id, status FROM tarefas WHERE id = ?",
                (task_id,),
            ).fetchone()
            if not task_row:
                return False, "Tarefa não encontrada."
            if task_row["status"] in ("concluida", "cancelada"):
                return False, "Não é possível adiar lembrete de tarefa concluída ou cancelada."

            with conn:
                existing_custom = conn.execute(
                    """
                    SELECT id FROM lembretes_tarefas
                    WHERE task_id = ? AND reminder_type = 'custom'
                    ORDER BY id ASC LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()

                if existing_custom:
                    conn.execute(
                        """
                        UPDATE lembretes_tarefas
                        SET remind_date = ?, remind_time = ?, is_active = 1,
                            is_sent = 0, notified_at = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        (new_date, new_time, ts, existing_custom["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO lembretes_tarefas (
                            task_id, reminder_type, remind_date, remind_time,
                            advance_minutes, repeat_interval, is_active, is_sent,
                            last_notified_date, notified_at, created_at, updated_at
                        )
                        VALUES (?, 'custom', ?, ?, 0, 'none', 1, 0, NULL, NULL, ?, ?)
                        """,
                        (task_id, new_date, new_time, ts, ts),
                    )
                conn.execute(
                    "UPDATE tarefas SET reminder_enabled = 1, updated_at = ? WHERE id = ?",
                    (ts, task_id),
                )

            return True, f"Lembrete adiado para {format_iso_date_br(new_date)} às {new_time}."
        except Exception as exc:
            return False, f"Erro ao adiar lembrete: {exc}"
        finally:
            conn.close()

    @staticmethod
    def _is_reminder_due(
        reminder: TaskReminder,
        task: Task,
        now_dt: datetime.datetime,
    ) -> Tuple[bool, str]:
        """
        Avalia se o lembrete atingiu o momento de disparo sem repetição indevida.
        Retorna (is_due, motivo_amigavel).
        """
        today_iso = now_dt.strftime("%Y-%m-%d")
        now_hm = now_dt.strftime("%H:%M")
        now_ts = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        r_type = reminder.reminder_type

        if r_type == "custom":
            if reminder.is_sent or not reminder.remind_date:
                return False, ""
            due_ts = f"{reminder.remind_date} {reminder.remind_time or '09:00'}:00"
            if due_ts <= now_ts:
                return True, f"Lembrete agendado para {format_iso_date_br(reminder.remind_date)} às {reminder.remind_time or '09:00'}"
            return False, ""

        if r_type == "due_day":
            if reminder.is_sent or not task.due_date:
                return False, ""
            target_time = reminder.remind_time or task.due_time or "09:00"
            due_ts = f"{task.due_date} {target_time}:00"
            if due_ts <= now_ts:
                return True, f"Vence hoje ({task.due_date_br})"
            return False, ""

        if r_type == "advance":
            if reminder.is_sent or not task.due_date:
                return False, ""
            base_time = task.due_time or reminder.remind_time or "09:00"
            try:
                base_dt = datetime.datetime.strptime(f"{task.due_date} {base_time}", "%Y-%m-%d %H:%M")
            except ValueError:
                return False, ""
            trigger_dt = base_dt - datetime.timedelta(minutes=max(1, reminder.advance_minutes or 60))
            if now_dt >= trigger_dt:
                adv_label = format_advance_label(reminder.advance_minutes)
                return True, f"Aviso antecipado ({adv_label}) — Prazo: {task.due_display}"
            return False, ""

        if r_type == "overdue":
            if not task.is_overdue(now_dt):
                return False, ""
            # Evita notificações repetidas no mesmo dia para a mesma tarefa atrasada
            if reminder.last_notified_date == today_iso:
                return False, ""
            target_time = reminder.remind_time or "09:00"
            if now_hm >= target_time:
                return True, f"Tarefa atrasada! Prazo era {task.due_display}"
            return False, ""

        return False, ""

    def check_and_notify_due_reminders(
        self,
        user_id: Optional[int] = None,
        now: Optional[datetime.datetime] = None,
        notify_callback: Optional[Callable[[Task, TaskReminder, str, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Verifica todos os lembretes ativos de tarefas abertas e dispara notificações
        do Windows vinculadas à tarefa correspondente, evitando envios duplicados.
        """
        now_dt = now or datetime.datetime.now()
        today_iso = now_dt.strftime("%Y-%m-%d")
        now_ts = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        conn = get_connection(self.db_path)
        dispatched: List[Dict[str, Any]] = []
        try:
            sql = """
                SELECT
                    r.id AS r_id, r.task_id AS r_task_id, r.reminder_type AS r_type,
                    r.remind_date AS r_date, r.remind_time AS r_time,
                    r.advance_minutes AS r_adv, r.repeat_interval AS r_repeat,
                    r.is_active AS r_active, r.is_sent AS r_sent,
                    r.last_notified_date AS r_last_date, r.notified_at AS r_notified_at,
                    r.created_at AS r_created_at, r.updated_at AS r_updated_at,
                    t.id AS t_id, t.user_id AS t_user_id, t.title AS t_title,
                    t.description AS t_description, t.start_date AS t_start_date,
                    t.due_date AS t_due_date, t.due_time AS t_due_time,
                    t.priority AS t_priority, t.status AS t_status,
                    t.category AS t_category, t.reminder_enabled AS t_reminder_enabled,
                    t.completed_at AS t_completed_at, t.legacy_schedule_id AS t_legacy_id,
                    t.created_at AS t_created_at, t.updated_at AS t_updated_at
                FROM lembretes_tarefas r
                INNER JOIN tarefas t ON t.id = r.task_id
                WHERE r.is_active = 1
                  AND t.reminder_enabled = 1
                  AND t.status IN ('pendente', 'em_andamento')
            """
            params: List[Any] = []
            if user_id is not None:
                sql += " AND t.user_id = ?"
                params.append(user_id)
            sql += " ORDER BY t.id ASC, r.id ASC"

            rows = conn.execute(sql, params).fetchall()
            if not rows:
                return []

            # Agrupa lembretes devidos por tarefa para evitar spam de múltiplas notificações simultâneas
            due_by_task: Dict[int, List[Tuple[Task, TaskReminder, str]]] = {}

            for row in rows:
                task = Task(
                    id=row["t_id"],
                    user_id=row["t_user_id"],
                    title=row["t_title"],
                    description=row["t_description"] or "",
                    start_date=row["t_start_date"] or "",
                    due_date=row["t_due_date"] or "",
                    due_time=row["t_due_time"] or "",
                    priority=row["t_priority"] or "media",
                    status=row["t_status"] or "pendente",
                    category=row["t_category"] or "",
                    reminder_enabled=bool(row["t_reminder_enabled"]),
                    completed_at=row["t_completed_at"],
                    legacy_schedule_id=row["t_legacy_id"],
                    created_at=row["t_created_at"] or "",
                    updated_at=row["t_updated_at"] or "",
                )
                reminder = TaskReminder(
                    id=row["r_id"],
                    task_id=row["r_task_id"],
                    reminder_type=row["r_type"],
                    remind_date=row["r_date"] or "",
                    remind_time=row["r_time"] or "09:00",
                    advance_minutes=int(row["r_adv"] or 0),
                    repeat_interval=row["r_repeat"] or "none",
                    is_active=bool(row["r_active"]),
                    is_sent=bool(row["r_sent"]),
                    last_notified_date=row["r_last_date"],
                    notified_at=row["r_notified_at"],
                    created_at=row["r_created_at"] or "",
                    updated_at=row["r_updated_at"] or "",
                )

                is_due, reason = self._is_reminder_due(reminder, task, now_dt)
                if is_due:
                    due_by_task.setdefault(task.id, []).append((task, reminder, reason))

            if not due_by_task:
                return []

            type_priority = {"overdue": 1, "custom": 2, "due_day": 3, "advance": 4}

            with conn:
                for task_id, items in due_by_task.items():
                    # Atualiza o estado no banco para todos os lembretes devidos desta tarefa
                    for task, reminder, _reason in items:
                        if reminder.reminder_type == "custom" and reminder.repeat_interval in ("daily", "weekly", "monthly"):
                            next_date = self._advance_repeat_date(reminder.remind_date, reminder.repeat_interval)
                            # Se ficou muito atrasado, garante que o próximo ciclo seja futuro
                            guard = 0
                            while f"{next_date} {reminder.remind_time}:00" <= now_ts and guard < 400:
                                next_date = self._advance_repeat_date(next_date, reminder.repeat_interval)
                                guard += 1
                            conn.execute(
                                """
                                UPDATE lembretes_tarefas
                                SET remind_date = ?, is_sent = 0, last_notified_date = ?,
                                    notified_at = ?, updated_at = ?
                                WHERE id = ?
                                """,
                                (next_date, today_iso, now_ts, now_ts, reminder.id),
                            )
                        elif reminder.reminder_type == "overdue":
                            conn.execute(
                                """
                                UPDATE lembretes_tarefas
                                SET last_notified_date = ?, notified_at = ?, updated_at = ?
                                WHERE id = ?
                                """,
                                (today_iso, now_ts, now_ts, reminder.id),
                            )
                        else:
                            conn.execute(
                                """
                                UPDATE lembretes_tarefas
                                SET is_sent = 1, last_notified_date = ?, notified_at = ?, updated_at = ?
                                WHERE id = ?
                                """,
                                (today_iso, now_ts, now_ts, reminder.id),
                            )

                    # Escolhe a notificação principal mais relevante para disparar 1 Toast limpo
                    items.sort(key=lambda x: type_priority.get(x[1].reminder_type, 9))
                    primary_task, primary_rem, primary_reason = items[0]

                    prefix = "🚨 Tarefa Atrasada" if primary_rem.reminder_type == "overdue" else "⏰ Tarefa DailyNotes"
                    toast_title = f"{prefix}: {primary_task.title}"
                    desc_preview = primary_task.description[:120].replace("\n", " ") if primary_task.description else ""
                    toast_msg = f"{primary_reason}\nPrioridade: {primary_task.priority_label}"
                    if desc_preview:
                        toast_msg += f"\n{desc_preview}"

                    dispatched.append(
                        {
                            "task": primary_task,
                            "reminder": primary_rem,
                            "title": toast_title,
                            "message": toast_msg,
                            "reason": primary_reason,
                        }
                    )

            # Dispara fora do bloco de transação do SQLite
            for item in dispatched:
                if notify_callback is not None:
                    notify_callback(item["task"], item["reminder"], item["title"], item["message"])
                else:
                    send_windows_notification(
                        title=item["title"],
                        message=item["message"],
                        play_sound=True,
                        task_id=item["task"].id,
                    )

            return dispatched
        except Exception as exc:
            logger.error("Erro ao verificar lembretes de tarefas: %s", exc)
            return []
        finally:
            conn.close()
