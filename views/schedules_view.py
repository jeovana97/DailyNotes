"""
Tela de Gerenciamento de Agendamentos e Lembretes.
Permite cadastrar notas agendadas com data, horário, prioridade e repetição,
com disparo automático de notificações nativas do Windows.
"""

import datetime
import tkinter as tk
from typing import Optional, Callable, List
import customtkinter as ctk

import config
from models.user import User
from models.schedule import Schedule
from services.schedule_service import ScheduleService
from utils.date_utils import format_date_br, parse_date_input, get_today_iso
from views.components.dialogs import show_message, ask_confirmation
from utils.notification_utils import send_windows_notification
from utils.window_utils import center_modal_on_parent


class ScheduleModalDialog(ctk.CTkToplevel):
    """Modal para cadastro ou edição de agendamento/lembrete."""

    def __init__(
        self,
        parent,
        title: str,
        schedule: Optional[Schedule] = None,
        initial_date: Optional[str] = None,
    ):
        super().__init__(parent)
        self.title(title)

        win_w = 520
        win_h = 600
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(460, 500)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.schedule = schedule
        self.result = None

        center_modal_on_parent(self, parent, win_w, win_h)

        # 1. Barra inferior FIXA de botões (GARANTE visibilidade sempre)
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(side="bottom", fill="x", padx=20, pady=(8, 14))

        btn_save_text = "💾 Salvar Agendamento" if not schedule else "💾 Atualizar Agendamento"
        self.btn_save = ctk.CTkButton(
            self.btn_frame,
            text=btn_save_text,
            width=190,
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["success"],
            hover_color=config.COLORS["success_hover"],
            text_color="#FFFFFF",
            command=self._on_save,
        )
        self.btn_save.pack(side="left")

        self.btn_cancel = ctk.CTkButton(
            self.btn_frame,
            text="Cancelar",
            width=100,
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self.destroy,
        )
        self.btn_cancel.pack(side="right")

        # 2. Container com rolagem para os campos do formulário
        self.container = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.container.pack(side="top", fill="both", expand=True, padx=15, pady=(15, 6))

        header_title = "⏰ Novo Agendamento de Nota" if not schedule else f"✏️ Editar Agendamento #{schedule.id}"
        self.lbl_title = ctk.CTkLabel(
            self.container,
            text=header_title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(pady=(12, 10))

        # Campo: Assunto / Título
        self.lbl_subject = ctk.CTkLabel(
            self.container,
            text="Assunto / Título da Nota:",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_subject.pack(fill="x", padx=20, pady=(0, 2))

        self.entry_title = ctk.CTkEntry(
            self.container,
            height=36,
            placeholder_text="Ex: Reunião com diretoria, Entrega de relatório, Pagamento...",
            corner_radius=6,
            font=ctk.CTkFont(size=13),
        )
        self.entry_title.pack(fill="x", padx=20, pady=(0, 12))
        if schedule:
            self.entry_title.insert(0, schedule.title)

        # Linha dupla: Data e Horário
        dt_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        dt_frame.pack(fill="x", padx=20, pady=(0, 12))

        # Coluna Esquerda: Data
        col_date = ctk.CTkFrame(dt_frame, fg_color="transparent")
        col_date.pack(side="left", fill="x", expand=True, padx=(0, 10))

        lbl_date = ctk.CTkLabel(
            col_date,
            text="📅 Data (DD/MM/AAAA):",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_date.pack(fill="x", pady=(0, 2))

        date_input_row = ctk.CTkFrame(col_date, fg_color="transparent")
        date_input_row.pack(fill="x")

        self.entry_date = ctk.CTkEntry(
            date_input_row,
            height=36,
            placeholder_text="DD/MM/AAAA",
            corner_radius=6,
            font=ctk.CTkFont(size=13),
        )
        self.entry_date.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_today = ctk.CTkButton(
            date_input_row,
            text="Hoje",
            width=50,
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._set_date_today,
        )
        btn_today.pack(side="left", padx=(0, 4))

        btn_tomorrow = ctk.CTkButton(
            date_input_row,
            text="+1 Dia",
            width=54,
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._set_date_tomorrow,
        )
        btn_tomorrow.pack(side="left")

        # Coluna Direita: Horário
        col_time = ctk.CTkFrame(dt_frame, fg_color="transparent")
        col_time.pack(side="right", fill="x", expand=True, padx=(10, 0))

        lbl_time = ctk.CTkLabel(
            col_time,
            text="🕒 Horário (HH:MM):",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_time.pack(fill="x", pady=(0, 2))

        time_input_row = ctk.CTkFrame(col_time, fg_color="transparent")
        time_input_row.pack(fill="x")

        self.entry_time = ctk.CTkEntry(
            time_input_row,
            height=36,
            placeholder_text="09:00",
            corner_radius=6,
            font=ctk.CTkFont(size=13),
        )
        self.entry_time.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_plus_1h = ctk.CTkButton(
            time_input_row,
            text="+1h",
            width=46,
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._add_hour_to_time,
        )
        btn_plus_1h.pack(side="left")

        # Inicializa valores de data e hora
        if schedule:
            self.entry_date.insert(0, schedule.date_br)
            self.entry_time.insert(0, schedule.schedule_time)
        else:
            default_d = format_date_br(initial_date) if initial_date else datetime.date.today().strftime("%d/%m/%Y")
            self.entry_date.insert(0, default_d)
            # Horário padrão: próxima hora cheia
            now = datetime.datetime.now()
            default_time = (now + datetime.timedelta(hours=1)).strftime("%H:00")
            self.entry_time.insert(0, default_time)

        # Linha de Opções: Prioridade e Repetição
        opts_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        opts_frame.pack(fill="x", padx=20, pady=(0, 12))

        # Prioridade
        col_prio = ctk.CTkFrame(opts_frame, fg_color="transparent")
        col_prio.pack(side="left", fill="x", expand=True, padx=(0, 10))

        lbl_prio = ctk.CTkLabel(
            col_prio,
            text="Prioridade:",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_prio.pack(fill="x", pady=(0, 2))

        self.combo_priority = ctk.CTkComboBox(
            col_prio,
            values=["Normal", "Alta", "Urgente", "Baixa"],
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
        )
        self.combo_priority.pack(fill="x")
        if schedule and schedule.priority:
            prio_map = {"normal": "Normal", "alta": "Alta", "urgente": "Urgente", "baixa": "Baixa"}
            self.combo_priority.set(prio_map.get(schedule.priority.lower(), "Normal"))
        else:
            self.combo_priority.set("Normal")

        # Repetição
        col_rep = ctk.CTkFrame(opts_frame, fg_color="transparent")
        col_rep.pack(side="right", fill="x", expand=True, padx=(10, 0))

        lbl_rep = ctk.CTkLabel(
            col_rep,
            text="Repetição do Lembrete:",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_rep.pack(fill="x", pady=(0, 2))

        self.combo_repeat = ctk.CTkComboBox(
            col_rep,
            values=["Não repete", "Diariamente", "Semanalmente", "Mensalmente"],
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
        )
        self.combo_repeat.pack(fill="x")
        if schedule and schedule.repeat_interval:
            rep_map = {"none": "Não repete", "daily": "Diariamente", "weekly": "Semanalmente", "monthly": "Mensalmente"}
            self.combo_repeat.set(rep_map.get(schedule.repeat_interval.lower(), "Não repete"))
        else:
            self.combo_repeat.set("Não repete")

        # Campo: Conteúdo da Nota / Detalhes
        self.lbl_content = ctk.CTkLabel(
            self.container,
            text="Nota / Detalhes do Agendamento:",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_content.pack(fill="x", padx=20, pady=(0, 2))

        self.txt_content = ctk.CTkTextbox(
            self.container,
            height=140,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            wrap="word",
        )
        self.txt_content.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        if schedule and schedule.content:
            self.txt_content.insert("1.0", schedule.content)

        # Informações sobre a notificação
        self.lbl_info = ctk.CTkLabel(
            self.container,
            text="🔔 Quando a data e horário agendados forem atingidos, o DailyNotes emitirá automaticamente um aviso nativo no Windows (Central de Ações) com sinal sonoro.",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
            wraplength=440,
            justify="left",
        )
        self.lbl_info.pack(fill="x", padx=20, pady=(0, 10))

        self.entry_title.focus_set()
        self.wait_window(self)

    def _set_date_today(self):
        self.entry_date.delete(0, "end")
        self.entry_date.insert(0, datetime.date.today().strftime("%d/%m/%Y"))

    def _set_date_tomorrow(self):
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        self.entry_date.delete(0, "end")
        self.entry_date.insert(0, tomorrow.strftime("%d/%m/%Y"))

    def _add_hour_to_time(self):
        current_time_str = self.entry_time.get().strip()
        try:
            parts = current_time_str.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            new_hh = (hh + 1) % 24
            self.entry_time.delete(0, "end")
            self.entry_time.insert(0, f"{new_hh:02d}:{mm:02d}")
        except Exception:
            self.entry_time.delete(0, "end")
            self.entry_time.insert(0, "10:00")

    def _on_save(self):
        title = self.entry_title.get().strip()
        if not title:
            show_message(self, "Aviso", "Informe o assunto ou título do agendamento.", kind="warning")
            self.entry_title.focus_set()
            return

        date_str = self.entry_date.get().strip()
        date_iso = parse_date_input(date_str)
        if not date_iso:
            show_message(self, "Aviso", "Informe uma data válida no formato DD/MM/AAAA.", kind="warning")
            self.entry_date.focus_set()
            return

        time_str = self.entry_time.get().strip()
        try:
            parts = time_str.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            if hh < 0 or hh > 23 or mm < 0 or mm > 59:
                raise ValueError()
            time_formatted = f"{hh:02d}:{mm:02d}"
        except Exception:
            show_message(self, "Aviso", "Informe um horário válido no formato HH:MM (ex: 14:30).", kind="warning")
            self.entry_time.focus_set()
            return

        prio_choice = self.combo_priority.get().lower()
        priority = "normal"
        if "urgente" in prio_choice:
            priority = "urgente"
        elif "alta" in prio_choice:
            priority = "alta"
        elif "baixa" in prio_choice:
            priority = "baixa"

        rep_choice = self.combo_repeat.get().lower()
        repeat = "none"
        if "diar" in rep_choice:
            repeat = "daily"
        elif "seman" in rep_choice:
            repeat = "weekly"
        elif "mens" in rep_choice:
            repeat = "monthly"

        content = self.txt_content.get("1.0", "end-1c").strip()

        self.result = {
            "title": title,
            "content": content,
            "schedule_date": date_iso,
            "schedule_time": time_formatted,
            "priority": priority,
            "repeat_interval": repeat,
        }
        self.destroy()


class SchedulesView(ctk.CTkFrame):
    """
    Tela principal de Agendamentos e Lembretes.
    """

    def __init__(
        self,
        master,
        current_user: User,
        schedule_service: ScheduleService,
        on_open_diary_date: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.schedule_service = schedule_service
        self.on_open_diary_date = on_open_diary_date

        self.current_filter = "pendente"
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # 1. Cabeçalho Card
        self.header_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.header_card.pack(fill="x", padx=20, pady=(15, 10))

        header_content = ctk.CTkFrame(self.header_card, fg_color="transparent")
        header_content.pack(fill="x", padx=16, pady=12)

        lbl_header = ctk.CTkLabel(
            header_content,
            text="⏰ Agendamentos e Lembretes",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_header.pack(side="left")

        # Botão Testar Notificação do Windows
        self.btn_test_notif = ctk.CTkButton(
            header_content,
            text="🔔 Testar Notificação",
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._handle_test_notification,
        )
        self.btn_test_notif.pack(side="right", padx=(8, 0))

        # Botão Novo Agendamento
        self.btn_new = ctk.CTkButton(
            header_content,
            text="➕ Novo Agendamento",
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._handle_new_schedule,
        )
        self.btn_new.pack(side="right")

        # 2. Barra de Filtros e Pesquisa
        self.filter_card = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.filter_card.pack(fill="x", padx=20, pady=(0, 10))

        filter_row = ctk.CTkFrame(self.filter_card, fg_color="transparent")
        filter_row.pack(fill="x", padx=14, pady=10)

        # Segmented Button de Status
        self.seg_filter = ctk.CTkSegmentedButton(
            filter_row,
            values=["Pendentes", "Hoje", "Atrasados", "Notificados", "Concluídos", "Todos"],
            command=self._on_segment_changed,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32,
        )
        self.seg_filter.set("Pendentes")
        self.seg_filter.pack(side="left", padx=(0, 14))

        # Campo de Busca
        self.entry_search = ctk.CTkEntry(
            filter_row,
            placeholder_text="🔍 Buscar por assunto ou nota...",
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_search.bind("<KeyRelease>", lambda e: self.refresh())

        # Botão Recarregar
        self.btn_refresh = ctk.CTkButton(
            filter_row,
            text="🔄",
            width=36,
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=13),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self.refresh,
        )
        self.btn_refresh.pack(side="left")

        # Barra de Resumo de Métricas
        self.summary_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.summary_frame.pack(fill="x", padx=20, pady=(0, 8))

        self.lbl_summary = ctk.CTkLabel(
            self.summary_frame,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        self.lbl_summary.pack(side="left")

        # 3. Lista Rolável de Agendamentos
        self.scroll_list = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.scroll_list.pack(fill="both", expand=True, padx=20, pady=(0, 15))

    def _on_segment_changed(self, value: str):
        val_map = {
            "Pendentes": "pendente",
            "Hoje": "hoje",
            "Atrasados": "atrasados",
            "Notificados": "notificado",
            "Concluídos": "concluido",
            "Todos": "todos",
        }
        self.current_filter = val_map.get(value, "pendente")
        self.refresh()

    def refresh(self):
        """Recarrega a listagem de agendamentos e atualiza os badges."""
        query = self.entry_search.get().strip() if hasattr(self, "entry_search") else None
        schedules = self.schedule_service.list_schedules(
            user_id=self.current_user.id,
            filter_status=self.current_filter,
            search_query=query,
        )
        counts = self.schedule_service.get_summary_counts(self.current_user.id)

        # Atualiza métricas
        self.lbl_summary.configure(
            text=f"Total: {counts['total']}  |  🟡 Pendentes: {counts['pendentes']}  |  📅 Hoje: {counts['hoje']}  |  🔴 Atrasados: {counts['atrasados']}  |  🟢 Concluídos: {counts['concluidos']}"
        )

        for widget in self.scroll_list.winfo_children():
            widget.destroy()

        if not schedules:
            empty_frame = ctk.CTkFrame(self.scroll_list, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=60)

            lbl_empty_icon = ctk.CTkLabel(
                empty_frame,
                text="⏰",
                font=ctk.CTkFont(size=48),
            )
            lbl_empty_icon.pack(pady=(0, 10))

            lbl_empty_text = ctk.CTkLabel(
                empty_frame,
                text="Nenhum agendamento encontrado nesta categoria.",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=config.COLORS["text_muted"],
            )
            lbl_empty_text.pack(pady=(0, 12))

            btn_empty_add = ctk.CTkButton(
                empty_frame,
                text="➕ Criar Primeiro Agendamento",
                height=36,
                corner_radius=8,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=config.COLORS["primary"],
                hover_color=config.COLORS["primary_hover"],
                text_color="#FFFFFF",
                command=self._handle_new_schedule,
            )
            btn_empty_add.pack()
            return

        for sched in schedules:
            self._render_schedule_card(sched)

    def _render_schedule_card(self, sched: Schedule):
        card = ctk.CTkFrame(
            self.scroll_list,
            corner_radius=10,
            fg_color=config.COLORS["card_dark_alt"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        card.pack(fill="x", padx=10, pady=5)

        # Linha Superior do Card: Badges de Status, Data/Hora, Prioridade e Repetição
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=14, pady=(10, 4))

        # Badge de Status
        status_bg = config.COLORS["card_dark"]
        status_fg = config.COLORS["text_dark"]
        if sched.status == "concluido":
            status_bg = config.COLORS["success"]
            status_fg = "#FFFFFF"
        elif sched.status == "notificado":
            status_bg = config.COLORS["primary"]
            status_fg = "#FFFFFF"
        elif sched.is_due:
            status_bg = config.COLORS["danger"]
            status_fg = "#FFFFFF"

        lbl_status = ctk.CTkLabel(
            top_row,
            text=f" {sched.status_label} ",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=status_bg,
            text_color=status_fg,
            corner_radius=6,
        )
        lbl_status.pack(side="left", padx=(0, 8))

        # Badge Data e Horário
        dt_text = f"📅 {sched.date_br} às 🕒 {sched.schedule_time}"
        lbl_dt = ctk.CTkLabel(
            top_row,
            text=dt_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_dt.pack(side="left", padx=(0, 8))

        # Badge Prioridade
        lbl_prio = ctk.CTkLabel(
            top_row,
            text=f"• Prioridade: {sched.priority_label}",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
        )
        lbl_prio.pack(side="left", padx=(0, 8))

        # Badge Repetição se houver
        if sched.repeat_interval and sched.repeat_interval != "none":
            lbl_rep = ctk.CTkLabel(
                top_row,
                text=f"• {sched.repeat_label}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLORS["secondary"],
            )
            lbl_rep.pack(side="left")

        # Linha do Meio: Título do Assunto
        title_row = ctk.CTkFrame(card, fg_color="transparent")
        title_row.pack(fill="x", padx=14, pady=(2, 4))

        lbl_subject = ctk.CTkLabel(
            title_row,
            text=sched.title,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        lbl_subject.pack(side="left", fill="x", expand=True)

        # Linha do Conteúdo / Nota (se houver)
        if sched.content:
            content_row = ctk.CTkFrame(card, fg_color="transparent")
            content_row.pack(fill="x", padx=14, pady=(0, 8))

            lbl_note = ctk.CTkLabel(
                content_row,
                text=sched.content,
                font=ctk.CTkFont(size=12),
                text_color=config.COLORS["text_muted"],
                anchor="w",
                justify="left",
                wraplength=650,
            )
            lbl_note.pack(fill="x")

        # Linha Inferior: Botões de Ação
        actions_row = ctk.CTkFrame(card, fg_color="transparent")
        actions_row.pack(fill="x", padx=14, pady=(0, 10))

        # Botão Concluir ou Reabrir
        if sched.status != "concluido":
            btn_complete = ctk.CTkButton(
                actions_row,
                text="✔️ Concluir",
                width=90,
                height=28,
                corner_radius=6,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=config.COLORS["success"],
                hover_color=config.COLORS["success_hover"],
                text_color="#FFFFFF",
                command=lambda s=sched: self._handle_toggle_complete(s, "concluido"),
            )
            btn_complete.pack(side="left", padx=(0, 6))
        else:
            btn_reopen = ctk.CTkButton(
                actions_row,
                text="↩️ Reabrir",
                width=90,
                height=28,
                corner_radius=6,
                font=ctk.CTkFont(size=11),
                fg_color=config.COLORS["card_dark"],
                hover_color=config.COLORS["primary"],
                text_color=config.COLORS["button_text"],
                command=lambda s=sched: self._handle_toggle_complete(s, "pendente"),
            )
            btn_reopen.pack(side="left", padx=(0, 6))

        # Botão Editar
        btn_edit = ctk.CTkButton(
            actions_row,
            text="✏️ Editar",
            width=80,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=lambda s=sched: self._handle_edit_schedule(s),
        )
        btn_edit.pack(side="left", padx=(0, 6))

        # Botão Abrir no Diário da Data
        if self.on_open_diary_date is not None:
            btn_diary = ctk.CTkButton(
                actions_row,
                text="📝 Abrir no Diário",
                width=120,
                height=28,
                corner_radius=6,
                font=ctk.CTkFont(size=11),
                fg_color=config.COLORS["card_dark"],
                hover_color=config.COLORS["primary"],
                text_color=config.COLORS["button_text"],
                command=lambda d=sched.schedule_date: self.on_open_diary_date(d),
            )
            btn_diary.pack(side="left", padx=(0, 6))

        # Botão Disparar Notificação de Teste
        btn_notif = ctk.CTkButton(
            actions_row,
            text="🔔 Testar Aviso",
            width=100,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark"],
            hover_color=config.COLORS["warning"],
            text_color=config.COLORS["button_text"],
            command=lambda s=sched: self._handle_manual_notify(s),
        )
        btn_notif.pack(side="left", padx=(0, 6))

        # Botão Excluir
        btn_delete = ctk.CTkButton(
            actions_row,
            text="🗑️ Excluir",
            width=80,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark"],
            hover_color=config.COLORS["danger"],
            text_color=config.COLORS["button_text"],
            command=lambda s=sched: self._handle_delete_schedule(s),
        )
        btn_delete.pack(side="right")

    def _handle_new_schedule(self):
        diag = ScheduleModalDialog(self, "Novo Agendamento")
        if diag.result:
            res = diag.result
            new_s, msg = self.schedule_service.create_schedule(
                user_id=self.current_user.id,
                title=res["title"],
                content=res["content"],
                schedule_date=res["schedule_date"],
                schedule_time=res["schedule_time"],
                priority=res["priority"],
                repeat_interval=res["repeat_interval"],
            )
            if new_s:
                show_message(self, "Sucesso", msg, kind="success")
                self.refresh()
            else:
                show_message(self, "Erro", msg, kind="danger")

    def _handle_edit_schedule(self, sched: Schedule):
        diag = ScheduleModalDialog(self, f"Editar Agendamento #{sched.id}", schedule=sched)
        if diag.result:
            res = diag.result
            ok, msg = self.schedule_service.update_schedule(
                schedule_id=sched.id,
                user_id=self.current_user.id,
                title=res["title"],
                content=res["content"],
                schedule_date=res["schedule_date"],
                schedule_time=res["schedule_time"],
                priority=res["priority"],
                repeat_interval=res["repeat_interval"],
            )
            if ok:
                show_message(self, "Sucesso", msg, kind="success")
                self.refresh()
            else:
                show_message(self, "Erro", msg, kind="danger")

    def _handle_toggle_complete(self, sched: Schedule, target_status: str):
        ok, msg = self.schedule_service.set_status(sched.id, self.current_user.id, target_status)
        if ok:
            self.refresh()
        else:
            show_message(self, "Erro", msg, kind="danger")

    def _handle_delete_schedule(self, sched: Schedule):
        confirmed = ask_confirmation(
            self,
            "Excluir Agendamento",
            f"Deseja realmente excluir o agendamento '{sched.title}'?",
            kind="danger",
        )
        if confirmed:
            ok, msg = self.schedule_service.delete_schedule(sched.id, self.current_user.id)
            if ok:
                self.refresh()
            else:
                show_message(self, "Erro", msg, kind="danger")

    def _handle_manual_notify(self, sched: Schedule):
        preview = sched.content[:120].replace("\n", " ") if sched.content else ""
        msg = f"Horário: {sched.schedule_time} ({sched.date_br})\n{preview}".strip()
        send_windows_notification(
            title=f"⏰ DailyNotes: {sched.title}",
            message=msg,
            app_id="DailyNotes",
            play_sound=True,
        )
        show_message(
            self,
            "Notificação Enviada",
            "A notificação do Windows foi disparada para a Central de Ações!",
            kind="info",
        )

    def _handle_test_notification(self):
        now_time = datetime.datetime.now().strftime("%H:%M")
        send_windows_notification(
            title="⏰ DailyNotes - Teste de Notificação",
            message=f"Esta é uma notificação nativa do Windows disparada com sucesso às {now_time}!",
            app_id="DailyNotes",
            play_sound=True,
        )
        show_message(
            self,
            "Notificação de Teste",
            "Aviso disparado para a Central de Ações do Windows!",
            kind="success",
        )

