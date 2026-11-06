import datetime
from typing import Optional, Callable, Set, List
import customtkinter as ctk

import config
from models.user import User
from models.diary import DiaryEntry
from services.diary_service import DiaryService
from utils.date_utils import format_date_br, format_date_long_br, get_today_iso, MESES_PT
from views.components.calendar_widget import CalendarWidget
from views.components.dialogs import DiaryNoteReaderDialog


class HistoryView(ctk.CTkFrame):
    """
    Tela de Histórico e Calendário.
    Permite navegar cronologicamente pelos diários anteriores,
    identificar visualmente dias com anotações e visualizar resumos.
    """

    def __init__(
        self,
        master,
        current_user: User,
        diary_service: DiaryService,
        on_open_diary_date: Callable[[str, Optional[int]], None],
        initial_date_iso: Optional[str] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.diary_service = diary_service
        self.on_open_diary_date = on_open_diary_date

        self.selected_date_iso = initial_date_iso or get_today_iso()
        dt = datetime.date.fromisoformat(self.selected_date_iso)
        self.current_year = dt.year
        self.current_month = dt.month
        self._reader_dialog: Optional[DiaryNoteReaderDialog] = None

        self._build_ui()
        self._refresh_month_data(self.current_year, self.current_month)

    def _build_ui(self):
        # Cabeçalho da tela
        self.header_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.header_card.pack(fill="x", padx=20, pady=(15, 10))

        self.lbl_title = ctk.CTkLabel(
            self.header_card,
            text="📅 Histórico e Calendário de Anotações",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(side="left", padx=15, pady=12)

        # Container Principal com 2 Colunas (Esquerda: Calendário | Direita: Lista Cronológica)
        self.body_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.body_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # Coluna Esquerda: Calendário e Detalhe da Data
        self.left_col = ctk.CTkFrame(
            self.body_frame,
            width=340,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.left_col.pack(side="left", fill="y", padx=(0, 10))
        self.left_col.pack_propagate(False)

        # Widget do Calendário
        self.calendar_widget = CalendarWidget(
            self.left_col,
            on_date_selected=self._on_calendar_date_selected,
            on_month_changed=self._on_calendar_month_changed,
            selected_date_iso=self.selected_date_iso,
        )
        self.calendar_widget.pack(fill="x", padx=10, pady=10)

        # Card de Detalhe da Data Selecionada
        self.date_detail_card = ctk.CTkFrame(
            self.left_col,
            corner_radius=10,
            fg_color=config.COLORS["card_dark_alt"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.date_detail_card.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.lbl_detail_date = ctk.CTkLabel(
            self.date_detail_card,
            text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=config.COLORS["text_dark"],
            wraplength=300,
        )
        self.lbl_detail_date.pack(pady=(12, 4), padx=10)

        self.lbl_detail_status = ctk.CTkLabel(
            self.date_detail_card,
            text="",
            font=ctk.CTkFont(size=13),
            text_color=config.COLORS["text_muted"],
            wraplength=300,
        )
        self.lbl_detail_status.pack(pady=4, padx=10)

        self.btn_open_selected = ctk.CTkButton(
            self.date_detail_card,
            text="📝 Abrir no Editor",
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_open_current_selected,
        )
        self.btn_open_selected.pack(side="bottom", fill="x", padx=15, pady=15)

        # Coluna Direita: Lista Cronológica do Mês
        self.right_col = ctk.CTkFrame(
            self.body_frame,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.right_col.pack(side="right", fill="both", expand=True)

        self.month_header_frame = ctk.CTkFrame(self.right_col, fg_color="transparent")
        self.month_header_frame.pack(fill="x", padx=15, pady=(12, 6))

        self.lbl_month_entries = ctk.CTkLabel(
            self.month_header_frame,
            text="",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_month_entries.pack(side="left")

        # Scrollable Frame com a lista cronológica
        self.entries_scroll = ctk.CTkScrollableFrame(self.right_col, fg_color="transparent")
        self.entries_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _refresh_month_data(self, year: int, month: int):
        self.current_year = year
        self.current_month = month

        # Obtém datas que possuem anotações neste mês
        dates_with_notes = self.diary_service.get_dates_with_notes(
            self.current_user.id, year, month
        )
        self.calendar_widget.set_dates_with_notes(dates_with_notes)

        # Atualiza o detalhe da data atualmente selecionada
        self._update_selected_date_detail()

        # Atualiza a lista cronológica do mês
        self._render_month_entries(year, month)

    def _on_calendar_date_selected(self, date_iso: str):
        self.selected_date_iso = date_iso
        self._update_selected_date_detail()

    def _on_calendar_month_changed(self, year: int, month: int):
        self._refresh_month_data(year, month)

    def _update_selected_date_detail(self):
        long_date = format_date_long_br(self.selected_date_iso)
        self.lbl_detail_date.configure(text=long_date)

        entry = self.diary_service.get_entry_by_date(self.current_user.id, self.selected_date_iso)
        if entry and entry.content.strip():
            words = len(entry.content.split())
            chars = len(entry.content)
            self.lbl_detail_status.configure(
                text=f"🟢 Possui anotação registrada\n({words} palavras | {chars:,} caracteres)\nÚltima alteração: {entry.updated_at}",
                text_color=config.COLORS["success"],
            )
            self.btn_open_selected.configure(text="📖 Abrir Anotação (Leitura)")
        else:
            self.lbl_detail_status.configure(
                text="⚪ Nenhuma anotação registrada neste dia.\nClique abaixo para visualizar ou criar uma anotação nesta data.",
                text_color=config.COLORS["text_muted"],
            )
            self.btn_open_selected.configure(text="📖 Abrir / Criar Anotação")

    def _render_month_entries(self, year: int, month: int):
        for widget in self.entries_scroll.winfo_children():
            widget.destroy()

        entries = self.diary_service.list_entries_by_month(self.current_user.id, year, month)
        nome_mes = MESES_PT[month - 1]
        self.lbl_month_entries.configure(
            text=f"Anotações em {nome_mes} de {year} ({len(entries)} dias):"
        )

        if not entries:
            empty_box = ctk.CTkFrame(self.entries_scroll, fg_color="transparent")
            empty_box.pack(expand=True, fill="both", pady=40)

            lbl = ctk.CTkLabel(
                empty_box,
                text=f"Nenhuma anotação encontrada em {nome_mes} de {year}.",
                font=ctk.CTkFont(size=14),
                text_color=config.COLORS["text_muted"],
            )
            lbl.pack()
            return

        for item in entries:
            card = ctk.CTkFrame(
                self.entries_scroll,
                corner_radius=10,
                fg_color=config.COLORS["card_dark_alt"],
                border_width=1,
                border_color=config.COLORS["border_dark"],
            )
            card.pack(fill="x", padx=5, pady=4)

            # Linha superior: Data e Contagem
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=12, pady=(8, 2))

            date_str = format_date_br(item.entry_date)
            lbl_date = ctk.CTkLabel(
                top_row,
                text=f"📅 {date_str} - {format_date_long_br(item.entry_date).split(',')[0]}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=config.COLORS["text_dark"],
            )
            lbl_date.pack(side="left")

            words = len(item.content.split())
            lbl_words = ctk.CTkLabel(
                top_row,
                text=f"{words} palavras | Alterado: {item.updated_at}",
                font=ctk.CTkFont(size=11),
                text_color=config.COLORS["text_muted"],
            )
            lbl_words.pack(side="right")

            # Trecho inicial
            first_lines = item.content.strip().split("\n")
            preview = first_lines[0][:140] + ("..." if len(first_lines[0]) > 140 else "")
            if len(first_lines) > 1 and len(preview) < 100:
                preview += " / " + first_lines[1][:80]

            lbl_preview = ctk.CTkLabel(
                card,
                text=preview,
                font=ctk.CTkFont(size=12),
                text_color=config.COLORS["text_dark"],
                wraplength=520,
                justify="left",
                anchor="w",
            )
            lbl_preview.pack(fill="x", padx=12, pady=(2, 6))

            # Botão rápido para abrir em janela de leitura
            btn_open = ctk.CTkButton(
                card,
                text="📖 Abrir",
                width=85,
                height=26,
                corner_radius=6,
                fg_color=config.COLORS["primary"],
                hover_color=config.COLORS["primary_hover"],
                text_color="#FFFFFF",
                command=lambda d=item.entry_date: self._open_date(d),
            )
            btn_open.pack(side="right", padx=12, pady=(0, 8))

            card.bind("<Double-Button-1>", lambda e, d=item.entry_date: self._open_date(d))
            lbl_preview.bind("<Double-Button-1>", lambda e, d=item.entry_date: self._open_date(d))

    def _open_date(self, date_iso: str):
        """Abre a anotação da data selecionada em uma janela exclusiva para leitura, com botão para editar."""
        if self._reader_dialog is not None and self._reader_dialog.winfo_exists():
            if not self._reader_dialog._confirm_can_close():
                return
            self._reader_dialog.destroy()

        author_str = f"{self.current_user.full_name} (@{self.current_user.username})" if self.current_user else None
        self._reader_dialog = DiaryNoteReaderDialog(
            parent=self,
            diary_service=self.diary_service,
            user_id=self.current_user.id,
            date_iso=date_iso,
            author_label=author_str,
            on_entry_saved=lambda: self._refresh_month_data(self.current_year, self.current_month),
            on_open_in_diary=self.on_open_diary_date,
        )

    def _on_open_current_selected(self):
        self._open_date(self.selected_date_iso)
