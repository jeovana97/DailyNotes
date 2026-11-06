import tkinter as tk
from tkinter import filedialog
from typing import Optional, Callable, List, Dict, Any
import customtkinter as ctk

import config
from models.user import User
from services.diary_service import DiaryService
from services.search_service import SearchService
from services.authentication_service import AuthenticationService
from services.backup_service import BackupService
from utils.date_utils import format_date_br, format_date_long_br, parse_date_input
from views.components.dialogs import show_message, DiaryNoteReaderDialog


class SearchView(ctk.CTkFrame):
    """
    Tela exclusiva de Pesquisa Avançada.
    Permite encontrar rapidamente qualquer anotação por palavra/expressão,
    sem distinção de maiúsculas ou acentuação, combinando filtros por data e usuário.
    """

    def __init__(
        self,
        master,
        current_user: User,
        search_service: SearchService,
        auth_service: AuthenticationService,
        backup_service: BackupService,
        on_open_diary_date: Callable[[str, Optional[int]], None],
        diary_service: Optional[DiaryService] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.search_service = search_service
        self.auth_service = auth_service
        self.backup_service = backup_service
        self.on_open_diary_date = on_open_diary_date
        self.diary_service = diary_service or DiaryService(db_path=self.search_service.db_path)

        self.results: List[Dict[str, Any]] = []
        self.selected_index: int = -1
        self._reader_dialog: Optional[DiaryNoteReaderDialog] = None

        self._build_ui()

    def _build_ui(self):
        # 1. Painel Superior com Filtros de Pesquisa
        self.filters_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.filters_card.pack(fill="x", padx=20, pady=(15, 10))

        # Título da tela
        self.header_frame = ctk.CTkFrame(self.filters_card, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=15, pady=(12, 6))

        self.lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="🔍 Pesquisa Avançada no Diário",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(side="left")

        # Linha 1 de Filtros: Campo de Busca textual + Botões
        self.row1 = ctk.CTkFrame(self.filters_card, fg_color="transparent")
        self.row1.pack(fill="x", padx=15, pady=6)

        self.entry_query = ctk.CTkEntry(
            self.row1,
            height=40,
            placeholder_text="Digite palavras ou expressões (ex: erro na emissão, chamado 8492, SQL...)",
            font=ctk.CTkFont(size=13),
            corner_radius=8,
        )
        self.entry_query.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_query.bind("<Return>", lambda e: self.execute_search())

        self.btn_search = ctk.CTkButton(
            self.row1,
            text="🔍 Pesquisar",
            width=110,
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self.execute_search,
        )
        self.btn_search.pack(side="left", padx=(0, 6))

        self.btn_clear = ctk.CTkButton(
            self.row1,
            text="🧹 Limpar",
            width=85,
            height=40,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._clear_filters,
        )
        self.btn_clear.pack(side="left")

        # Linha 2 de Filtros: Datas e Ordenação
        self.row2 = ctk.CTkFrame(self.filters_card, fg_color="transparent")
        self.row2.pack(fill="x", padx=15, pady=(4, 14))

        # Data Inicial
        self.lbl_start = ctk.CTkLabel(self.row2, text="Data Inicial:", font=ctk.CTkFont(size=12))
        self.lbl_start.pack(side="left", padx=(0, 4))
        self.entry_start_date = ctk.CTkEntry(
            self.row2, width=105, height=32, placeholder_text="DD/MM/AAAA", corner_radius=6
        )
        self.entry_start_date.pack(side="left", padx=(0, 12))
        self.entry_start_date.bind("<Return>", lambda e: self.execute_search())

        # Data Final
        self.lbl_end = ctk.CTkLabel(self.row2, text="Data Final:", font=ctk.CTkFont(size=12))
        self.lbl_end.pack(side="left", padx=(0, 4))
        self.entry_end_date = ctk.CTkEntry(
            self.row2, width=105, height=32, placeholder_text="DD/MM/AAAA", corner_radius=6
        )
        self.entry_end_date.pack(side="left", padx=(0, 12))
        self.entry_end_date.bind("<Return>", lambda e: self.execute_search())

        # Data Exata
        self.lbl_exact = ctk.CTkLabel(self.row2, text="Data Exata:", font=ctk.CTkFont(size=12))
        self.lbl_exact.pack(side="left", padx=(0, 4))
        self.entry_exact_date = ctk.CTkEntry(
            self.row2, width=105, height=32, placeholder_text="DD/MM/AAAA", corner_radius=6
        )
        self.entry_exact_date.pack(side="left", padx=(0, 15))
        self.entry_exact_date.bind("<Return>", lambda e: self.execute_search())

        # Ordenação
        self.lbl_order = ctk.CTkLabel(self.row2, text="Ordem:", font=ctk.CTkFont(size=12))
        self.lbl_order.pack(side="left", padx=(0, 4))
        self.combo_order = ctk.CTkComboBox(
            self.row2,
            values=["Mais recentes primeiro", "Mais antigas primeiro"],
            width=180,
            height=32,
            corner_radius=6,
        )
        self.combo_order.set("Mais recentes primeiro")
        self.combo_order.pack(side="left", padx=(0, 15))

        # Filtro de Usuário (apenas se autorizado a ver outros diários)
        if self.current_user.can_view_other_diaries:
            self.lbl_user_filter = ctk.CTkLabel(self.row2, text="Usuário:", font=ctk.CTkFont(size=12))
            self.lbl_user_filter.pack(side="left", padx=(0, 4))

            self.users_list = self.auth_service.list_users(self.current_user)
            user_choices = ["Todos os usuários"] + [f"{u.full_name} ({u.username})" for u in self.users_list]
            self.combo_user_filter = ctk.CTkComboBox(
                self.row2,
                values=user_choices,
                width=190,
                height=32,
                corner_radius=6,
            )
            self.combo_user_filter.set("Todos os usuários")
            self.combo_user_filter.pack(side="left")
        else:
            self.combo_user_filter = None

        # 2. Barra de Resumo dos Resultados e Exportação CSV
        self.summary_bar = ctk.CTkFrame(
            self,
            height=40,
            corner_radius=8,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.summary_bar.pack(fill="x", padx=20, pady=(0, 10))

        self.lbl_results_count = ctk.CTkLabel(
            self.summary_bar,
            text="Faça uma pesquisa para visualizar as anotações.",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_results_count.pack(side="left", padx=15, pady=8)

        # Botão Navegar Próximo / Anterior entre resultados
        self.nav_results_frame = ctk.CTkFrame(self.summary_bar, fg_color="transparent")
        self.nav_results_frame.pack(side="right", padx=10)

        self.btn_prev_res = ctk.CTkButton(
            self.nav_results_frame,
            text="◀ Anterior",
            width=80,
            height=28,
            corner_radius=6,
            state="disabled",
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["button_text"],
            command=self._on_prev_result,
        )
        self.btn_prev_res.pack(side="left", padx=3)

        self.btn_next_res = ctk.CTkButton(
            self.nav_results_frame,
            text="Próximo ▶",
            width=80,
            height=28,
            corner_radius=6,
            state="disabled",
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["button_text"],
            command=self._on_next_result,
        )
        self.btn_next_res.pack(side="left", padx=3)

        self.btn_export_csv = ctk.CTkButton(
            self.nav_results_frame,
            text="📊 Exportar CSV",
            width=110,
            height=28,
            corner_radius=6,
            state="disabled",
            fg_color=config.COLORS["accent"],
            hover_color=config.COLORS["accent_hover"],
            text_color="#FFFFFF",
            command=self._on_export_csv,
        )
        self.btn_export_csv.pack(side="left", padx=(8, 5))

        # 3. Lista de Resultados com Rolagem
        self.results_scroll = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.results_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # Estado inicial vazio amigável
        self._render_empty_state("Utilize a barra de pesquisa acima para encontrar qualquer informação no diário.")

    def _render_empty_state(self, message: str):
        for widget in self.results_scroll.winfo_children():
            widget.destroy()

        empty_box = ctk.CTkFrame(self.results_scroll, fg_color="transparent")
        empty_box.pack(expand=True, fill="both", pady=60)

        icon = ctk.CTkLabel(empty_box, text="🔎", font=ctk.CTkFont(size=42))
        icon.pack(pady=(0, 10))

        lbl = ctk.CTkLabel(
            empty_box,
            text=message,
            font=ctk.CTkFont(size=14),
            text_color=config.COLORS["text_muted"],
            justify="center",
            wraplength=500,
        )
        lbl.pack()

    def execute_search(self):
        query = self.entry_query.get().strip()
        start_str = self.entry_start_date.get().strip()
        end_str = self.entry_end_date.get().strip()
        exact_str = self.entry_exact_date.get().strip()

        # Validação das datas informadas
        start_iso = None
        if start_str:
            start_iso = parse_date_input(start_str)
            if not start_iso:
                show_message(self, "Data Inválida", "Data Inicial inválida. Use DD/MM/AAAA.", kind="warning")
                return

        end_iso = None
        if end_str:
            end_iso = parse_date_input(end_str)
            if not end_iso:
                show_message(self, "Data Inválida", "Data Final inválida. Use DD/MM/AAAA.", kind="warning")
                return

        exact_iso = None
        if exact_str:
            exact_iso = parse_date_input(exact_str)
            if not exact_iso:
                show_message(self, "Data Inválida", "Data Exata inválida. Use DD/MM/AAAA.", kind="warning")
                return

        order_desc = (self.combo_order.get() == "Mais recentes primeiro")

        target_user_id = None
        if self.combo_user_filter:
            selected_user_str = self.combo_user_filter.get()
            if selected_user_str != "Todos os usuários":
                for u in self.users_list:
                    if f"{u.full_name} ({u.username})" == selected_user_str:
                        target_user_id = u.id
                        break

        # Executa a busca
        self.results = self.search_service.search_diaries(
            requester=self.current_user,
            query=query,
            start_date=start_iso,
            end_date=end_iso,
            exact_date=exact_iso,
            target_user_id=target_user_id,
            order_desc=order_desc,
        )

        self.selected_index = -1
        self._render_results()

    def _render_results(self):
        for widget in self.results_scroll.winfo_children():
            widget.destroy()

        count = len(self.results)
        if count == 0:
            self.lbl_results_count.configure(
                text="Nenhuma anotação encontrada com os filtros informados.",
                text_color=config.COLORS["warning"],
            )
            self.btn_export_csv.configure(state="disabled")
            self.btn_prev_res.configure(state="disabled")
            self.btn_next_res.configure(state="disabled")
            self._render_empty_state("Nenhuma anotação corresponde aos critérios de pesquisa.\nTente utilizar palavras mais curtas ou verificar o período filtrado.")
            return

        self.lbl_results_count.configure(
            text=f"✅ {count} {'anotação encontrada' if count == 1 else 'anotações encontradas'}:",
            text_color=config.COLORS["success"],
        )
        self.btn_export_csv.configure(state="normal")
        self.btn_prev_res.configure(state="normal")
        self.btn_next_res.configure(state="normal")

        # Renderiza cada resultado em um card moderno
        for idx, item in enumerate(self.results):
            card = ctk.CTkFrame(
                self.results_scroll,
                corner_radius=10,
                fg_color=config.COLORS["card_dark_alt"],
                border_width=1,
                border_color=config.COLORS["border_dark"],
            )
            card.pack(fill="x", padx=10, pady=5)

            # Cabeçalho do Card (Data, Usuário, Data de alteração)
            header_row = ctk.CTkFrame(card, fg_color="transparent")
            header_row.pack(fill="x", padx=12, pady=(10, 4))

            date_str = format_date_br(item["entry_date"])
            lbl_date = ctk.CTkLabel(
                header_row,
                text=f"📅 {date_str}",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=config.COLORS["text_dark"],
            )
            lbl_date.pack(side="left")

            if self.current_user.can_view_other_diaries:
                lbl_user = ctk.CTkLabel(
                    header_row,
                    text=f"👤 {item.get('full_name')} (@{item.get('username')})",
                    font=ctk.CTkFont(size=12),
                    text_color=config.COLORS["secondary"],
                )
                lbl_user.pack(side="left", padx=15)

            lbl_updated = ctk.CTkLabel(
                header_row,
                text=f"Última alteração: {item.get('updated_at', '')}",
                font=ctk.CTkFont(size=11),
                text_color=config.COLORS["text_muted"],
            )
            lbl_updated.pack(side="right")

            # Trecho com o termo localizado
            snippet_text = item.get("snippet", "")
            lbl_snippet = ctk.CTkLabel(
                card,
                text=snippet_text,
                font=ctk.CTkFont(size=13),
                text_color=config.COLORS["text_dark"],
                wraplength=700,
                justify="left",
                anchor="w",
            )
            lbl_snippet.pack(fill="x", padx=14, pady=(2, 8))

            # Rodapé do Card com botão abrir
            footer_row = ctk.CTkFrame(card, fg_color="transparent")
            footer_row.pack(fill="x", padx=12, pady=(0, 10))

            btn_open = ctk.CTkButton(
                footer_row,
                text="📖 Abrir Anotação (Leitura)",
                width=185,
                height=28,
                corner_radius=6,
                fg_color=config.COLORS["primary"],
                hover_color=config.COLORS["primary_hover"],
                text_color="#FFFFFF",
                command=lambda d=item["entry_date"], uid=item["user_id"], it=item: self._open_result(d, uid, it),
            )
            btn_open.pack(side="right")

            # Duplo clique no card ou no trecho abre a anotação em janela de leitura
            card.bind("<Double-Button-1>", lambda e, d=item["entry_date"], uid=item["user_id"], it=item: self._open_result(d, uid, it))
            lbl_snippet.bind("<Double-Button-1>", lambda e, d=item["entry_date"], uid=item["user_id"], it=item: self._open_result(d, uid, it))

    def _open_result(self, date_iso: str, user_id: int, item: Optional[Dict[str, Any]] = None):
        """Abre a anotação em uma janela exclusiva para leitura, com opção de editar."""
        if self._reader_dialog is not None and self._reader_dialog.winfo_exists():
            if not self._reader_dialog._confirm_can_close():
                return
            self._reader_dialog.destroy()

        author_str = None
        if item and item.get("full_name"):
            author_str = f"{item.get('full_name')} (@{item.get('username')})"
        elif self.current_user:
            author_str = f"{self.current_user.full_name} (@{self.current_user.username})"

        query = self.entry_query.get().strip()
        self._reader_dialog = DiaryNoteReaderDialog(
            parent=self,
            diary_service=self.diary_service,
            user_id=user_id,
            date_iso=date_iso,
            author_label=author_str,
            highlight_query=query,
            on_entry_saved=self.execute_search,
            on_open_in_diary=self.on_open_diary_date,
        )

    def _on_prev_result(self):
        if not self.results:
            return
        if self.selected_index <= 0:
            self.selected_index = len(self.results) - 1
        else:
            self.selected_index -= 1
        item = self.results[self.selected_index]
        self._open_result(item["entry_date"], item["user_id"], item)

    def _on_next_result(self):
        if not self.results:
            return
        if self.selected_index >= len(self.results) - 1:
            self.selected_index = 0
        else:
            self.selected_index += 1
        item = self.results[self.selected_index]
        self._open_result(item["entry_date"], item["user_id"], item)

    def _clear_filters(self):
        self.entry_query.delete(0, "end")
        self.entry_start_date.delete(0, "end")
        self.entry_end_date.delete(0, "end")
        self.entry_exact_date.delete(0, "end")
        self.combo_order.set("Mais recentes primeiro")
        if self.combo_user_filter:
            self.combo_user_filter.set("Todos os usuários")
        self.results.clear()
        self.lbl_results_count.configure(
            text="Filtros limpos.", text_color=config.COLORS["text_dark"]
        )
        self.btn_export_csv.configure(state="disabled")
        self.btn_prev_res.configure(state="disabled")
        self.btn_next_res.configure(state="disabled")
        self._render_empty_state("Filtros limpos. Digite novos termos para pesquisar.")

    def _on_export_csv(self):
        if not self.results:
            return

        file_path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar Resultados para CSV",
            initialfile="resultados_pesquisa.csv",
            defaultextension=".csv",
            filetypes=[("Arquivos CSV", "*.csv")],
        )
        if file_path:
            ok, msg = self.backup_service.export_search_results_to_csv(self.results, file_path)
            if ok:
                show_message(self, "Exportado", msg, kind="success")
            else:
                show_message(self, "Erro", msg, kind="danger")
