from dataclasses import dataclass
from typing import Optional
import datetime
from utils.date_utils import format_date_br


@dataclass
class Schedule:
    """Modelo de dados para Agendamentos e Lembretes com Notificação."""
    id: Optional[int]
    user_id: int
    title: str
    title_normalized: str = ""
    content: str = ""
    schedule_date: str = ""  # Formato ISO: YYYY-MM-DD
    schedule_time: str = "09:00"  # Formato: HH:MM
    status: str = "pendente"  # 'pendente', 'notificado', 'concluido', 'cancelado'
    priority: str = "normal"  # 'baixa', 'normal', 'alta', 'urgente'
    repeat_interval: str = "none"  # 'none', 'daily', 'weekly', 'monthly'
    notified_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    user_name: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Schedule":
        """Instancia um Schedule a partir de um sqlite3.Row."""
        keys = row.keys()
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            title_normalized=row["title_normalized"] if "title_normalized" in keys else "",
            content=row["content"] if "content" in keys else "",
            schedule_date=row["schedule_date"],
            schedule_time=row["schedule_time"],
            status=row["status"],
            priority=row["priority"] if "priority" in keys else "normal",
            repeat_interval=row["repeat_interval"] if "repeat_interval" in keys else "none",
            notified_at=row["notified_at"] if "notified_at" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            user_name=row["user_name"] if "user_name" in keys else None,
        )

    @property
    def date_br(self) -> str:
        """Retorna a data no formato legível brasileiro DD/MM/AAAA."""
        return format_date_br(self.schedule_date)

    @property
    def is_due(self) -> bool:
        """Verifica se o agendamento já venceu ou está no momento de ser notificado."""
        if self.status != "pendente":
            return False
        try:
            target_dt = datetime.datetime.strptime(
                f"{self.schedule_date} {self.schedule_time}", "%Y-%m-%d %H:%M"
            )
            return datetime.datetime.now() >= target_dt
        except Exception:
            return False

    @property
    def is_today(self) -> bool:
        """Verifica se a data do agendamento é hoje."""
        today = datetime.date.today().strftime("%Y-%m-%d")
        return self.schedule_date == today

    @property
    def status_label(self) -> str:
        """Retorna o rótulo amigável com emoji para o status."""
        if self.status == "concluido":
            return "🟢 Concluído"
        if self.status == "notificado":
            return "🔔 Notificado"
        if self.status == "cancelado":
            return "⚪ Cancelado"
        if self.is_due:
            return "🔴 Atrasado"
        return "🟡 Pendente"

    @property
    def priority_label(self) -> str:
        """Retorna o rótulo amigável com emoji para prioridade."""
        p = (self.priority or "").lower()
        if p == "urgente":
            return "🚨 Urgente"
        if p == "alta":
            return "🔴 Alta"
        if p == "baixa":
            return "🟢 Baixa"
        return "🔵 Normal"

    @property
    def repeat_label(self) -> str:
        """Retorna o rótulo da repetição."""
        r = (self.repeat_interval or "").lower()
        if r == "daily":
            return "🔄 Diário"
        if r == "weekly":
            return "🔄 Semanal"
        if r == "monthly":
            return "🔄 Mensal"
        return "Não repete"

