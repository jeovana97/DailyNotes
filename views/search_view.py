import time
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
from utils.date_utils import format_date_br, parse_date_input
from views.components.dialogs import show_message, DiaryNoteReaderDialog


class SearchView(ctk.CTkFrame):
    """
    Tela exclusiva de Pesquisa Avançada.
    Permite encontrar rapidamente qualquer anotação por palavra/expressão,
    sem distinção de maiúsculas ou acentuação, combinando filtros por data e usuário.
    Otimizada com paginação incremental e renderização progressiva em lotes leves.
    """

    PAGE_SIZE = 25
    INITIAL_SYNC_BATCH = 8
    ASYNC_BATCH_SIZE = 6

    def __init__(
        self,
        master,
        current_user: User,
        search_service: SearchService,
        auth_service: AuthenticationService,
        backup_service: BackupService,
        on_open_diary_date: Callable[[str, Optional[int]], None],
        diary_service: Optional[DiaryService] = None,
        on_open_folder_note: Optional[Callable[[Optional[int], Optional[int]], None]] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.search_service = search_service
        self.auth_service = auth_service
        self.backup_service = backup_service
        self.on_open_diary_date = on_open_diary_date
        self.diary_service = diary_service or DiaryService(db_path=self.search_service.db_path)
        self.on_open_folder_note = on_open_folder_note

        self.results: List[Dict[str, Any]] = []
        self.selected_index: int = -1
        self._reader_dialog: Optional[DiaryNoteReaderDialog] = None
        self._last_elapsed_ms: float = 0.0

        # Controle de renderização progressiva e paginação incremental
        self._render_token: int = 0
        self._render_job_id: Optional[str] = None
        self._rendered_count: int = 0
        self._target_render_count: int = 0
        self._load_more_frame: Optional[tk.Widget] = None

        self._build_ui()

    @staticmethod
    def _resolve_color(color_val, is_dark: bool) -> str:
        if isinstance(color_val, (tuple, list)):
            return color_val[1 if is_dark else 0]
        return str(color_val)

    def _get_theme_palette(self) -> Dict[str, str]:
        is_dark = ctk.get_appearance_mode() == "Dark"
        return {
            "card_bg": self._resolve_color(config.COLORS["card_dark_alt"], is_dark),
            "border": self._resolve_color(config.COLORS["border_dark"], is_dark),
            "text": self._resolve_color(config.COLORS["text_dark"], is_dark),
            "muted": self._resolve_color(config.COLORS["text_muted"], is_dark),
            "primary": self._resolve_color(config.COLORS["primary"], is_dark),
            "primary_hover": self._resolve_color(config.COLORS["primary_hover"], is_dark),
            "secondary": self._resolve_color(config.COLORS["secondary"], is_dark),
            "secondary_hover": self._resolve_color(config.COLORS["secondary_hover"], is_dark),
            "btn_bg": self._resolve_color(config.COLORS["card_dark"], is_dark),
            "btn_fg": self._resolve_color(config.COLORS["button_text"], is_dark),
        }

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
            text="🔍 Pesquisa Avançada (Diário, Pastas e Arquivos)",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(side="left")

        # Seletor de onde pesquisar (Diário e Pastas / Somente Diário / Pastas e Arquivos)
        self.scope_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.scope_frame.pack(side="right")

        self.lbl_scope = ctk.CTkLabel(
            self.scope_frame,
            text="Pesquisar em:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_scope.pack(side="left", padx=(0, 6))

        self.combo_scope = ctk.CTkComboBox(
            self.scope_frame,
            values=["Diário e Pastas", "Somente Diário", "Pastas e Arquivos"],
            width=185,
            height=30,
            corner_radius=6,
            command=lambda _v: self.execute_search() if self.entry_query.get().strip() else None,
        )
        self.combo_scope.set("Diário e Pastas")
        self.combo_scope.pack(side="left")

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
        self._render_empty_state(
            "Utilize a barra de pesquisa acima para encontrar informações no Diário ou em Pastas e Arquivos."
        )

    def _cancel_pending_render(self):
        self._render_token += 1
        if self._render_job_id is not None:
            try:
                self.after_cancel(self._render_job_id)
            except Exception:
                pass
            self._render_job_id = None

    def _clear_results_container(self):
        self._cancel_pending_render()
        self._load_more_frame = None
        for widget in self.results_scroll.winfo_children():
            widget.destroy()
        try:
            self.results_scroll._parent_canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _render_empty_state(self, message: str):
        self._clear_results_container()

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

        scope_label = self.combo_scope.get()
        if scope_label == "Somente Diário":
            scope = "diaries"
        elif scope_label == "Pastas e Arquivos":
            scope = "notes"
        else:
            scope = "all"

        # Executa a busca otimizada (FTS5 trigram + C nativo) medindo o tempo real
        t0 = time.perf_counter()
        self.results = self.search_service.search_all(
            requester=self.current_user,
            query=query,
            start_date=start_iso,
            end_date=end_iso,
            exact_date=exact_iso,
            target_user_id=target_user_id,
            order_desc=order_desc,
            scope=scope,
        )
        self._last_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.selected_index = -1
        self._render_results()

    def _update_summary_label(self):
        total = len(self.results)
        ms_txt = f"{self._last_elapsed_ms:.0f} ms" if self._last_elapsed_ms >= 1.0 else "< 1 ms"
        noun = "anotação encontrada" if total == 1 else "anotações encontradas"
        if self._rendered_count < total:
            shown = min(self._target_render_count, total)
            summary = f"✅ {total} {noun} (exibindo {shown} de {total} • {ms_txt})"
        else:
            summary = f"✅ {total} {noun} ({ms_txt})"
        self.lbl_results_count.configure(text=summary, text_color=config.COLORS["success"])

    def _create_result_card(self, item: Dict[str, Any], palette: Dict[str, str]):
        """Cria um card leve (Tk nativo estilizado com o tema) de altíssima velocidade."""
        is_note = (item.get("source_type") == "note")
        card_bg = palette["card_bg"]

        card = tk.Frame(
            self.results_scroll,
            bg=card_bg,
            highlightbackground=palette["border"],
            highlightthickness=1,
            bd=0,
        )
        card.pack(fill="x", padx=10, pady=4)

        # Cabeçalho compacto: Badge + Título/Data + Usuário + Data alteração + Botão Abrir
        header_row = tk.Frame(card, bg=card_bg)
        header_row.pack(fill="x", padx=12, pady=(8, 3))

        badge_bg = palette["secondary"] if is_note else palette["primary"]
        origin_badge = tk.Label(
            header_row,
            text="📁 Pasta & Arquivos" if is_note else "📔 Diário",
            bg=badge_bg,
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            padx=7,
            pady=2,
        )
        origin_badge.pack(side="left", padx=(0, 8))

        if is_note:
            folder_path = item.get("folder_path", "Raiz (Sem pasta)")
            note_title = item.get("title", "Sem título")
            title_txt = f"📄 {note_title}   •   📂 {folder_path}"
        else:
            date_str = format_date_br(item["entry_date"])
            title_txt = f"📅 {date_str}"

        lbl_date = tk.Label(
            header_row,
            text=title_txt,
            bg=card_bg,
            fg=palette["text"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        lbl_date.pack(side="left")

        if self.current_user.can_view_other_diaries:
            lbl_user = tk.Label(
                header_row,
                text=f"👤 {item.get('full_name')} (@{item.get('username')})",
                bg=card_bg,
                fg=palette["secondary"],
                font=("Segoe UI", 9),
            )
            lbl_user.pack(side="left", padx=12)

        btn_bg = palette["secondary"] if is_note else palette["primary"]
        btn_hover = palette["secondary_hover"] if is_note else palette["primary_hover"]
        btn_text = "📂 Abrir na Pasta" if is_note else "📖 Abrir Anotação (Leitura)"

        btn_open = tk.Button(
            header_row,
            text=btn_text,
            bg=btn_bg,
            fg="#FFFFFF",
            activebackground=btn_hover,
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            command=lambda it=item: self._open_item(it),
        )
        btn_open.pack(side="right", padx=(8, 0))
        btn_open.bind("<Enter>", lambda _e, b=btn_open, c=btn_hover: b.configure(bg=c))
        btn_open.bind("<Leave>", lambda _e, b=btn_open, c=btn_bg: b.configure(bg=c))

        lbl_updated = tk.Label(
            header_row,
            text=f"Alterado: {item.get('updated_at', '')}",
            bg=card_bg,
            fg=palette["muted"],
            font=("Segoe UI", 8),
        )
        lbl_updated.pack(side="right")

        # Trecho com o termo localizado
        snippet_text = item.get("snippet", "")
        lbl_snippet = tk.Label(
            card,
            text=snippet_text,
            bg=card_bg,
            fg=palette["text"],
            font=("Segoe UI", 10),
            wraplength=760,
            justify="left",
            anchor="w",
        )
        lbl_snippet.pack(fill="x", padx=14, pady=(2, 8))

        # Duplo clique no card ou no trecho abre o item correspondente
        open_handler = lambda _e, it=item: self._open_item(it)
        card.bind("<Double-Button-1>", open_handler)
        header_row.bind("<Double-Button-1>", open_handler)
        lbl_date.bind("<Double-Button-1>", open_handler)
        lbl_snippet.bind("<Double-Button-1>", open_handler)

    def _render_results(self, initial_limit: Optional[int] = None):
        self._clear_results_container()

        count = len(self.results)
        if count == 0:
            self.lbl_results_count.configure(
                text="Nenhuma anotação encontrada com os filtros informados.",
                text_color=config.COLORS["warning"],
            )
            self.btn_export_csv.configure(state="disabled")
            self.btn_prev_res.configure(state="disabled")
            self.btn_next_res.configure(state="disabled")
            self._render_empty_state(
                "Nenhuma anotação corresponde aos critérios de pesquisa.\n"
                "Tente utilizar palavras mais curtas ou verificar o período filtrado."
            )
            return

        self.btn_export_csv.configure(state="normal")
        self.btn_prev_res.configure(state="normal")
        self.btn_next_res.configure(state="normal")

        self._rendered_count = 0
        self._target_render_count = min(count, initial_limit or self.PAGE_SIZE)
        token = self._render_token
        palette = self._get_theme_palette()

        # Renderiza o primeiro lote imediatamente (preenche toda a área visível sem espera)
        first_end = min(self._target_render_count, self.INITIAL_SYNC_BATCH)
        for idx in range(0, first_end):
            self._create_result_card(self.results[idx], palette)
        self._rendered_count = first_end
        self._update_summary_label()

        if self._rendered_count < self._target_render_count:
            self._render_job_id = self.after(
                8, lambda t=token, p=palette: self._render_next_batch(t, p)
            )
        else:
            self._ensure_load_more_footer(palette)

    def _render_next_batch(self, token: int, palette: Dict[str, str]):
        self._render_job_id = None
        if token != self._render_token:
            return
        try:
            if not self.winfo_exists() or not self.results_scroll.winfo_exists():
                return
        except Exception:
            return

        batch_end = min(self._target_render_count, self._rendered_count + self.ASYNC_BATCH_SIZE)
        for idx in range(self._rendered_count, batch_end):
            self._create_result_card(self.results[idx], palette)
        self._rendered_count = batch_end
        self._update_summary_label()

        if self._rendered_count < self._target_render_count:
            self._render_job_id = self.after(
                8, lambda t=token, p=palette: self._render_next_batch(t, p)
            )
        else:
            self._ensure_load_more_footer(palette)

    def _ensure_load_more_footer(self, palette: Dict[str, str]):
        if self._load_more_frame is not None:
            try:
                self._load_more_frame.destroy()
            except Exception:
                pass
            self._load_more_frame = None

        remaining = len(self.results) - self._rendered_count
        if remaining <= 0:
            return

        next_step = min(self.PAGE_SIZE, remaining)
        footer = tk.Frame(self.results_scroll, bg=palette["btn_bg"])
        footer.pack(fill="x", padx=10, pady=(8, 12))

        btn_more = tk.Button(
            footer,
            text=f"➕ Carregar mais +{next_step} resultados (restam {remaining})",
            bg=palette["primary"],
            fg="#FFFFFF",
            activebackground=palette["primary_hover"],
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            command=self._load_more_results,
        )
        btn_more.pack(side="left", padx=(0, 8))

        btn_all = tk.Button(
            footer,
            text=f"📋 Mostrar todos ({len(self.results)})",
            bg=palette["card_bg"],
            fg=palette["text"],
            activebackground=palette["border"],
            activeforeground=palette["text"],
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            command=self._load_all_results,
        )
        btn_all.pack(side="left")

        self._load_more_frame = footer

    def _load_more_results(self):
        if self._load_more_frame is not None:
            try:
                self._load_more_frame.destroy()
            except Exception:
                pass
            self._load_more_frame = None

        self._target_render_count = min(len(self.results), self._rendered_count + self.PAGE_SIZE)
        token = self._render_token
        palette = self._get_theme_palette()
        self._render_next_batch(token, palette)

    def _load_all_results(self):
        if self._load_more_frame is not None:
            try:
                self._load_more_frame.destroy()
            except Exception:
                pass
            self._load_more_frame = None

        self._target_render_count = len(self.results)
        token = self._render_token
        palette = self._get_theme_palette()
        self._render_next_batch(token, palette)

    def refresh_theme(self):
        """Reaplica a paleta Claro/Escuro nos cards leves já renderizados."""
        if self.results:
            keep_count = max(self.PAGE_SIZE, self._rendered_count)
            self._render_results(initial_limit=keep_count)

    def _open_item(self, item: Dict[str, Any]):
        """Abre um resultado do Diário ou de Pastas & Arquivos conforme sua origem."""
        if item.get("source_type") == "note":
            if self.on_open_folder_note is not None:
                query = self.entry_query.get().strip()
                try:
                    self.on_open_folder_note(item.get("folder_id"), item.get("note_id"), highlight_query=query)
                except TypeError:
                    self.on_open_folder_note(item.get("folder_id"), item.get("note_id"))
            else:
                show_message(
                    self,
                    "Nota em Pasta",
                    f"Nota: {item.get('title')}\nPasta: {item.get('folder_path')}",
                    kind="info",
                )
        else:
            self._open_result(item["entry_date"], item["user_id"], item)

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
        self._open_item(self.results[self.selected_index])

    def _on_next_result(self):
        if not self.results:
            return
        if self.selected_index >= len(self.results) - 1:
            self.selected_index = 0
        else:
            self.selected_index += 1
        self._open_item(self.results[self.selected_index])

    def _clear_filters(self):
        self.entry_query.delete(0, "end")
        self.entry_start_date.delete(0, "end")
        self.entry_end_date.delete(0, "end")
        self.entry_exact_date.delete(0, "end")
        self.combo_scope.set("Diário e Pastas")
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

    def destroy(self):
        self._cancel_pending_render()
        super().destroy()
