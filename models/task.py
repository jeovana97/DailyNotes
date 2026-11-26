"""
Modelos de domínio do Gerenciador de Tarefas (evolução do menu Agendamentos).
Define as entidades Task, TaskHistoryEntry e TaskReminder e utilitários de formatação.
"""

import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


TASK_PRIORITIES: Tuple[str, ...] = ("baixa", "media", "alta", "urgente")
TASK_STATUSES: Tuple[str, ...] = ("pendente", "em_andamento", "concluida", "cancelada")
REMINDER_TYPES: Tuple[str, ...] = ("custom", "due_day", "advance", "overdue")
REPEAT_INTERVALS: Tuple[str, ...] = ("none", "daily", "weekly", "monthly")

PRIORITY_LABELS = {
    "baixa": "Baixa",
    "media": "Média",
    "alta": "Alta",
    "urgente": "Urgente",
}

PRIORITY_ORDER = {
    "urgente": 4,
    "alta": 3,
    "media": 2,
    "baixa": 1,
}

STATUS_LABELS = {
    "pendente": "Pendente",
    "em_andamento": "Em andamento",
    "concluida": "Concluída",
    "cancelada": "Cancelada",
}

REMINDER_TYPE_LABELS = {
    "custom": "Data e horário específicos",
    "due_day": "Aviso no dia do vencimento",
    "advance": "Aviso antecipado",
    "overdue": "Lembrete de tarefa atrasada",
}

REPEAT_LABELS = {
    "none": "Sem repetição",
    "daily": "Diário",
    "weekly": "Semanal",
    "monthly": "Mensal",
}

ADVANCE_PRESETS = [
    (15, "15 minutos antes"),
    (30, "30 minutos antes"),
    (60, "1 hora antes"),
    (120, "2 horas antes"),
    (240, "4 horas antes"),
    (1440, "1 dia antes"),
    (2880, "2 dias antes"),
]


def normalize_priority(value: Optional[str]) -> str:
    """Normaliza prioridade aceitando variantes com acento ou o valor legado 'normal'."""
    raw = (value or "media").strip().lower()
    mapping = {
        "baixa": "baixa",
        "media": "media",
        "média": "media",
        "normal": "media",
        "alta": "alta",
        "urgente": "urgente",
    }
    return mapping.get(raw, "media")


def normalize_status(value: Optional[str]) -> str:
    """Normaliza status aceitando rótulos amigáveis e valores legados."""
    raw = (value or "pendente").strip().lower()
    mapping = {
        "pendente": "pendente",
        "notificado": "pendente",
        "em_andamento": "em_andamento",
        "em andamento": "em_andamento",
        "andamento": "em_andamento",
        "concluida": "concluida",
        "concluída": "concluida",
        "concluido": "concluida",
        "concluído": "concluida",
        "cancelada": "cancelada",
        "cancelado": "cancelada",
    }
    return mapping.get(raw, "pendente")


def format_iso_date_br(date_iso: Optional[str]) -> str:
    """Converte YYYY-MM-DD para DD/MM/AAAA."""
    if not date_iso:
        return ""
    parts = str(date_iso).strip().split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return str(date_iso)


def format_timestamp_br(ts: Optional[str]) -> str:
    """Converte YYYY-MM-DD HH:MM:SS para DD/MM/AAAA HH:MM."""
    if not ts:
        return ""
    raw = str(ts).strip()
    if len(raw) >= 16 and raw[4] == "-" and raw[7] == "-":
        date_part = format_iso_date_br(raw[:10])
        time_part = raw[11:16]
        return f"{date_part} {time_part}"
    if len(raw) == 10 and raw[4] == "-":
        return format_iso_date_br(raw)
    return raw


def format_advance_label(minutes: int) -> str:
    """Formata minutos de antecedência em texto amigável."""
    mins = max(0, int(minutes or 0))
    for preset_m, label in ADVANCE_PRESETS:
        if mins == preset_m:
            return label
    if mins >= 1440 and mins % 1440 == 0:
        days = mins // 1440
        return f"{days} dia{'s' if days > 1 else ''} antes"
    if mins >= 60 and mins % 60 == 0:
        hours = mins // 60
        return f"{hours} hora{'s' if hours > 1 else ''} antes"
    return f"{mins} minuto{'s' if mins != 1 else ''} antes"


@dataclass
class TaskHistoryEntry:
    """Representa um registro cronológico de andamento ou alteração de uma tarefa."""
    id: Optional[int]
    task_id: int
    status_at_time: str
    note: str
    created_at: str = ""

    @property
    def created_at_br(self) -> str:
        return format_timestamp_br(self.created_at)

    @property
    def date_br(self) -> str:
        return format_iso_date_br(self.created_at[:10]) if self.created_at else ""

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(normalize_status(self.status_at_time), self.status_at_time)


@dataclass
class TaskReminder:
    """Representa uma configuração de lembrete/notificação vinculada a uma tarefa."""
    id: Optional[int]
    task_id: int
    reminder_type: str = "custom"  # custom | due_day | advance | overdue
    remind_date: str = ""          # YYYY-MM-DD (para custom)
    remind_time: str = "09:00"     # HH:MM
    advance_minutes: int = 0       # Minutos antes do vencimento (para advance)
    repeat_interval: str = "none"  # none | daily | weekly | monthly
    is_active: bool = True
    is_sent: bool = False
    last_notified_date: Optional[str] = None
    notified_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def type_label(self) -> str:
        return REMINDER_TYPE_LABELS.get(self.reminder_type, self.reminder_type)

    @property
    def summary_text(self) -> str:
        if self.reminder_type == "custom":
            d_br = format_iso_date_br(self.remind_date) if self.remind_date else "sem data"
            rep = f" ({REPEAT_LABELS.get(self.repeat_interval, '')})" if self.repeat_interval != "none" else ""
            return f"Data/hora: {d_br} às {self.remind_time or '09:00'}{rep}"
        if self.reminder_type == "due_day":
            return f"No dia do vencimento às {self.remind_time or '09:00'}"
        if self.reminder_type == "advance":
            return f"Antecipado: {format_advance_label(self.advance_minutes)}"
        if self.reminder_type == "overdue":
            return f"Tarefa atrasada (diário às {self.remind_time or '09:00'})"
        return self.type_label


@dataclass
class Task:
    """Entidade principal de uma Tarefa do Gerenciador de Tarefas."""
    id: Optional[int]
    user_id: int
    title: str
    description: str = ""
    start_date: str = ""       # YYYY-MM-DD
    due_date: str = ""         # YYYY-MM-DD
    due_time: str = ""         # HH:MM (opcional)
    priority: str = "media"    # baixa | media | alta | urgente
    status: str = "pendente"   # pendente | em_andamento | concluida | cancelada
    category: str = ""
    reminder_enabled: bool = False
    completed_at: Optional[str] = None
    legacy_schedule_id: Optional[int] = None
    created_at: str = ""
    updated_at: str = ""

    # Campos auxiliares populados nas consultas
    last_update_note: str = ""
    last_update_at: str = ""
    history_count: int = 0
    active_reminders_count: int = 0
    history: List[TaskHistoryEntry] = field(default_factory=list)
    reminders: List[TaskReminder] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.status in ("pendente", "em_andamento")

    @property
    def is_completed(self) -> bool:
        return self.status == "concluida"

    @property
    def is_canceled(self) -> bool:
        return self.status == "cancelada"

    def is_overdue(self, now: Optional[datetime.datetime] = None) -> bool:
        """Retorna True se a tarefa estiver aberta e com data/horário previstos vencidos."""
        if not self.is_open or not self.due_date:
            return False
        ref = now or datetime.datetime.now()
        today_iso = ref.strftime("%Y-%m-%d")
        if self.due_date < today_iso:
            return True
        if self.due_date == today_iso and self.due_time:
            now_hm = ref.strftime("%H:%M")
            return self.due_time < now_hm
        return False

    def is_due_today(self, now: Optional[datetime.datetime] = None) -> bool:
        if not self.is_open or not self.due_date:
            return False
        ref = now or datetime.datetime.now()
        return self.due_date == ref.strftime("%Y-%m-%d")

    def is_upcoming(self, now: Optional[datetime.datetime] = None) -> bool:
        if not self.is_open or not self.due_date:
            return False
        ref = now or datetime.datetime.now()
        return self.due_date > ref.strftime("%Y-%m-%d")

    @property
    def due_date_br(self) -> str:
        return format_iso_date_br(self.due_date) if self.due_date else "Sem prazo"

    @property
    def due_display(self) -> str:
        if not self.due_date:
            return "Sem prazo definido"
        if self.due_time:
            return f"{self.due_date_br} às {self.due_time}"
        return self.due_date_br

    @property
    def start_date_br(self) -> str:
        return format_iso_date_br(self.start_date) if self.start_date else "-"

    @property
    def created_at_br(self) -> str:
        return format_timestamp_br(self.created_at)

    @property
    def updated_at_br(self) -> str:
        return format_timestamp_br(self.updated_at)

    @property
    def completed_at_br(self) -> str:
        return format_timestamp_br(self.completed_at) if self.completed_at else ""

    @property
    def last_update_br(self) -> str:
        return format_timestamp_br(self.last_update_at or self.updated_at or self.created_at)

    @property
    def priority_label(self) -> str:
        return PRIORITY_LABELS.get(self.priority, self.priority)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def priority_weight(self) -> int:
        return PRIORITY_ORDER.get(self.priority, 2)
