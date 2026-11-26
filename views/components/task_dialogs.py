"""
Diálogo modal para Cadastro e Edição de Tarefas com suporte completo a:
- Título, descrição inicial, data de início, data prevista, horário opcional
- Prioridade (Baixa, Média, Alta, Urgente), Status (Pendente, Em andamento, Concluída, Cancelada)
- Categoria opcional com sugestões
- Configuração completa de lembretes/notificações (data/horário personalizados,
  aviso no dia do vencimento, aviso antecipado e lembrete de tarefa atrasada).
"""

import datetime
from typing import Any, Dict, List, Optional
import customtkinter as ctk

import config
from models.task import (
    ADVANCE_PRESETS,
    PRIORITY_LABELS,
    REPEAT_LABELS,
    STATUS_LABELS,
    Task,
    format_iso_date_br,
)
from utils.date_utils import get_today_iso, parse_date_input
from utils.window_utils import center_modal_on_parent
from views.components.dialogs import show_message


DEFAULT_CATEGORIES = ["Trabalho", "Suporte", "Financeiro", "Projetos", "Pessoal", "Estudos"]


class TaskFormDialog(ctk.CTkToplevel):
    """Modal completo para criar ou editar uma tarefa e seus lembretes."""

    def __init__(
        self,
        parent,
        title_window: str,
        task: Optional[Task] = None,
        categories: Optional[List[str]] = None,
    ):
        super().__init__(parent)
        self.title(title_window)
        self.geometry("620x720")
        self.minsize(560, 600)
        self.transient(parent)
        self.grab_set()

        self.task = task
        self.result: Optional[Dict[str, Any]] = None
        center_modal_on_parent(self, parent, 620, 720)

        # Mapas amigáveis de rótulo <-> chave
        self._prio_label_to_key = {v: k for k, v in PRIORITY_LABELS.items()}
        self._status_label_to_key = {v: k for k, v in STATUS_LABELS.items()}
        self._repeat_label_to_key = {v: k for k, v in REPEAT_LABELS.items()}
        self._advance_label_to_mins = {lbl: mins for mins, lbl in ADVANCE_PRESETS}

        # Container principal
        self.outer = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.outer.pack(fill="both", expand=True, padx=14, pady=14)

        # Cabeçalho fixo do modal
        header = ctk.CTkFrame(self.outer, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 6))

        icon_hdr = "✏️" if task else "➕"
        ctk.CTkLabel(
            header,
            text=f"{icon_hdr} {title_window}",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        ).pack(side="left")

        if task and task.created_at_br:
            ctk.CTkLabel(
                header,
                text=f"Cadastrada em {task.created_at_br}",
                font=ctk.CTkFont(size=11),
                text_color=config.COLORS["text_muted"],
            ).pack(side="right")

        # Área rolável do formulário
        self.scroll = ctk.CTkScrollableFrame(
            self.outer,
            fg_color="transparent",
            corner_radius=0,
        )
        self.scroll.pack(fill="both", expand=True, padx=10, pady=(4, 6))

        # --- 1. TÍTULO ---
        self._section_label(self.scroll, "Título da Tarefa *")
        self.entry_title = ctk.CTkEntry(
            self.scroll,
            height=38,
            placeholder_text="Ex: Corrigir problema na emissão de notas fiscais",
            corner_radius=8,
        )
        self.entry_title.pack(fill="x", padx=8, pady=(0, 10))

        # --- 2. DESCRIÇÃO INICIAL ---
        self._section_label(self.scroll, "Descrição Inicial")
        self.txt_description = ctk.CTkTextbox(
            self.scroll,
            height=96,
            corner_radius=8,
            border_width=1,
            border_color=config.COLORS["border_dark"],
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
        )
        self.txt_description.pack(fill="x", padx=8, pady=(0, 12))

        # --- 3. DATAS E HORÁRIO ---
        dates_row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        dates_row.pack(fill="x", padx=8, pady=(0, 6))
        dates_row.grid_columnconfigure(0, weight=1)
        dates_row.grid_columnconfigure(1, weight=1)
        dates_row.grid_columnconfigure(2, weight=1)

        # Data de início
        col_start = ctk.CTkFrame(dates_row, fg_color="transparent")
        col_start.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkLabel(
            col_start,
            text="Data de Início",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        ).pack(fill="x", pady=(0, 3))
        self.entry_start_date = ctk.CTkEntry(
            col_start, height=34, placeholder_text="DD/MM/AAAA", corner_radius=6
        )
        self.entry_start_date.pack(fill="x")

        # Data prevista de conclusão
        col_due = ctk.CTkFrame(dates_row, fg_color="transparent")
        col_due.grid(row=0, column=1, sticky="ew", padx=3)
        ctk.CTkLabel(
            col_due,
            text="Data Prevista",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        ).pack(fill="x", pady=(0, 3))
        self.entry_due_date = ctk.CTkEntry(
            col_due, height=34, placeholder_text="DD/MM/AAAA", corner_radius=6
        )
        self.entry_due_date.pack(fill="x")

        # Horário opcional
        col_time = ctk.CTkFrame(dates_row, fg_color="transparent")
        col_time.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ctk.CTkLabel(
            col_time,
            text="Horário (opcional)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        ).pack(fill="x", pady=(0, 3))
        self.entry_due_time = ctk.CTkEntry(
            col_time, height=34, placeholder_text="HH:MM (ex: 15:00)", corner_radius=6
        )
        self.entry_due_time.pack(fill="x")

        # Atalhos rápidos para Data Prevista
        quick_row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        quick_row.pack(fill="x", padx=8, pady=(0, 12))
        ctk.CTkLabel(
            quick_row,
            text="Prazo rápido:",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
        ).pack(side="left", padx=(0, 6))

        for label_q, delta_d in [("Hoje", 0), ("Amanhã", 1), ("+3 dias", 3), ("+7 dias", 7)]:
            ctk.CTkButton(
                quick_row,
                text=label_q,
                width=64,
                height=24,
                corner_radius=6,
                font=ctk.CTkFont(size=11),
                fg_color=config.COLORS["card_dark_alt"],
                hover_color=config.COLORS["primary"],
                text_color=config.COLORS["button_text"],
                command=lambda d=delta_d: self._set_quick_due_date(d),
            ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            quick_row,
            text="Sem prazo",
            width=72,
            height=24,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["text_muted"],
            command=self._clear_due_date,
        ).pack(side="left")

        # --- 4. PRIORIDADE, STATUS E CATEGORIA ---
        meta_row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        meta_row.pack(fill="x", padx=8, pady=(0, 12))
        meta_row.grid_columnconfigure(0, weight=1)
        meta_row.grid_columnconfigure(1, weight=1)
        meta_row.grid_columnconfigure(2, weight=1)

        col_prio = ctk.CTkFrame(meta_row, fg_color="transparent")
        col_prio.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkLabel(
            col_prio,
            text="Prioridade",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        ).pack(fill="x", pady=(0, 3))
        self.opt_priority = ctk.CTkOptionMenu(
            col_prio,
            values=list(PRIORITY_LABELS.values()),
            height=34,
            corner_radius=6,
        )
        self.opt_priority.pack(fill="x")

        col_status = ctk.CTkFrame(meta_row, fg_color="transparent")
        col_status.grid(row=0, column=1, sticky="ew", padx=3)
        ctk.CTkLabel(
            col_status,
            text="Status",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        ).pack(fill="x", pady=(0, 3))
        self.opt_status = ctk.CTkOptionMenu(
            col_status,
            values=list(STATUS_LABELS.values()),
            height=34,
            corner_radius=6,
        )
        self.opt_status.pack(fill="x")

        col_cat = ctk.CTkFrame(meta_row, fg_color="transparent")
        col_cat.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ctk.CTkLabel(
            col_cat,
            text="Categoria (opcional)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        ).pack(fill="x", pady=(0, 3))

        merged_cats: List[str] = []
        for c in (categories or []) + DEFAULT_CATEGORIES:
            c_clean = (c or "").strip()
            if c_clean and c_clean not in merged_cats:
                merged_cats.append(c_clean)

        self.combo_category = ctk.CTkComboBox(
            col_cat,
            values=merged_cats,
            height=34,
            corner_radius=6,
        )
        self.combo_category.set("")
        self.combo_category.pack(fill="x")

        # --- 5. NOTIFICAÇÕES E LEMBRETES ---
        self.rem_card = ctk.CTkFrame(
            self.scroll,
            corner_radius=10,
            fg_color=config.COLORS["card_dark_alt"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.rem_card.pack(fill="x", padx=8, pady=(2, 10))

        rem_hdr = ctk.CTkFrame(self.rem_card, fg_color="transparent")
        rem_hdr.pack(fill="x", padx=12, pady=(10, 6))

        ctk.CTkLabel(
            rem_hdr,
            text="🔔 Notificações e Lembretes",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        ).pack(side="left")

        self.var_rem_enabled = ctk.BooleanVar(value=False)
        self.switch_rem_enabled = ctk.CTkSwitch(
            rem_hdr,
            text="Ativar avisos",
            variable=self.var_rem_enabled,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._toggle_reminders_panel,
        )
        self.switch_rem_enabled.pack(side="right")

        self.rem_options_frame = ctk.CTkFrame(self.rem_card, fg_color="transparent")
        self.rem_options_frame.pack(fill="x", padx=12, pady=(0, 10))

        # 5.1 Lembrete em data/horário específico
        self.var_rem_custom = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self.rem_options_frame,
            text="Lembrete em data e horário específicos",
            variable=self.var_rem_custom,
            font=ctk.CTkFont(size=12, weight="bold"),
            checkbox_width=18,
            checkbox_height=18,
        ).pack(anchor="w", pady=(2, 4))

        custom_row = ctk.CTkFrame(self.rem_options_frame, fg_color="transparent")
        custom_row.pack(fill="x", padx=(24, 0), pady=(0, 8))

        self.entry_rem_date = ctk.CTkEntry(
            custom_row, width=116, height=30, placeholder_text="DD/MM/AAAA", corner_radius=6
        )
        self.entry_rem_date.pack(side="left", padx=(0, 6))

        self.entry_rem_time = ctk.CTkEntry(
            custom_row, width=82, height=30, placeholder_text="HH:MM", corner_radius=6
        )
        self.entry_rem_time.pack(side="left", padx=(0, 6))

        self.opt_rem_repeat = ctk.CTkOptionMenu(
            custom_row,
            values=list(REPEAT_LABELS.values()),
            width=148,
            height=30,
            corner_radius=6,
        )
        self.opt_rem_repeat.set(REPEAT_LABELS["none"])
        self.opt_rem_repeat.pack(side="left")

        # 5.2 Aviso no dia do vencimento
        due_day_row = ctk.CTkFrame(self.rem_options_frame, fg_color="transparent")
        due_day_row.pack(fill="x", pady=(0, 6))
        self.var_rem_due_day = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            due_day_row,
            text="Aviso no dia do vencimento às:",
            variable=self.var_rem_due_day,
            font=ctk.CTkFont(size=12),
            checkbox_width=18,
            checkbox_height=18,
        ).pack(side="left")
        self.entry_due_day_time = ctk.CTkEntry(
            due_day_row, width=78, height=28, placeholder_text="09:00", corner_radius=6
        )
        self.entry_due_day_time.insert(0, "09:00")
        self.entry_due_day_time.pack(side="left", padx=(8, 0))

        # 5.3 Aviso antecipado
        adv_row = ctk.CTkFrame(self.rem_options_frame, fg_color="transparent")
        adv_row.pack(fill="x", pady=(0, 6))
        self.var_rem_advance = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            adv_row,
            text="Aviso antecipado:",
            variable=self.var_rem_advance,
            font=ctk.CTkFont(size=12),
            checkbox_width=18,
            checkbox_height=18,
        ).pack(side="left")
        self.opt_advance = ctk.CTkOptionMenu(
            adv_row,
            values=[lbl for _m, lbl in ADVANCE_PRESETS],
            width=165,
            height=28,
            corner_radius=6,
        )
        self.opt_advance.set("1 dia antes")
        self.opt_advance.pack(side="left", padx=(8, 0))

        # 5.4 Lembrete de tarefa atrasada
        overdue_row = ctk.CTkFrame(self.rem_options_frame, fg_color="transparent")
        overdue_row.pack(fill="x", pady=(0, 2))
        self.var_rem_overdue = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            overdue_row,
            text="Lembrete diário se ficar atrasada às:",
            variable=self.var_rem_overdue,
            font=ctk.CTkFont(size=12),
            checkbox_width=18,
            checkbox_height=18,
        ).pack(side="left")
        self.entry_overdue_time = ctk.CTkEntry(
            overdue_row, width=78, height=28, placeholder_text="09:00", corner_radius=6
        )
        self.entry_overdue_time.insert(0, "09:00")
        self.entry_overdue_time.pack(side="left", padx=(8, 0))

        # --- RODAPÉ DE AÇÕES ---
        btn_row = ctk.CTkFrame(self.outer, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(6, 14))

        ctk.CTkButton(
            btn_row,
            text="Cancelar",
            width=110,
            height=38,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row,
            text="💾 Salvar Tarefa",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_save,
        ).pack(side="right", fill="x", expand=True)

        # Preenche valores iniciais (edição ou nova tarefa)
        self._populate_initial_values()
        self._toggle_reminders_panel()

        self.after(80, lambda: self.entry_title.focus_set() if self.winfo_exists() else None)
        self.wait_window(self)

    @staticmethod
    def _section_label(parent, text: str):
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 3))

    def _set_quick_due_date(self, delta_days: int):
        target = datetime.date.today() + datetime.timedelta(days=delta_days)
        br = target.strftime("%d/%m/%Y")
        self.entry_due_date.delete(0, "end")
        self.entry_due_date.insert(0, br)
        if not self.entry_rem_date.get().strip():
            self.entry_rem_date.insert(0, br)

    def _clear_due_date(self):
        self.entry_due_date.delete(0, "end")

    def _populate_initial_values(self):
        today_br = format_iso_date_br(get_today_iso())

        if self.task is not None:
            t = self.task
            self.entry_title.insert(0, t.title)
            if t.description:
                self.txt_description.insert("1.0", t.description)
            if t.start_date:
                self.entry_start_date.insert(0, format_iso_date_br(t.start_date))
            if t.due_date:
                self.entry_due_date.insert(0, format_iso_date_br(t.due_date))
            if t.due_time:
                self.entry_due_time.insert(0, t.due_time)

            self.opt_priority.set(PRIORITY_LABELS.get(t.priority, "Média"))
            self.opt_status.set(STATUS_LABELS.get(t.status, "Pendente"))
            self.combo_category.set(t.category or "")

            self.var_rem_enabled.set(bool(t.reminder_enabled or t.reminders))
            for rem in t.reminders:
                if rem.reminder_type == "custom":
                    self.var_rem_custom.set(True)
                    self.entry_rem_date.delete(0, "end")
                    if rem.remind_date:
                        self.entry_rem_date.insert(0, format_iso_date_br(rem.remind_date))
                    self.entry_rem_time.delete(0, "end")
                    self.entry_rem_time.insert(0, rem.remind_time or "09:00")
                    self.opt_rem_repeat.set(REPEAT_LABELS.get(rem.repeat_interval, "Sem repetição"))
                elif rem.reminder_type == "due_day":
                    self.var_rem_due_day.set(True)
                    self.entry_due_day_time.delete(0, "end")
                    self.entry_due_day_time.insert(0, rem.remind_time or "09:00")
                elif rem.reminder_type == "advance":
                    self.var_rem_advance.set(True)
                    matched_lbl = next(
                        (lbl for mins, lbl in ADVANCE_PRESETS if mins == rem.advance_minutes),
                        "1 dia antes",
                    )
                    self.opt_advance.set(matched_lbl)
                elif rem.reminder_type == "overdue":
                    self.var_rem_overdue.set(True)
                    self.entry_overdue_time.delete(0, "end")
                    self.entry_overdue_time.insert(0, rem.remind_time or "09:00")
        else:
            self.entry_start_date.insert(0, today_br)
            self.entry_due_date.insert(0, today_br)
            self.opt_priority.set(PRIORITY_LABELS["media"])
            self.opt_status.set(STATUS_LABELS["pendente"])
            self.combo_category.set("")
            self.entry_rem_date.insert(0, today_br)
            next_hour = (datetime.datetime.now() + datetime.timedelta(hours=1)).strftime("%H:00")
            self.entry_rem_time.insert(0, next_hour)
            self.var_rem_enabled.set(False)

    def _toggle_reminders_panel(self):
        if self.var_rem_enabled.get():
            self.rem_options_frame.pack(fill="x", padx=12, pady=(0, 10))
            # Se acabou de ligar e nenhum checkbox está marcado, pré-marca "No dia do vencimento" ou "Custom"
            if not any(
                (
                    self.var_rem_custom.get(),
                    self.var_rem_due_day.get(),
                    self.var_rem_advance.get(),
                    self.var_rem_overdue.get(),
                )
            ):
                if self.entry_due_date.get().strip():
                    self.var_rem_due_day.set(True)
                    self.var_rem_overdue.set(True)
                else:
                    self.var_rem_custom.set(True)
        else:
            self.rem_options_frame.pack_forget()

    def _parse_optional_br_date(self, raw: str, field_name: str) -> Optional[str]:
        val = (raw or "").strip()
        if not val:
            return ""
        iso = parse_date_input(val)
        if not iso:
            show_message(self, "Data Inválida", f"{field_name} inválida. Use o formato DD/MM/AAAA.", kind="warning")
            return None
        return iso

    def _validate_hm(self, raw: str, field_name: str, allow_empty: bool = False) -> Optional[str]:
        val = (raw or "").strip()
        if not val:
            return "" if allow_empty else "09:00"
        parts = val.split(":")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            show_message(self, "Horário Inválido", f"{field_name} inválido. Use HH:MM (ex: 14:30).", kind="warning")
            return None
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            show_message(self, "Horário Inválido", f"{field_name} fora do intervalo 00:00 a 23:59.", kind="warning")
            return None
        return f"{h:02d}:{m:02d}"

    def _on_save(self):
        title = self.entry_title.get().strip()
        if not title:
            show_message(self, "Campo Obrigatório", "Informe um título para a tarefa.", kind="warning")
            self.entry_title.focus_set()
            return

        start_iso = self._parse_optional_br_date(self.entry_start_date.get(), "Data de início")
        if start_iso is None:
            return

        due_iso = self._parse_optional_br_date(self.entry_due_date.get(), "Data prevista")
        if due_iso is None:
            return

        due_time = self._validate_hm(self.entry_due_time.get(), "Horário previsto", allow_empty=True)
        if due_time is None:
            return

        description = self.txt_description.get("1.0", "end-1c").strip()
        priority = self._prio_label_to_key.get(self.opt_priority.get(), "media")
        status = self._status_label_to_key.get(self.opt_status.get(), "pendente")
        category = self.combo_category.get().strip()

        reminder_enabled = bool(self.var_rem_enabled.get())
        reminders: List[Dict[str, Any]] = []

        if reminder_enabled:
            if self.var_rem_custom.get():
                rem_date_iso = self._parse_optional_br_date(self.entry_rem_date.get(), "Data do lembrete")
                if not rem_date_iso:
                    if rem_date_iso == "":
                        show_message(
                            self,
                            "Lembrete Incompleto",
                            "Informe a data do lembrete específico (DD/MM/AAAA).",
                            kind="warning",
                        )
                    return
                rem_time = self._validate_hm(self.entry_rem_time.get(), "Horário do lembrete", allow_empty=False)
                if rem_time is None:
                    return
                rep_key = self._repeat_label_to_key.get(self.opt_rem_repeat.get(), "none")
                reminders.append(
                    {
                        "reminder_type": "custom",
                        "remind_date": rem_date_iso,
                        "remind_time": rem_time,
                        "advance_minutes": 0,
                        "repeat_interval": rep_key,
                        "is_active": True,
                    }
                )

            if self.var_rem_due_day.get():
                if not due_iso:
                    show_message(
                        self,
                        "Prazo Necessário",
                        "Para ativar o 'Aviso no dia do vencimento', preencha a Data Prevista da tarefa.",
                        kind="warning",
                    )
                    return
                dd_time = self._validate_hm(
                    self.entry_due_day_time.get(), "Horário do aviso de vencimento", allow_empty=False
                )
                if dd_time is None:
                    return
                reminders.append(
                    {
                        "reminder_type": "due_day",
                        "remind_date": "",
                        "remind_time": dd_time,
                        "advance_minutes": 0,
                        "repeat_interval": "none",
                        "is_active": True,
                    }
                )

            if self.var_rem_advance.get():
                if not due_iso:
                    show_message(
                        self,
                        "Prazo Necessário",
                        "Para ativar o 'Aviso antecipado', preencha a Data Prevista da tarefa.",
                        kind="warning",
                    )
                    return
                adv_mins = self._advance_label_to_mins.get(self.opt_advance.get(), 1440)
                reminders.append(
                    {
                        "reminder_type": "advance",
                        "remind_date": "",
                        "remind_time": due_time or "09:00",
                        "advance_minutes": adv_mins,
                        "repeat_interval": "none",
                        "is_active": True,
                    }
                )

            if self.var_rem_overdue.get():
                if not due_iso:
                    show_message(
                        self,
                        "Prazo Necessário",
                        "Para ativar o 'Lembrete de tarefa atrasada', preencha a Data Prevista da tarefa.",
                        kind="warning",
                    )
                    return
                ov_time = self._validate_hm(
                    self.entry_overdue_time.get(), "Horário do lembrete de atraso", allow_empty=False
                )
                if ov_time is None:
                    return
                reminders.append(
                    {
                        "reminder_type": "overdue",
                        "remind_date": "",
                        "remind_time": ov_time,
                        "advance_minutes": 0,
                        "repeat_interval": "none",
                        "is_active": True,
                    }
                )

            if not reminders:
                reminder_enabled = False

        self.result = {
            "title": title,
            "description": description,
            "start_date": start_iso,
            "due_date": due_iso,
            "due_time": due_time,
            "priority": priority,
            "status": status,
            "category": category,
            "reminder_enabled": reminder_enabled,
            "reminders": reminders,
        }
        self.destroy()
