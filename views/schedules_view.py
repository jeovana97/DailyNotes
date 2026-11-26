"""
Tela principal do Gerenciador de Tarefas e Agendamentos (evolução do menu Agendamentos).
Experiência estilo Microsoft To Do integrada ao Diário de Anotações:
- Indicadores de produtividade (Pendentes, Em andamento, Concluídas, Atrasadas, Para hoje)
- 8 abas/visões rápidas + pesquisa em título/descrição/histórico + filtros + ordenação
- Listagem moderna com alteração rápida de status e destaque visual para tarefas do dia/atrasadas
- Painel lateral completo de Detalhes da Tarefa (Informações gerais, Ações e Andamento/Histórico cronológico).
"""

import datetime
from typing import Callable, Dict, List, Optional
import customtkinter as ctk

import config
from models.user import User
from models.task import (
    PRIORITY_LABELS,
    STATUS_LABELS,
    Task,
    normalize_status,
)
from services.schedule_service import ScheduleService
from services.task_service import TaskService
from utils.date_utils import parse_date_input
from utils.notification_utils import send_windows_notification
from views.components.dialogs import ask_confirmation, show_message
from views.components.task_dialogs import TaskFormDialog


PRIORITY_COLORS = {
    "baixa": ("#64748B", "#94A3B8"),
    "media": ("#2563EB", "#3B82F6"),
    "alta": ("#EA580C", "#F97316"),
    "urgente": ("#DC2626", "#EF4444"),
}

PRIORITY_ICONS = {
    "baixa": "⚪",
    "media": "🔵",
    "alta": "🟠",
    "urgente": "🔴",
}

STATUS_COLORS = {
    "pendente": ("#2563EB", "#3B82F6"),
    "em_andamento": ("#7C3AED", "#8B5CF6"),
    "concluida": ("#059669", "#10B981"),
    "cancelada": ("#64748B", "#64748B"),
}

STATUS_ICONS = {
    "pendente": "⏳",
    "em_andamento": "🚀",
    "concluida": "✅",
    "cancelada": "🚫",
}

TAB_DEFINITIONS = [
    ("todas", "Todas"),
    ("pendentes", "Pendentes"),
    ("em_andamento", "Em andamento"),
    ("concluidas", "Concluídas"),
    ("canceladas", "Canceladas"),
    ("atrasadas", "Atrasadas"),
    ("hoje", "☀️ Para hoje"),
    ("proximos_dias", "Próximos dias"),
]

SORT_OPTIONS = {
    "Data prevista": "due_date",
    "Prioridade": "priority",
    "Data de cadastro": "created_at",
    "Última atualização": "updated_at",
}


class SchedulesView(ctk.CTkFrame):
    """
    Tela do Gerenciador de Tarefas e Agendamentos.
    Mantém o nome `SchedulesView` e assinatura compatível com `MainWindow`.
    """

    def __init__(
        self,
        master,
        current_user: User,
        schedule_service: Optional[ScheduleService] = None,
        on_open_diary_date: Optional[Callable[[str, int], None]] = None,
        task_service: Optional[TaskService] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.schedule_service = schedule_service
        self.on_open_diary_date = on_open_diary_date

        db_path = (
            task_service.db_path
            if task_service is not None
            else (schedule_service.db_path if schedule_service is not None else config.DB_PATH)
        )
        self.task_service = task_service or TaskService(db_path=db_path)

        # Estado de filtros, ordenação e seleção
        self.current_tab: str = "todas"
        self.current_sort_by: str = "due_date"
        self.current_sort_desc: bool = False
        self.selected_task_id: Optional[int] = None
        self.history_descending: bool = False
        self._tasks_cache: List[Task] = []
        self._card_frames: Dict[int, ctk.CTkFrame] = {}
        self._tab_buttons: Dict[str, ctk.CTkButton] = {}
        self._summary_labels: Dict[str, ctk.CTkLabel] = {}
        self._search_after_id: Optional[str] = None
        self._updating_detail_controls: bool = False

        self._status_label_to_key = {v: k for k, v in STATUS_LABELS.items()}
        self._prio_label_to_key = {v: k for k, v in PRIORITY_LABELS.items()}

        self._build_ui()
        self.refresh()

    def destroy(self):
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
            self._search_after_id = None
        super().destroy()

    # ==========================================================================
    # CONSTRUÇÃO DA INTERFACE
    # ==========================================================================

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # Cabeçalho
        self.grid_rowconfigure(1, weight=0)  # Cards de indicadores
        self.grid_rowconfigure(2, weight=0)  # Abas + pesquisa/filtros
        self.grid_rowconfigure(3, weight=1)  # Split-view (Lista | Detalhes)

        # --- ROW 0: CABEÇALHO ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))

        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            title_col,
            text="✅ Agendamentos & Tarefas",
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_col,
            text="Organize suas atividades, acompanhe o andamento passo a passo e receba lembretes no Windows.",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        ).pack(anchor="w", pady=(1, 0))

        actions_hdr = ctk.CTkFrame(header, fg_color="transparent")
        actions_hdr.pack(side="right")

        ctk.CTkButton(
            actions_hdr,
            text="🔔 Testar Aviso",
            width=124,
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark"],
            hover_color=config.COLORS["card_dark_alt"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._handle_test_notification,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            actions_hdr,
            text="➕ Nova Tarefa",
            width=142,
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._handle_new_task,
        ).pack(side="left")

        # --- ROW 1: INDICADORES DE PRODUTIVIDADE ---
        cards_row = ctk.CTkFrame(self, fg_color="transparent")
        cards_row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))
        for i in range(5):
            cards_row.grid_columnconfigure(i, weight=1, uniform="kpi")

        kpis = [
            ("pendentes", "📋 Pendentes", ("#2563EB", "#3B82F6")),
            ("em_andamento", "🚀 Em andamento", ("#7C3AED", "#8B5CF6")),
            ("concluidas", "✅ Concluídas", ("#059669", "#10B981")),
            ("atrasadas", "🚨 Atrasadas", ("#DC2626", "#EF4444")),
            ("hoje", "☀️ Para hoje", ("#D97706", "#F59E0B")),
        ]
        for idx, (key, label, accent) in enumerate(kpis):
            pad_l = 0 if idx == 0 else 4
            pad_r = 0 if idx == len(kpis) - 1 else 4
            card = ctk.CTkFrame(
                cards_row,
                corner_radius=10,
                fg_color=config.COLORS["card_dark"],
                border_width=1,
                border_color=config.COLORS["border_dark"],
                cursor="hand2",
            )
            card.grid(row=0, column=idx, sticky="ew", padx=(pad_l, pad_r))

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=12, pady=8)

            lbl_val = ctk.CTkLabel(
                inner,
                text="0",
                font=ctk.CTkFont(size=20, weight="bold"),
                text_color=accent,
                anchor="w",
            )
            lbl_val.pack(side="left", padx=(0, 8))

            lbl_name = ctk.CTkLabel(
                inner,
                text=label,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=config.COLORS["text_dark"],
                anchor="w",
            )
            lbl_name.pack(side="left", fill="x", expand=True)

            self._summary_labels[key] = lbl_val
            for w in (card, inner, lbl_val, lbl_name):
                w.bind("<Button-1>", lambda _e, k=key: self._set_tab(k))

        # --- ROW 2: ABAS + PESQUISA, FILTROS E ORDENAÇÃO ---
        controls_card = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        controls_card.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))

        # 2.1 Abas de visualização
        tabs_row = ctk.CTkFrame(controls_card, fg_color="transparent")
        tabs_row.pack(fill="x", padx=10, pady=(8, 6))

        for tab_key, tab_title in TAB_DEFINITIONS:
            btn = ctk.CTkButton(
                tabs_row,
                text=tab_title,
                height=30,
                width=74,
                corner_radius=7,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="transparent",
                hover_color=config.COLORS["card_dark_alt"],
                text_color=config.COLORS["text_dark"],
                command=lambda k=tab_key: self._set_tab(k),
            )
            btn.pack(side="left", padx=(0, 4))
            self._tab_buttons[tab_key] = btn

        # 2.2 Pesquisa + Filtros + Ordenação
        filters_row = ctk.CTkFrame(controls_card, fg_color="transparent")
        filters_row.pack(fill="x", padx=10, pady=(0, 8))

        self.entry_search = ctk.CTkEntry(
            filters_row,
            height=32,
            placeholder_text="🔍 Pesquisar por título, descrição ou andamento...",
            corner_radius=7,
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_search.bind("<KeyRelease>", self._on_search_key_release)
        self.entry_search.bind("<Return>", lambda _e: self.refresh())

        self.opt_filter_priority = ctk.CTkOptionMenu(
            filters_row,
            values=["Prioridade: Todas"] + list(PRIORITY_LABELS.values()),
            width=136,
            height=32,
            corner_radius=7,
            font=ctk.CTkFont(size=11),
            command=lambda _v: self.refresh(),
        )
        self.opt_filter_priority.set("Prioridade: Todas")
        self.opt_filter_priority.pack(side="left", padx=(0, 5))

        self.opt_filter_status = ctk.CTkOptionMenu(
            filters_row,
            values=["Status: Todos"] + list(STATUS_LABELS.values()),
            width=128,
            height=32,
            corner_radius=7,
            font=ctk.CTkFont(size=11),
            command=lambda _v: self.refresh(),
        )
        self.opt_filter_status.set("Status: Todos")
        self.opt_filter_status.pack(side="left", padx=(0, 5))

        self.entry_date_from = ctk.CTkEntry(
            filters_row,
            width=96,
            height=32,
            placeholder_text="De DD/MM/AA",
            corner_radius=7,
            font=ctk.CTkFont(size=11),
        )
        self.entry_date_from.pack(side="left", padx=(0, 4))
        self.entry_date_from.bind("<Return>", lambda _e: self.refresh())
        self.entry_date_from.bind("<FocusOut>", lambda _e: self.refresh())

        self.entry_date_to = ctk.CTkEntry(
            filters_row,
            width=96,
            height=32,
            placeholder_text="Até DD/MM/AA",
            corner_radius=7,
            font=ctk.CTkFont(size=11),
        )
        self.entry_date_to.pack(side="left", padx=(0, 5))
        self.entry_date_to.bind("<Return>", lambda _e: self.refresh())
        self.entry_date_to.bind("<FocusOut>", lambda _e: self.refresh())

        self.opt_sort_by = ctk.CTkOptionMenu(
            filters_row,
            values=list(SORT_OPTIONS.keys()),
            width=134,
            height=32,
            corner_radius=7,
            font=ctk.CTkFont(size=11),
            command=self._on_sort_changed,
        )
        self.opt_sort_by.set("Data prevista")
        self.opt_sort_by.pack(side="left", padx=(0, 4))

        self.btn_sort_dir = ctk.CTkButton(
            filters_row,
            text="↑",
            width=30,
            height=32,
            corner_radius=7,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._toggle_sort_direction,
        )
        self.btn_sort_dir.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            filters_row,
            text="Limpar",
            width=60,
            height=32,
            corner_radius=7,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["text_muted"],
            command=self._clear_filters,
        ).pack(side="left")

        # --- ROW 3: SPLIT-VIEW (LISTA À ESQUERDA | DETALHES À DIREITA) ---
        split = ctk.CTkFrame(self, fg_color="transparent")
        split.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 14))
        split.grid_rowconfigure(0, weight=1)
        split.grid_columnconfigure(0, weight=56, minsize=430)
        split.grid_columnconfigure(1, weight=44, minsize=380)

        # Painel Esquerdo: Lista de Tarefas
        self.list_panel = ctk.CTkFrame(
            split,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.list_panel.grid_columnconfigure(0, weight=1)
        self.list_panel.grid_rowconfigure(0, weight=0)
        self.list_panel.grid_rowconfigure(1, weight=0)
        self.list_panel.grid_rowconfigure(2, weight=1)

        list_hdr = ctk.CTkFrame(self.list_panel, fg_color="transparent")
        list_hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))

        self.lbl_list_title = ctk.CTkLabel(
            list_hdr,
            text="📋 Todas as Tarefas",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        self.lbl_list_title.pack(side="left")

        self.lbl_list_count = ctk.CTkLabel(
            list_hdr,
            text="0 tarefas",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_list_count.pack(side="right")

        # Banner de destaque "Tarefas do Dia" (exibido dinamicamente)
        self.today_banner = ctk.CTkFrame(
            self.list_panel,
            corner_radius=8,
            fg_color=("#FEF3C7", "#2B2111"),
            border_width=1,
            border_color=("#F59E0B", "#92400E"),
        )
        self.lbl_today_banner = ctk.CTkLabel(
            self.today_banner,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#92400E", "#FCD34D"),
            anchor="w",
        )
        self.lbl_today_banner.pack(side="left", padx=10, pady=6, fill="x", expand=True)

        self.btn_today_focus = ctk.CTkButton(
            self.today_banner,
            text="Ver hoje",
            width=74,
            height=24,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#D97706", "#B45309"),
            hover_color=("#B45309", "#D97706"),
            text_color="#FFFFFF",
            command=lambda: self._set_tab("hoje"),
        )
        self.btn_today_focus.pack(side="right", padx=8, pady=5)

        self.list_scroll = ctk.CTkScrollableFrame(
            self.list_panel,
            fg_color="transparent",
            corner_radius=0,
        )
        self.list_scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 10))

        # Painel Direito: Detalhes da Tarefa
        self.detail_panel = ctk.CTkFrame(
            split,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.detail_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self.detail_panel.grid_columnconfigure(0, weight=1)
        self.detail_panel.grid_rowconfigure(0, weight=1)

        self.detail_scroll = ctk.CTkScrollableFrame(
            self.detail_panel,
            fg_color="transparent",
            corner_radius=0,
        )
        self.detail_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    # ==========================================================================
    # FILTROS, ABAS E ORDENAÇÃO
    # ==========================================================================

    def _set_tab(self, tab_key: str):
        self.current_tab = tab_key
        self.refresh()

    def _on_search_key_release(self, _event=None):
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
        self._search_after_id = self.after(180, self.refresh)

    def _on_sort_changed(self, selected_label: str):
        self.current_sort_by = SORT_OPTIONS.get(selected_label, "due_date")
        if self.current_sort_by in ("created_at", "updated_at"):
            self.current_sort_desc = True
        else:
            self.current_sort_desc = False
        self.btn_sort_dir.configure(text="↓" if self.current_sort_desc else "↑")
        self.refresh()

    def _toggle_sort_direction(self):
        self.current_sort_desc = not self.current_sort_desc
        self.btn_sort_dir.configure(text="↓" if self.current_sort_desc else "↑")
        self.refresh()

    def _clear_filters(self):
        self.current_tab = "todas"
        self.entry_search.delete(0, "end")
        self.opt_filter_priority.set("Prioridade: Todas")
        self.opt_filter_status.set("Status: Todos")
        self.entry_date_from.delete(0, "end")
        self.entry_date_to.delete(0, "end")
        self.opt_sort_by.set("Data prevista")
        self.current_sort_by = "due_date"
        self.current_sort_desc = False
        self.btn_sort_dir.configure(text="↑")
        self.refresh()

    def _update_tab_styles(self, counts: Dict[str, int]):
        count_map = {
            "todas": counts["total"],
            "pendentes": counts["pendentes"],
            "em_andamento": counts["em_andamento"],
            "concluidas": counts["concluidas"],
            "canceladas": counts["canceladas"],
            "atrasadas": counts["atrasadas"],
            "hoje": counts["hoje"],
            "proximos_dias": counts["proximos_dias"],
        }
        for key, base_title in TAB_DEFINITIONS:
            btn = self._tab_buttons.get(key)
            if not btn:
                continue
            cnt = count_map.get(key, 0)
            btn.configure(text=f"{base_title} ({cnt})")
            if key == self.current_tab:
                btn.configure(
                    fg_color=config.COLORS["primary"],
                    hover_color=config.COLORS["primary_hover"],
                    text_color="#FFFFFF",
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    hover_color=config.COLORS["card_dark_alt"],
                    text_color=config.COLORS["text_dark"],
                )

    def _get_active_filters(self) -> Dict[str, str]:
        prio_val = self.opt_filter_priority.get()
        prio_filter = "" if prio_val.startswith("Prioridade:") else self._prio_label_to_key.get(prio_val, "")

        status_val = self.opt_filter_status.get()
        status_filter = "" if status_val.startswith("Status:") else self._status_label_to_key.get(status_val, "")

        raw_from = self.entry_date_from.get().strip()
        date_from = parse_date_input(raw_from) if raw_from else ""
        if date_from is None:
            date_from = ""

        raw_to = self.entry_date_to.get().strip()
        date_to = parse_date_input(raw_to) if raw_to else ""
        if date_to is None:
            date_to = ""

        return {
            "search_query": self.entry_search.get().strip(),
            "priority_filter": prio_filter,
            "status_filter": status_filter,
            "date_from": date_from,
            "date_to": date_to,
        }

    # ==========================================================================
    # ATUALIZAÇÃO DA TELA E RENDERIZAÇÃO DA LISTAGEM
    # ==========================================================================

    def refresh(self):
        """Recarrega indicadores, listagem filtrada e painel de detalhes."""
        if not self.winfo_exists():
            return

        counts = self.task_service.get_summary_counts(self.current_user.id)
        for key, lbl in self._summary_labels.items():
            lbl.configure(text=str(counts.get(key, 0)))

        self._update_tab_styles(counts)

        # Banner de destaque "Para hoje"
        today_count = counts.get("hoje", 0)
        if today_count > 0 and self.current_tab != "hoje":
            plural = "tarefa prevista" if today_count == 1 else "tarefas previstas"
            self.lbl_today_banner.configure(
                text=f"☀️ Foco do Dia: você tem {today_count} {plural} para hoje!"
            )
            self.today_banner.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 4))
        else:
            self.today_banner.grid_forget()

        # Título contextual da listagem
        tab_title_map = {
            "todas": "📋 Todas as Tarefas",
            "pendentes": "⏳ Minhas Tarefas Pendentes",
            "em_andamento": "🚀 Tarefas em Andamento",
            "concluidas": "✅ Tarefas Concluídas",
            "canceladas": "🚫 Tarefas Canceladas",
            "atrasadas": "🚨 Tarefas Atrasadas",
            "hoje": "☀️ Foco de Hoje — Tarefas do Dia",
            "proximos_dias": "🗓️ Próximos Dias",
        }
        self.lbl_list_title.configure(text=tab_title_map.get(self.current_tab, "📋 Tarefas"))

        flt = self._get_active_filters()
        tasks = self.task_service.list_tasks(
            user_id=self.current_user.id,
            tab=self.current_tab,
            search_query=flt["search_query"],
            status_filter=flt["status_filter"] or None,
            priority_filter=flt["priority_filter"] or None,
            date_from=flt["date_from"],
            date_to=flt["date_to"],
            sort_by=self.current_sort_by,
            sort_desc=self.current_sort_desc,
        )
        self._tasks_cache = tasks
        self.lbl_list_count.configure(
            text=f"{len(tasks)} {'tarefa' if len(tasks) == 1 else 'tarefas'}"
        )

        # Renderiza lista de cards
        for child in self.list_scroll.winfo_children():
            child.destroy()
        self._card_frames.clear()

        if not tasks:
            self._render_empty_list_state()
        else:
            for task in tasks:
                self._render_task_card(task)

        # Mantém tarefa selecionada se ainda existir no banco; senão seleciona a 1ª da lista
        selected_task = None
        if self.selected_task_id is not None:
            selected_task = self.task_service.get_task_by_id(
                self.selected_task_id, self.current_user.id, include_details=True
            )
        if selected_task is None and tasks:
            self.selected_task_id = tasks[0].id
            selected_task = self.task_service.get_task_by_id(
                self.selected_task_id, self.current_user.id, include_details=True
            )
        elif selected_task is None:
            self.selected_task_id = None

        self._highlight_selected_card()
        self._render_task_details(selected_task)

    def _render_empty_list_state(self):
        box = ctk.CTkFrame(
            self.list_scroll,
            corner_radius=10,
            fg_color=config.COLORS["card_dark_alt"],
        )
        box.pack(fill="x", padx=6, pady=24)

        ctk.CTkLabel(
            box,
            text="✨ Nenhuma tarefa encontrada nesta visualização",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=config.COLORS["text_dark"],
        ).pack(pady=(22, 4))

        ctk.CTkLabel(
            box,
            text="Crie uma nova tarefa ou ajuste os filtros/abas acima.",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
        ).pack(pady=(0, 14))

        ctk.CTkButton(
            box,
            text="➕ Cadastrar Nova Tarefa",
            height=34,
            corner_radius=8,
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._handle_new_task,
        ).pack(pady=(0, 20))

    def _get_task_accent_color(self, task: Task):
        if task.is_overdue():
            return ("#DC2626", "#EF4444")
        if task.status == "concluida":
            return ("#059669", "#10B981")
        if task.status == "cancelada":
            return ("#64748B", "#64748B")
        if task.priority == "urgente":
            return ("#DC2626", "#EF4444")
        if task.status == "em_andamento":
            return ("#7C3AED", "#8B5CF6")
        if task.is_due_today():
            return ("#D97706", "#F59E0B")
        return PRIORITY_COLORS.get(task.priority, ("#2563EB", "#3B82F6"))

    def _render_task_card(self, task: Task):
        accent = self._get_task_accent_color(task)
        is_selected = task.id == self.selected_task_id
        overdue = task.is_overdue()
        due_today = task.is_due_today()

        card = ctk.CTkFrame(
            self.list_scroll,
            corner_radius=10,
            fg_color=config.COLORS["card_dark_alt"],
            border_width=2 if is_selected else 1,
            border_color=config.COLORS["primary"] if is_selected else config.COLORS["border_dark"],
            cursor="hand2",
        )
        card.pack(fill="x", padx=4, pady=4)
        self._card_frames[task.id] = card

        # Faixa lateral colorida de indicador visual
        bar = ctk.CTkFrame(card, width=5, corner_radius=3, fg_color=accent)
        bar.pack(side="left", fill="y", padx=(6, 8), pady=8)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=8)

        # --- Linha 1: Botão rápido concluir + Título + Seletor rápido de Status ---
        top_row = ctk.CTkFrame(body, fg_color="transparent")
        top_row.pack(fill="x")

        toggle_icon = "✓" if task.is_completed else "○"
        toggle_fg = ("#059669", "#10B981") if task.is_completed else "transparent"
        toggle_txt = "#FFFFFF" if task.is_completed else config.COLORS["text_muted"]
        btn_check = ctk.CTkButton(
            top_row,
            text=toggle_icon,
            width=26,
            height=26,
            corner_radius=13,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=toggle_fg,
            hover_color=("#059669", "#10B981"),
            border_width=1,
            border_color=("#059669", "#10B981") if task.is_completed else config.COLORS["border_dark"],
            text_color=toggle_txt,
            command=lambda t=task: self._handle_quick_toggle_complete(t),
        )
        btn_check.pack(side="left", padx=(0, 8))

        title_font = ctk.CTkFont(
            size=13,
            weight="bold",
            overstrike=task.is_completed or task.is_canceled,
        )
        title_color = (
            config.COLORS["text_muted"]
            if (task.is_completed or task.is_canceled)
            else config.COLORS["text_dark"]
        )
        lbl_title = ctk.CTkLabel(
            top_row,
            text=task.title,
            font=title_font,
            text_color=title_color,
            anchor="w",
        )
        lbl_title.pack(side="left", fill="x", expand=True, padx=(0, 6))

        # Seletor rápido de Status diretamente na listagem
        opt_card_status = ctk.CTkOptionMenu(
            top_row,
            values=list(STATUS_LABELS.values()),
            width=118,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=STATUS_COLORS.get(task.status, ("#2563EB", "#3B82F6")),
            button_color=STATUS_COLORS.get(task.status, ("#2563EB", "#3B82F6")),
            button_hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=lambda val, tid=task.id: self._handle_inline_status_change(tid, val),
        )
        opt_card_status.set(task.status_label)
        opt_card_status.pack(side="right")

        # --- Linha 2: Badges (Prioridade, Atrasada, Hoje, Categoria, Lembrete) ---
        badges_row = ctk.CTkFrame(body, fg_color="transparent")
        badges_row.pack(fill="x", pady=(5, 3))

        self._make_pill(
            badges_row,
            f"{PRIORITY_ICONS.get(task.priority, '🔵')} {task.priority_label}",
            PRIORITY_COLORS.get(task.priority, ("#2563EB", "#3B82F6")),
        )

        if overdue:
            self._make_pill(badges_row, "⚠️ Atrasada", ("#DC2626", "#EF4444"))
        elif due_today:
            self._make_pill(badges_row, "☀️ Hoje", ("#D97706", "#F59E0B"))

        if task.category:
            self._make_pill(badges_row, f"🏷️ {task.category}", ("#475569", "#475569"))

        if task.reminder_enabled and task.active_reminders_count > 0:
            self._make_pill(badges_row, "🔔 Lembrete", ("#0284C7", "#0EA5E9"))

        if task.history_count > 0:
            self._make_pill(
                badges_row,
                f"💬 {task.history_count}",
                ("#64748B", "#475569"),
            )

        # --- Linha 3: Data Prevista + Última Atualização ---
        meta_row = ctk.CTkFrame(body, fg_color="transparent")
        meta_row.pack(fill="x", pady=(2, 0))

        due_color = ("#DC2626", "#F87171") if overdue else config.COLORS["text_muted"]
        lbl_due = ctk.CTkLabel(
            meta_row,
            text=f"📅 Previsto: {task.due_display}",
            font=ctk.CTkFont(size=11, weight="bold" if (overdue or due_today) else "normal"),
            text_color=due_color,
            anchor="w",
        )
        lbl_due.pack(side="left", padx=(0, 12))

        last_note = (task.last_update_note or "").replace("\n", " ").strip()
        if len(last_note) > 48:
            last_note = last_note[:48].rstrip() + "..."
        last_txt = f"🕒 Atualizado: {task.last_update_br}"
        if last_note:
            last_txt += f" — {last_note}"

        lbl_last = ctk.CTkLabel(
            meta_row,
            text=last_txt,
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        lbl_last.pack(side="left", fill="x", expand=True)

        # Clique em qualquer área do card (exceto botão/menu) seleciona a tarefa
        for clickable in (card, bar, body, top_row, lbl_title, badges_row, meta_row, lbl_due, lbl_last):
            clickable.bind("<Button-1>", lambda _e, tid=task.id: self.select_task(tid))

    @staticmethod
    def _make_pill(parent, text: str, fg_color):
        pill = ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=fg_color,
            text_color="#FFFFFF",
            corner_radius=6,
            padx=7,
            pady=2,
        )
        pill.pack(side="left", padx=(0, 5))
        return pill

    def _highlight_selected_card(self):
        for tid, card in self._card_frames.items():
            if not card.winfo_exists():
                continue
            if tid == self.selected_task_id:
                card.configure(border_width=2, border_color=config.COLORS["primary"])
            else:
                card.configure(border_width=1, border_color=config.COLORS["border_dark"])

    def select_task(self, task_id: int):
        """Seleciona uma tarefa na listagem e exibe seus detalhes completos à direita."""
        self.selected_task_id = task_id
        self._highlight_selected_card()
        task = self.task_service.get_task_by_id(task_id, self.current_user.id, include_details=True)
        self._render_task_details(task)

    # ==========================================================================
    # PAINEL DE DETALHES DA TAREFA (INFORMAÇÕES GERAIS, AÇÕES E ANDAMENTO)
    # ==========================================================================

    def _render_task_details(self, task: Optional[Task]):
        for child in self.detail_scroll.winfo_children():
            child.destroy()

        if task is None:
            empty = ctk.CTkFrame(self.detail_scroll, fg_color="transparent")
            empty.pack(fill="both", expand=True, padx=16, pady=60)

            ctk.CTkLabel(
                empty,
                text="📌 Detalhes da Tarefa",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=config.COLORS["text_dark"],
            ).pack(pady=(0, 6))

            ctk.CTkLabel(
                empty,
                text="Clique em uma tarefa na listagem ao lado para consultar todas as informações,\nacompanhar o histórico cronológico e registrar novas atualizações de andamento.",
                font=ctk.CTkFont(size=12),
                text_color=config.COLORS["text_muted"],
                justify="center",
            ).pack(pady=(0, 16))

            ctk.CTkButton(
                empty,
                text="➕ Criar Primeira Tarefa",
                height=36,
                corner_radius=8,
                fg_color=config.COLORS["primary"],
                hover_color=config.COLORS["primary_hover"],
                text_color="#FFFFFF",
                command=self._handle_new_task,
            ).pack()
            return

        # ======================================================================
        # SEÇÃO 1: INFORMAÇÕES GERAIS
        # ======================================================================
        info_card = ctk.CTkFrame(
            self.detail_scroll,
            corner_radius=10,
            fg_color=config.COLORS["card_dark_alt"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        info_card.pack(fill="x", padx=4, pady=(2, 10))

        info_hdr = ctk.CTkFrame(info_card, fg_color="transparent")
        info_hdr.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            info_hdr,
            text="📋 Informações Gerais",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_muted"],
        ).pack(side="left")

        ctk.CTkLabel(
            info_hdr,
            text=f"ID #{task.id}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=config.COLORS["text_muted"],
        ).pack(side="right")

        ctk.CTkLabel(
            info_card,
            text=task.title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", padx=12, pady=(2, 6))

        # Badges de estado
        det_badges = ctk.CTkFrame(info_card, fg_color="transparent")
        det_badges.pack(fill="x", padx=12, pady=(0, 8))

        self._make_pill(
            det_badges,
            f"{STATUS_ICONS.get(task.status, '•')} {task.status_label}",
            STATUS_COLORS.get(task.status, ("#2563EB", "#3B82F6")),
        )
        self._make_pill(
            det_badges,
            f"{PRIORITY_ICONS.get(task.priority, '🔵')} Prioridade {task.priority_label}",
            PRIORITY_COLORS.get(task.priority, ("#2563EB", "#3B82F6")),
        )
        if task.is_overdue():
            self._make_pill(det_badges, "⚠️ Atrasada", ("#DC2626", "#EF4444"))
        elif task.is_due_today():
            self._make_pill(det_badges, "☀️ Vence Hoje", ("#D97706", "#F59E0B"))
        if task.category:
            self._make_pill(det_badges, f"🏷️ {task.category}", ("#475569", "#475569"))

        # Descrição inicial
        desc_box = ctk.CTkFrame(
            info_card,
            corner_radius=8,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        desc_box.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            desc_box,
            text=task.description if task.description else "Sem descrição inicial informada.",
            font=ctk.CTkFont(size=12, slant="italic" if not task.description else "roman"),
            text_color=config.COLORS["text_dark"] if task.description else config.COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=400,
        ).pack(fill="x", padx=10, pady=8)

        # Grade de datas e metadados
        meta_grid = ctk.CTkFrame(info_card, fg_color="transparent")
        meta_grid.pack(fill="x", padx=12, pady=(0, 10))
        meta_grid.grid_columnconfigure(0, weight=1)
        meta_grid.grid_columnconfigure(1, weight=1)

        meta_items = [
            ("📅 Cadastro:", task.created_at_br or "-"),
            ("🚀 Início:", task.start_date_br or "-"),
            ("🎯 Data prevista:", task.due_display),
            (
                "✅ Concluída em:" if task.completed_at else "🕒 Última atualização:",
                task.completed_at_br if task.completed_at else (task.last_update_br or "-"),
            ),
        ]
        for idx, (lbl_k, lbl_v) in enumerate(meta_items):
            r_idx, c_idx = divmod(idx, 2)
            cell = ctk.CTkFrame(meta_grid, fg_color="transparent")
            cell.grid(row=r_idx, column=c_idx, sticky="ew", padx=(0, 6), pady=2)
            ctk.CTkLabel(
                cell,
                text=lbl_k,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLORS["text_muted"],
            ).pack(side="left", padx=(0, 4))
            ctk.CTkLabel(
                cell,
                text=lbl_v,
                font=ctk.CTkFont(size=11),
                text_color=config.COLORS["text_dark"],
            ).pack(side="left")

        # Lembretes vinculados
        if task.reminders:
            rem_box = ctk.CTkFrame(
                info_card,
                corner_radius=8,
                fg_color=config.COLORS["card_dark"],
            )
            rem_box.pack(fill="x", padx=12, pady=(0, 10))

            ctk.CTkLabel(
                rem_box,
                text="🔔 Lembretes configurados:",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLORS["text_dark"],
                anchor="w",
            ).pack(fill="x", padx=10, pady=(6, 2))

            for rem in task.reminders:
                status_rem = " (enviado)" if rem.is_sent else (" (pausado)" if not rem.is_active else " (ativo)")
                ctk.CTkLabel(
                    rem_box,
                    text=f"• {rem.summary_text}{status_rem}",
                    font=ctk.CTkFont(size=11),
                    text_color=config.COLORS["text_muted"],
                    anchor="w",
                ).pack(fill="x", padx=14, pady=(0, 3))

        # ======================================================================
        # SEÇÃO 2: AÇÕES
        # ======================================================================
        actions_card = ctk.CTkFrame(
            self.detail_scroll,
            corner_radius=10,
            fg_color=config.COLORS["card_dark_alt"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        actions_card.pack(fill="x", padx=4, pady=(0, 10))

        ctk.CTkLabel(
            actions_card,
            text="⚡ Ações",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 6))

        # Linha 1 de ações: Alterar Status + Concluir/Reabrir
        status_act_row = ctk.CTkFrame(actions_card, fg_color="transparent")
        status_act_row.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkLabel(
            status_act_row,
            text="Status:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        ).pack(side="left", padx=(0, 6))

        self.detail_status_menu = ctk.CTkOptionMenu(
            status_act_row,
            values=list(STATUS_LABELS.values()),
            width=142,
            height=30,
            corner_radius=6,
            command=lambda val, tid=task.id: self._handle_detail_status_change(tid, val),
        )
        self._updating_detail_controls = True
        self.detail_status_menu.set(task.status_label)
        self._updating_detail_controls = False
        self.detail_status_menu.pack(side="left", padx=(0, 8))

        if task.is_open:
            ctk.CTkButton(
                status_act_row,
                text="✅ Concluir Tarefa",
                height=30,
                corner_radius=6,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=("#059669", "#10B981"),
                hover_color=("#047857", "#059669"),
                text_color="#FFFFFF",
                command=lambda t=task: self._handle_complete_task(t),
            ).pack(side="left", fill="x", expand=True)
        else:
            ctk.CTkButton(
                status_act_row,
                text="🔄 Reabrir Tarefa",
                height=30,
                corner_radius=6,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=config.COLORS["primary"],
                hover_color=config.COLORS["primary_hover"],
                text_color="#FFFFFF",
                command=lambda t=task: self._handle_reopen_task(t),
            ).pack(side="left", fill="x", expand=True)

        # Linha 2 de ações: Editar, Notificar, Diário, Excluir
        btns_row = ctk.CTkFrame(actions_card, fg_color="transparent")
        btns_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkButton(
            btns_row,
            text="✏️ Editar",
            width=82,
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=config.COLORS["card_dark"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=lambda t=task: self._handle_edit_task(t),
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btns_row,
            text="🔔 Notificar",
            width=88,
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=lambda t=task: self._handle_manual_notify(t),
        ).pack(side="left", padx=(0, 6))

        if task.due_date and self.on_open_diary_date:
            ctk.CTkButton(
                btns_row,
                text="📓 Diário",
                width=78,
                height=30,
                corner_radius=6,
                font=ctk.CTkFont(size=11),
                fg_color=config.COLORS["card_dark"],
                hover_color=config.COLORS["primary"],
                text_color=config.COLORS["button_text"],
                command=lambda d=task.due_date: self.on_open_diary_date(d, self.current_user.id),
            ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btns_row,
            text="🗑️ Excluir",
            width=82,
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=config.COLORS["card_dark"],
            hover_color=config.COLORS["danger"],
            text_color=config.COLORS["button_text"],
            command=lambda t=task: self._handle_delete_task(t),
        ).pack(side="right")

        # ======================================================================
        # SEÇÃO 3: ANDAMENTO E HISTÓRICO CRONOLÓGICO
        # ======================================================================
        progress_card = ctk.CTkFrame(
            self.detail_scroll,
            corner_radius=10,
            fg_color=config.COLORS["card_dark_alt"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        progress_card.pack(fill="x", padx=4, pady=(0, 6))

        prog_hdr = ctk.CTkFrame(progress_card, fg_color="transparent")
        prog_hdr.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            prog_hdr,
            text=f"📝 Andamento e Histórico ({len(task.history)})",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        ).pack(side="left")

        order_lbl = "Mais recentes ↓" if self.history_descending else "Cronológico ↑"
        ctk.CTkButton(
            prog_hdr,
            text=order_lbl,
            width=108,
            height=24,
            corner_radius=6,
            font=ctk.CTkFont(size=10),
            fg_color=config.COLORS["card_dark"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["text_muted"],
            command=self._toggle_history_order,
        ).pack(side="right")

        ctk.CTkLabel(
            progress_card,
            text="Adicionar nova atualização ou observação (Ctrl+Enter para registrar):",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", padx=12, pady=(2, 4))

        self.txt_new_update = ctk.CTkTextbox(
            progress_card,
            height=74,
            corner_radius=8,
            border_width=1,
            border_color=config.COLORS["border_dark"],
            fg_color=config.COLORS["card_dark"],
            text_color=config.COLORS["text_dark"],
        )
        self.txt_new_update.pack(fill="x", padx=12, pady=(0, 6))
        self.txt_new_update.bind(
            "<Control-Return>", lambda _e, tid=task.id: self._handle_add_progress_update(tid)
        )

        add_bar = ctk.CTkFrame(progress_card, fg_color="transparent")
        add_bar.pack(fill="x", padx=12, pady=(0, 10))

        self.opt_update_status = ctk.CTkOptionMenu(
            add_bar,
            values=["Manter status atual"] + list(STATUS_LABELS.values()),
            width=155,
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
        )
        self.opt_update_status.set("Manter status atual")
        self.opt_update_status.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            add_bar,
            text="➕ Registrar Atualização",
            height=32,
            corner_radius=7,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=lambda tid=task.id: self._handle_add_progress_update(tid),
        ).pack(side="left", fill="x", expand=True)

        # Histórico completo de atualizações
        hist_entries = list(reversed(task.history)) if self.history_descending else list(task.history)

        if not hist_entries:
            ctk.CTkLabel(
                progress_card,
                text="Nenhuma atualização registrada ainda.",
                font=ctk.CTkFont(size=11, slant="italic"),
                text_color=config.COLORS["text_muted"],
            ).pack(padx=12, pady=(4, 12))
        else:
            timeline = ctk.CTkFrame(progress_card, fg_color="transparent")
            timeline.pack(fill="x", padx=12, pady=(0, 12))

            for entry in hist_entries:
                st_key = normalize_status(entry.status_at_time)
                st_color = STATUS_COLORS.get(st_key, ("#2563EB", "#3B82F6"))

                item_card = ctk.CTkFrame(
                    timeline,
                    corner_radius=8,
                    fg_color=config.COLORS["card_dark"],
                    border_width=1,
                    border_color=config.COLORS["border_dark"],
                )
                item_card.pack(fill="x", pady=3)

                dot_bar = ctk.CTkFrame(item_card, width=4, corner_radius=2, fg_color=st_color)
                dot_bar.pack(side="left", fill="y", padx=(6, 8), pady=6)

                item_body = ctk.CTkFrame(item_card, fg_color="transparent")
                item_body.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=6)

                item_top = ctk.CTkFrame(item_body, fg_color="transparent")
                item_top.pack(fill="x")

                ctk.CTkLabel(
                    item_top,
                    text=f"🕒 {entry.created_at_br}",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=config.COLORS["text_muted"],
                ).pack(side="left")

                ctk.CTkLabel(
                    item_top,
                    text=entry.status_label,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color=st_color,
                    text_color="#FFFFFF",
                    corner_radius=5,
                    padx=6,
                    pady=1,
                ).pack(side="right")

                ctk.CTkLabel(
                    item_body,
                    text=entry.note,
                    font=ctk.CTkFont(size=12),
                    text_color=config.COLORS["text_dark"],
                    anchor="w",
                    justify="left",
                    wraplength=390,
                ).pack(fill="x", pady=(4, 0))

    def _toggle_history_order(self):
        self.history_descending = not self.history_descending
        if self.selected_task_id is not None:
            self.select_task(self.selected_task_id)

    # ==========================================================================
    # AÇÕES DO USUÁRIO
    # ==========================================================================

    def _handle_new_task(self):
        cats = self.task_service.list_categories(self.current_user.id)
        diag = TaskFormDialog(self, "Nova Tarefa", categories=cats)
        if not diag.result:
            return
        res = diag.result
        new_task, msg = self.task_service.create_task(
            user_id=self.current_user.id,
            title=res["title"],
            description=res["description"],
            start_date=res["start_date"],
            due_date=res["due_date"],
            due_time=res["due_time"],
            priority=res["priority"],
            status=res["status"],
            category=res["category"],
            reminder_enabled=res["reminder_enabled"],
            reminders=res["reminders"],
        )
        if new_task:
            self.selected_task_id = new_task.id
            self.refresh()
            show_message(self, "Sucesso", msg, kind="success")
        else:
            show_message(self, "Erro", msg, kind="danger")

    def _handle_edit_task(self, task: Task):
        fresh = self.task_service.get_task_by_id(task.id, self.current_user.id, include_details=True) or task
        cats = self.task_service.list_categories(self.current_user.id)
        diag = TaskFormDialog(self, f"Editar Tarefa #{fresh.id}", task=fresh, categories=cats)
        if not diag.result:
            return
        res = diag.result
        ok, msg = self.task_service.update_task(
            task_id=fresh.id,
            user_id=self.current_user.id,
            title=res["title"],
            description=res["description"],
            start_date=res["start_date"],
            due_date=res["due_date"],
            due_time=res["due_time"],
            priority=res["priority"],
            status=res["status"],
            category=res["category"],
            reminder_enabled=res["reminder_enabled"],
            reminders=res["reminders"],
        )
        if ok:
            self.selected_task_id = fresh.id
            self.refresh()
            show_message(self, "Sucesso", msg, kind="success")
        else:
            show_message(self, "Erro", msg, kind="danger")

    def _handle_quick_toggle_complete(self, task: Task):
        if task.is_completed:
            ok, msg = self.task_service.reopen_task(task.id, self.current_user.id, target_status="pendente")
        else:
            ok, msg = self.task_service.complete_task(task.id, self.current_user.id)
        if ok:
            self.selected_task_id = task.id
            self.refresh()
        else:
            show_message(self, "Erro", msg, kind="danger")

    def _handle_inline_status_change(self, task_id: int, status_label: str):
        new_status = self._status_label_to_key.get(status_label, "pendente")
        ok, msg = self.task_service.change_status(task_id, self.current_user.id, new_status)
        if ok:
            self.selected_task_id = task_id
            self.refresh()
        else:
            show_message(self, "Erro", msg, kind="danger")

    def _handle_detail_status_change(self, task_id: int, status_label: str):
        if self._updating_detail_controls:
            return
        self._handle_inline_status_change(task_id, status_label)

    def _handle_complete_task(self, task: Task):
        ok, msg = self.task_service.complete_task(task.id, self.current_user.id)
        if ok:
            self.selected_task_id = task.id
            self.refresh()
        else:
            show_message(self, "Erro", msg, kind="danger")

    def _handle_reopen_task(self, task: Task):
        ok, msg = self.task_service.reopen_task(task.id, self.current_user.id, target_status="em_andamento")
        if ok:
            self.selected_task_id = task.id
            self.refresh()
        else:
            show_message(self, "Erro", msg, kind="danger")

    def _handle_delete_task(self, task: Task):
        confirmed = ask_confirmation(
            self,
            "Excluir Tarefa",
            f"Deseja realmente excluir a tarefa '{task.title}'?\nTodo o histórico e lembretes desta tarefa serão removidos.",
            kind="danger",
        )
        if not confirmed:
            return
        ok, msg = self.task_service.delete_task(task.id, self.current_user.id)
        if ok:
            if self.selected_task_id == task.id:
                self.selected_task_id = None
            self.refresh()
        else:
            show_message(self, "Erro", msg, kind="danger")

    def _handle_add_progress_update(self, task_id: int):
        if not hasattr(self, "txt_new_update") or not self.txt_new_update.winfo_exists():
            return
        note_text = self.txt_new_update.get("1.0", "end-1c").strip()
        if not note_text:
            show_message(
                self,
                "Campo Vazio",
                "Digite uma informação ou observação de andamento antes de registrar.",
                kind="warning",
            )
            return

        chosen_status_lbl = self.opt_update_status.get()
        new_status = (
            None
            if chosen_status_lbl == "Manter status atual"
            else self._status_label_to_key.get(chosen_status_lbl)
        )

        entry, msg = self.task_service.add_progress_update(
            task_id=task_id,
            user_id=self.current_user.id,
            note=note_text,
            new_status=new_status,
        )
        if entry:
            self.selected_task_id = task_id
            self.refresh()
        else:
            show_message(self, "Erro", msg, kind="danger")

    def open_task_by_id(self, task_id: Optional[int]):
        """Abre e destaca diretamente a tarefa solicitada (ex.: ao clicar em notificação Toast)."""
        if task_id is None:
            self.refresh()
            return
        task = self.task_service.get_task_by_id(task_id, self.current_user.id, include_details=True)
        if task is None:
            task = self.task_service.get_task_by_legacy_schedule_id(task_id, self.current_user.id)
        if task is not None:
            self.current_tab = "todas"
            self.selected_task_id = task.id
        self.refresh()

    def open_schedule_by_id(self, schedule_id: Optional[int]):
        """Mantém compatibilidade com notificações do protocolo legado dailynotes://schedule/open."""
        self.open_task_by_id(schedule_id)

    def _handle_manual_notify(self, task: Task):
        preview = task.description[:120].replace("\n", " ") if task.description else ""
        msg = f"Prazo: {task.due_display} | Prioridade: {task.priority_label}"
        if preview:
            msg += f"\n{preview}"
        send_windows_notification(
            title=f"⏰ Tarefa DailyNotes: {task.title}",
            message=msg,
            play_sound=True,
            task_id=task.id,
        )
        show_message(
            self,
            "Notificação Enviada",
            "A notificação vinculada à tarefa foi disparada para a Central de Ações do Windows!",
            kind="info",
        )

    def _handle_test_notification(self):
        now_time = datetime.datetime.now().strftime("%H:%M")
        send_windows_notification(
            title="⏰ DailyNotes - Teste de Notificação",
            message=f"As notificações do Gerenciador de Tarefas estão funcionando às {now_time}!",
            play_sound=True,
        )
        show_message(
            self,
            "Notificação de Teste",
            "Aviso disparado para a Central de Ações do Windows!",
            kind="success",
        )
