import calendar
import datetime
import re
from typing import Optional, Set, Callable
import customtkinter as ctk
import config
from utils.date_utils import MESES_PT, get_today_iso


class CalendarWidget(ctk.CTkFrame):
    """
    Componente moderno de calendário mensal para CustomTkinter.
    - Exibe dias do mês
    - Destaca dias que possuem anotações cadastradas
    - Permite seleção de datas e navegação entre meses e anos
    - Permite clicar no cabeçalho mês/ano para digitar e pular para qualquer data diretamente
    """

    def __init__(
        self,
        master,
        on_date_selected: Optional[Callable[[str], None]] = None,
        on_month_changed: Optional[Callable[[int, int], None]] = None,
        selected_date_iso: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(master, corner_radius=12, **kwargs)

        self.on_date_selected = on_date_selected
        self.on_month_changed = on_month_changed

        today = datetime.date.today()
        self.current_year = today.year
        self.current_month = today.month

        self.selected_date = selected_date_iso or today.isoformat()
        if self.selected_date:
            try:
                dt = datetime.date.fromisoformat(self.selected_date)
                self.current_year = dt.year
                self.current_month = dt.month
            except Exception:
                pass

        self.dates_with_notes: Set[str] = set()
        self.day_buttons = []

        self._build_ui()
        self._render_calendar()

    def _build_ui(self):
        # Container do cabeçalho
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=10, pady=(10, 5))

        # 1. Modo Normal: Botões de navegação e mês/ano clicável
        self.nav_mode_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.nav_mode_frame.pack(fill="x")

        self.btn_prev_month = ctk.CTkButton(
            self.nav_mode_frame,
            text="◀",
            width=32,
            height=32,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._prev_month,
        )
        self.btn_prev_month.pack(side="left")

        # Botão interativo do mês/ano: ao clicar, abre o campo para digitação direta
        self.btn_month_year = ctk.CTkButton(
            self.nav_mode_frame,
            text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="transparent",
            hover_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
            cursor="hand2",
            command=self._enter_edit_mode,
        )
        self.btn_month_year.pack(side="left", expand=True, fill="both", padx=4)
        self.lbl_month_year = self.btn_month_year  # Compatibilidade

        self.btn_next_month = ctk.CTkButton(
            self.nav_mode_frame,
            text="▶",
            width=32,
            height=32,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._next_month,
        )
        self.btn_next_month.pack(side="right")

        # Botão Hoje
        self.btn_today = ctk.CTkButton(
            self.nav_mode_frame,
            text="Hoje",
            width=48,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["accent"],
            hover_color=config.COLORS["accent_hover"],
            text_color="#FFFFFF",
            command=self._go_today,
        )
        self.btn_today.pack(side="right", padx=(0, 6))

        # 2. Modo Edição: Permite digitar data específica (DD/MM/AAAA, MM/AAAA, etc.)
        self.edit_mode_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")

        self.entry_date = ctk.CTkEntry(
            self.edit_mode_frame,
            placeholder_text="DD/MM/AAAA ou MM/AAAA",
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.entry_date.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.entry_date.bind("<Return>", lambda event: self._confirm_date_input())
        self.entry_date.bind("<Escape>", lambda event: self._exit_edit_mode())

        self.btn_confirm_date = ctk.CTkButton(
            self.edit_mode_frame,
            text="Ir",
            width=36,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._confirm_date_input,
        )
        self.btn_confirm_date.pack(side="left", padx=(0, 4))

        self.btn_cancel_date = ctk.CTkButton(
            self.edit_mode_frame,
            text="✕",
            width=32,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["danger"],
            text_color=config.COLORS["button_text"],
            command=self._exit_edit_mode,
        )
        self.btn_cancel_date.pack(side="left")

        # Cabeçalho dos dias da semana (Segunda a Domingo)
        self.weekdays_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.weekdays_frame.pack(fill="x", padx=10, pady=(5, 2))

        dias_siglas = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        for col, dia in enumerate(dias_siglas):
            lbl = ctk.CTkLabel(
                self.weekdays_frame,
                text=dia,
                width=38,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLORS["text_muted"],
            )
            lbl.grid(row=0, column=col, padx=2, pady=2)
            self.weekdays_frame.grid_columnconfigure(col, weight=1)

        # Grade dos dias do mês
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for col in range(7):
            self.grid_frame.grid_columnconfigure(col, weight=1)

    def _render_calendar(self):
        # Atualiza título do mês e ano com indicador visual de interatividade
        nome_mes = MESES_PT[self.current_month - 1]
        self.btn_month_year.configure(text=f"{nome_mes} {self.current_year}  ▾")

        # Limpa botões antigos da grade
        for btn in self.day_buttons:
            btn.destroy()
        self.day_buttons.clear()

        cal = calendar.Calendar(firstweekday=0)  # 0 = Segunda-feira
        month_days = cal.monthdatescalendar(self.current_year, self.current_month)

        today_iso = get_today_iso()

        for row_idx, week in enumerate(month_days):
            for col_idx, day_date in enumerate(week):
                day_iso = day_date.isoformat()
                is_current_month = (day_date.month == self.current_month)
                is_selected = (day_iso == self.selected_date)
                is_today = (day_iso == today_iso)
                has_notes = (day_iso in self.dates_with_notes)

                # Define cores e estilos
                if is_selected:
                    fg_color = config.COLORS["primary"]
                    hover_color = config.COLORS["primary_hover"]
                    text_color = "#FFFFFF"
                    border_width = 2
                    border_color = config.COLORS["secondary"]
                elif has_notes and is_current_month:
                    # Destaque com visual moderno para dias com anotação
                    fg_color = config.COLORS["secondary"]
                    hover_color = config.COLORS["secondary_hover"]
                    text_color = "#FFFFFF"
                    border_width = 1
                    border_color = config.COLORS["primary"]
                elif is_today:
                    fg_color = config.COLORS["card_dark_alt"]
                    hover_color = config.COLORS["primary"]
                    text_color = config.COLORS["primary"]
                    border_width = 1
                    border_color = config.COLORS["primary"]
                elif is_current_month:
                    fg_color = "transparent"
                    hover_color = config.COLORS["card_dark_alt"]
                    text_color = config.COLORS["text_dark"]
                    border_width = 0
                    border_color = None
                else:
                    # Dias fora do mês atual
                    fg_color = "transparent"
                    hover_color = config.COLORS["card_dark_alt"]
                    text_color = config.COLORS["text_muted"]
                    border_width = 0
                    border_color = None

                # Texto do botão: exibe dia e um indicador discreto se houver anotação
                badge = " •" if (has_notes and is_current_month and not is_selected) else ""
                btn_text = f"{day_date.day}{badge}"

                btn = ctk.CTkButton(
                    self.grid_frame,
                    text=btn_text,
                    width=38,
                    height=34,
                    corner_radius=8,
                    fg_color=fg_color,
                    hover_color=hover_color,
                    text_color=text_color,
                    border_width=border_width,
                    border_color=border_color,
                    font=ctk.CTkFont(size=12, weight="bold" if (has_notes or is_selected) else "normal"),
                    command=lambda d=day_iso: self._on_day_clicked(d),
                )
                btn.grid(row=row_idx, column=col_idx, padx=2, pady=2, sticky="nsew")
                self.day_buttons.append(btn)

    def _on_day_clicked(self, date_iso: str):
        self.selected_date = date_iso
        dt = datetime.date.fromisoformat(date_iso)
        if dt.month != self.current_month or dt.year != self.current_year:
            self.current_month = dt.month
            self.current_year = dt.year
            if self.on_month_changed:
                self.on_month_changed(self.current_year, self.current_month)

        self._render_calendar()

        if self.on_date_selected:
            self.on_date_selected(date_iso)

    def _prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1

        if self.on_month_changed:
            self.on_month_changed(self.current_year, self.current_month)
        self._render_calendar()

    def _next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1

        if self.on_month_changed:
            self.on_month_changed(self.current_year, self.current_month)
        self._render_calendar()

    def _go_today(self):
        today_iso = get_today_iso()
        self.select_date(today_iso)

    def _enter_edit_mode(self):
        """Ativa o modo de digitação direta de data no cabeçalho."""
        self.nav_mode_frame.pack_forget()
        self.edit_mode_frame.pack(fill="x", expand=True)

        # Sugestão inicial: data selecionada ou mês/ano atual
        sugestao = ""
        if self.selected_date:
            try:
                dt = datetime.date.fromisoformat(self.selected_date)
                sugestao = f"{dt.day:02d}/{dt.month:02d}/{dt.year}"
            except Exception:
                sugestao = f"{self.current_month:02d}/{self.current_year}"
        else:
            sugestao = f"{self.current_month:02d}/{self.current_year}"

        self.entry_date.configure(
            border_color=config.COLORS["border_dark"],
            border_width=1
        )
        self.entry_date.delete(0, "end")
        self.entry_date.insert(0, sugestao)
        self.entry_date.select_range(0, "end")
        self.entry_date.focus_set()

    def _exit_edit_mode(self):
        """Retorna do modo de digitação para os botões de navegação normais."""
        self.edit_mode_frame.pack_forget()
        self.nav_mode_frame.pack(fill="x", expand=True)

    def _confirm_date_input(self):
        """Processa a data ou mês/ano digitado e navega até ele."""
        raw_val = self.entry_date.get()
        res = self._parse_calendar_jump(raw_val)
        if not res:
            # Feedback de erro visual na borda do campo
            self.entry_date.configure(border_color=config.COLORS["danger"], border_width=2)
            self.after(1500, lambda: self.entry_date.configure(
                border_color=config.COLORS["border_dark"], border_width=1
            ) if self.entry_date.winfo_exists() else None)
            return

        if res["type"] == "date":
            self.select_date(res["iso"])
        elif res["type"] == "month":
            month_changed = (res["year"] != self.current_year or res["month"] != self.current_month)
            self.current_year = res["year"]
            self.current_month = res["month"]
            if month_changed and self.on_month_changed:
                self.on_month_changed(self.current_year, self.current_month)
            self._render_calendar()

        self._exit_edit_mode()

    def _parse_calendar_jump(self, text: str) -> Optional[dict]:
        """
        Interpreta formatos de data e mês/ano para navegação no calendário:
        - DD/MM/AAAA, DD/MM/AA, DD-MM-AAAA, DD.MM.AAAA, DD MM AAAA
        - AAAA-MM-DD
        - '15 de janeiro de 2025' ou '15 jan 2025'
        - MM/AAAA, MM-AAAA, MM AAAA
        - 'janeiro 2025' ou 'jan 2025'
        - AAAA (ano de 4 dígitos)
        """
        t = text.strip()
        if not t:
            return None

        # 1. Apenas ano (ex: 2026)
        if re.fullmatch(r"\d{4}", t):
            year = int(t)
            if 1900 <= year <= 2100:
                return {"type": "month", "year": year, "month": self.current_month}
            return None

        # 2. DD/MM/AAAA (ex: 15/01/2025 ou 15/1/25)
        m = re.fullmatch(r"(\d{1,2})[/\-\.\s](\d{1,2})[/\-\.\s](\d{2,4})", t)
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if year < 100:
                year += 2000
            try:
                d = datetime.date(year, month, day)
                return {"type": "date", "iso": d.isoformat()}
            except ValueError:
                return None

        # 3. AAAA-MM-DD (ex: 2025-01-15)
        m = re.fullmatch(r"(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", t)
        if m:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                d = datetime.date(year, month, day)
                return {"type": "date", "iso": d.isoformat()}
            except ValueError:
                return None

        # 4. MM/AAAA (ex: 05/2025 ou 5/2025)
        m = re.fullmatch(r"(\d{1,2})[/\-\.\s](\d{2,4})", t)
        if m:
            month, year = int(m.group(1)), int(m.group(2))
            if year < 100:
                year += 2000
            if 1 <= month <= 12 and 1900 <= year <= 2100:
                return {"type": "month", "year": year, "month": month}
            return None

        # 5. Data com nome de mês (ex: '15 de janeiro de 2025' ou '15 jan 2025')
        m = re.fullmatch(r"(\d{1,2})\s*(?:de\s*)?([a-zA-ZçÇãÃáÁéÉíÍóÓúÚ]+)\s*(?:de\s*)?(\d{2,4})", t, re.IGNORECASE)
        if m:
            day = int(m.group(1))
            m_str = m.group(2).lower()
            year = int(m.group(3))
            if year < 100:
                year += 2000
            for idx, mes in enumerate(MESES_PT):
                if mes.lower().startswith(m_str):
                    try:
                        d = datetime.date(year, idx + 1, day)
                        return {"type": "date", "iso": d.isoformat()}
                    except ValueError:
                        return None

        # 6. Mês por extenso + ano (ex: 'outubro 2025' ou 'out 2025')
        parts = t.lower().split()
        if len(parts) == 2 and parts[1].isdigit():
            m_str, y_str = parts[0], int(parts[1])
            if y_str < 100:
                y_str += 2000
            for idx, mes in enumerate(MESES_PT):
                if mes.lower().startswith(m_str):
                    return {"type": "month", "year": y_str, "month": idx + 1}

        return None


    def select_date(self, date_iso: str):
        """Seleciona programaticamente uma data e atualiza a exibição."""
        self.selected_date = date_iso
        try:
            dt = datetime.date.fromisoformat(date_iso)
            month_changed = (dt.month != self.current_month or dt.year != self.current_year)
            self.current_month = dt.month
            self.current_year = dt.year
            if month_changed and self.on_month_changed:
                self.on_month_changed(self.current_year, self.current_month)
        except Exception:
            pass

        self._render_calendar()
        if self.on_date_selected:
            self.on_date_selected(date_iso)

    def set_dates_with_notes(self, dates: Set[str]):
        """Atualiza a lista de datas que possuem anotações e re-renderiza o calendário."""
        self.dates_with_notes = set(dates)
        self._render_calendar()
