"""
Serviço de Gestão e Verificação de Agendamentos e Lembretes.
Dispara notificações nativas do Windows quando a data e horário agendados forem atingidos.
"""

import datetime
import logging
from typing import Optional, List, Tuple, Dict, Any

from database.connection import get_connection
from models.schedule import Schedule
from utils.date_utils import get_current_timestamp, get_today_iso, parse_date_input
from utils.text_utils import normalize_text
from utils.notification_utils import send_windows_notification

logger = logging.getLogger(__name__)


class ScheduleService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def create_schedule(
        self,
        user_id: int,
        title: str,
        content: str = "",
        schedule_date: str = "",
        schedule_time: str = "09:00",
        priority: str = "normal",
        repeat_interval: str = "none",
    ) -> Tuple[Optional[Schedule], str]:
        """Cadastra um novo agendamento com data, horário e nota associada."""
        if not title or not title.strip():
            return None, "O assunto/título do agendamento não pode estar em branco."

        # Valida ou normaliza a data
        date_iso = parse_date_input(schedule_date)
        if not date_iso:
            date_iso = get_today_iso()

        # Valida o horário (HH:MM)
        time_clean = (schedule_time or "09:00").strip()
        try:
            parts = time_clean.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            time_formatted = f"{hh:02d}:{mm:02d}"
        except Exception:
            time_formatted = "09:00"

        priority = priority.lower() if priority in ("baixa", "normal", "alta", "urgente") else "normal"
        repeat_interval = (
            repeat_interval.lower()
            if repeat_interval in ("none", "daily", "weekly", "monthly")
            else "none"
        )

        title_norm = normalize_text(title)
        now = get_current_timestamp()

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO schedules (
                    user_id, title, title_normalized, content,
                    schedule_date, schedule_time, status, priority,
                    repeat_interval, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?, ?, ?, ?)
                """,
                (
                    user_id,
                    title.strip(),
                    title_norm,
                    content.strip(),
                    date_iso,
                    time_formatted,
                    priority,
                    repeat_interval,
                    now,
                    now,
                ),
            )
            conn.commit()
            sched_id = cursor.lastrowid
            cursor.execute("SELECT * FROM schedules WHERE id = ?", (sched_id,))
            return Schedule.from_row(cursor.fetchone()), "Agendamento criado com sucesso!"
        except Exception as e:
            logger.error("Erro ao criar agendamento: %s", e)
            return None, f"Erro ao criar agendamento: {e}"
        finally:
            conn.close()

    def update_schedule(
        self,
        schedule_id: int,
        user_id: int,
        title: str,
        content: str,
        schedule_date: str,
        schedule_time: str,
        priority: str = "normal",
        repeat_interval: str = "none",
        status: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Atualiza os dados de um agendamento existente."""
        if not title or not title.strip():
            return False, "O assunto/título não pode estar em branco."

        date_iso = parse_date_input(schedule_date) or schedule_date
        try:
            parts = schedule_time.strip().split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            time_formatted = f"{hh:02d}:{mm:02d}"
        except Exception:
            time_formatted = "09:00"

        title_norm = normalize_text(title)
        now = get_current_timestamp()

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    """
                    UPDATE schedules
                    SET title = ?, title_normalized = ?, content = ?,
                        schedule_date = ?, schedule_time = ?, priority = ?,
                        repeat_interval = ?, status = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        title.strip(),
                        title_norm,
                        content.strip(),
                        date_iso,
                        time_formatted,
                        priority,
                        repeat_interval,
                        status,
                        now,
                        schedule_id,
                        user_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE schedules
                    SET title = ?, title_normalized = ?, content = ?,
                        schedule_date = ?, schedule_time = ?, priority = ?,
                        repeat_interval = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        title.strip(),
                        title_norm,
                        content.strip(),
                        date_iso,
                        time_formatted,
                        priority,
                        repeat_interval,
                        now,
                        schedule_id,
                        user_id,
                    ),
                )
            conn.commit()
            if cursor.rowcount > 0:
                return True, "Agendamento atualizado com sucesso!"
            return False, "Agendamento não encontrado ou sem permissão."
        except Exception as e:
            logger.error("Erro ao atualizar agendamento: %s", e)
            return False, f"Erro ao atualizar agendamento: {e}"
        finally:
            conn.close()

    def delete_schedule(self, schedule_id: int, user_id: int) -> Tuple[bool, str]:
        """Exclui um agendamento do usuário."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM schedules WHERE id = ? AND user_id = ?", (schedule_id, user_id))
            conn.commit()
            if cursor.rowcount > 0:
                return True, "Agendamento excluído com sucesso!"
            return False, "Agendamento não encontrado ou sem permissão."
        except Exception as e:
            logger.error("Erro ao excluir agendamento: %s", e)
            return False, f"Erro ao excluir agendamento: {e}"
        finally:
            conn.close()

    def set_status(self, schedule_id: int, user_id: int, new_status: str) -> Tuple[bool, str]:
        """Altera o status de um agendamento (ex: 'concluido', 'pendente', 'cancelado')."""
        now = get_current_timestamp()
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE schedules
                SET status = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (new_status, now, schedule_id, user_id),
            )
            conn.commit()
            if cursor.rowcount > 0:
                msg = "Agendamento marcado como concluído!" if new_status == "concluido" else f"Status alterado para {new_status}!"
                return True, msg
            return False, "Agendamento não encontrado."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def get_schedule_by_id(self, schedule_id: int, user_id: Optional[int] = None) -> Optional[Schedule]:
        """Retorna um agendamento específico."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            if user_id is not None:
                cursor.execute("SELECT * FROM schedules WHERE id = ? AND user_id = ?", (schedule_id, user_id))
            else:
                cursor.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
            row = cursor.fetchone()
            return Schedule.from_row(row) if row else None
        finally:
            conn.close()

    def list_schedules(
        self,
        user_id: int,
        filter_status: Optional[str] = None,
        filter_date: Optional[str] = None,
        search_query: Optional[str] = None,
        is_admin_all: bool = False,
    ) -> List[Schedule]:
        """
        Lista os agendamentos com filtros opcionais:
        - filter_status: 'todos', 'pendente', 'notificado', 'concluido', 'hoje', 'atrasados'
        - filter_date: YYYY-MM-DD
        - search_query: pesquisa no título e conteúdo
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            params = []
            conditions = []

            if not is_admin_all:
                conditions.append("s.user_id = ?")
                params.append(user_id)

            today_iso = get_today_iso()
            now_time = datetime.datetime.now().strftime("%H:%M")

            if filter_status == "pendente":
                conditions.append("s.status = 'pendente'")
            elif filter_status == "notificado":
                conditions.append("s.status = 'notificado'")
            elif filter_status == "concluido":
                conditions.append("s.status = 'concluido'")
            elif filter_status == "hoje":
                conditions.append("s.schedule_date = ?")
                params.append(today_iso)
            elif filter_status == "atrasados":
                conditions.append(
                    """(
                        s.status = 'pendente'
                        AND (
                            s.schedule_date < ?
                            OR (s.schedule_date = ? AND s.schedule_time < ?)
                        )
                    )"""
                )
                params.extend([today_iso, today_iso, now_time])

            if filter_date:
                conditions.append("s.schedule_date = ?")
                params.append(filter_date)

            if search_query and search_query.strip():
                query_norm = normalize_text(search_query)
                conditions.append("(s.title_normalized LIKE ? OR s.content LIKE ?)")
                params.append(f"%{query_norm}%")
                params.append(f"%{search_query.strip()}%")

            where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            query = f"""
                SELECT s.*, u.full_name as user_name
                FROM schedules s
                LEFT JOIN users u ON u.id = s.user_id
                {where_clause}
                ORDER BY
                    CASE
                        WHEN s.status = 'pendente' THEN 1
                        WHEN s.status = 'notificado' THEN 2
                        ELSE 3
                    END,
                    s.schedule_date ASC,
                    s.schedule_time ASC
            """
            cursor.execute(query, params)
            return [Schedule.from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_summary_counts(self, user_id: int) -> Dict[str, int]:
        """Retorna a contagem de agendamentos por categoria."""
        conn = get_connection(self.db_path)
        today_iso = get_today_iso()
        now_time = datetime.datetime.now().strftime("%H:%M")
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'pendente' THEN 1 ELSE 0 END) as pendentes,
                    SUM(CASE WHEN schedule_date = ? THEN 1 ELSE 0 END) as hoje,
                    SUM(CASE WHEN status = 'concluido' THEN 1 ELSE 0 END) as concluidos,
                    SUM(CASE
                        WHEN status = 'pendente' AND (schedule_date < ? OR (schedule_date = ? AND schedule_time < ?))
                        THEN 1 ELSE 0
                    END) as atrasados
                FROM schedules
                WHERE user_id = ?
                """,
                (today_iso, today_iso, today_iso, now_time, user_id),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "total": row["total"] or 0,
                    "pendentes": row["pendentes"] or 0,
                    "hoje": row["hoje"] or 0,
                    "concluidos": row["concluidos"] or 0,
                    "atrasados": row["atrasados"] or 0,
                }
            return {"total": 0, "pendentes": 0, "hoje": 0, "concluidos": 0, "atrasados": 0}
        finally:
            conn.close()

    def check_and_notify_due_schedules(self, user_id: Optional[int] = None) -> List[Schedule]:
        """
        Verifica se há agendamentos pendentes cuja data e horário já foram atingidos.
        Para cada agendamento vencido:
        - Dispara a notificação nativa do Windows (Toast)
        - Se for de repetição, programa a próxima data
        - Caso contrário, marca o status como 'notificado'
        Retorna a lista de agendamentos que foram notificados nesta chamada.
        """
        today_iso = get_today_iso()
        now_time = datetime.datetime.now().strftime("%H:%M")
        now_ts = get_current_timestamp()

        conn = get_connection(self.db_path)
        notified_schedules: List[Schedule] = []

        try:
            cursor = conn.cursor()
            params = [today_iso, today_iso, now_time]
            user_filter = "AND s.user_id = ?" if user_id is not None else ""
            if user_id is not None:
                params.append(user_id)

            query = f"""
                SELECT s.*, u.full_name as user_name
                FROM schedules s
                LEFT JOIN users u ON u.id = s.user_id
                WHERE s.status = 'pendente'
                  AND (
                      s.schedule_date < ?
                      OR (s.schedule_date = ? AND s.schedule_time <= ?)
                  )
                {user_filter}
                ORDER BY s.schedule_date ASC, s.schedule_time ASC
            """
            cursor.execute(query, params)
            due_rows = cursor.fetchall()

            for row in due_rows:
                sched = Schedule.from_row(row)

                # Monta a mensagem para a notificação do Windows
                notif_title = f"⏰ Lembrete DailyNotes: {sched.title}"
                preview_text = sched.content[:150].replace("\n", " ") if sched.content else ""
                notif_msg = f"Horário: {sched.schedule_time} ({sched.date_br})\n{preview_text}".strip()

                # Dispara notificação nativa do Windows (Toast)
                send_windows_notification(
                    title=notif_title,
                    message=notif_msg,
                    app_id="DailyNotes",
                    play_sound=True,
                )

                # Gerencia repetição ou atualiza status para 'notificado'
                if sched.repeat_interval == "daily":
                    # Avança 1 dia
                    dt = datetime.datetime.strptime(sched.schedule_date, "%Y-%m-%d") + datetime.timedelta(days=1)
                    next_date = dt.strftime("%Y-%m-%d")
                    cursor.execute(
                        "UPDATE schedules SET schedule_date = ?, notified_at = ?, updated_at = ? WHERE id = ?",
                        (next_date, now_ts, now_ts, sched.id),
                    )
                elif sched.repeat_interval == "weekly":
                    # Avança 7 dias
                    dt = datetime.datetime.strptime(sched.schedule_date, "%Y-%m-%d") + datetime.timedelta(days=7)
                    next_date = dt.strftime("%Y-%m-%d")
                    cursor.execute(
                        "UPDATE schedules SET schedule_date = ?, notified_at = ?, updated_at = ? WHERE id = ?",
                        (next_date, now_ts, now_ts, sched.id),
                    )
                elif sched.repeat_interval == "monthly":
                    # Avança 30 dias
                    dt = datetime.datetime.strptime(sched.schedule_date, "%Y-%m-%d") + datetime.timedelta(days=30)
                    next_date = dt.strftime("%Y-%m-%d")
                    cursor.execute(
                        "UPDATE schedules SET schedule_date = ?, notified_at = ?, updated_at = ? WHERE id = ?",
                        (next_date, now_ts, now_ts, sched.id),
                    )
                else:
                    cursor.execute(
                        "UPDATE schedules SET status = 'notificado', notified_at = ?, updated_at = ? WHERE id = ?",
                        (now_ts, now_ts, sched.id),
                    )

                notified_schedules.append(sched)

            conn.commit()
            return notified_schedules
        except Exception as e:
            logger.error("Erro durante verificação de agendamentos vencidos: %s", e)
            return []
        finally:
            conn.close()

