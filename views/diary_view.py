import os
import tkinter as tk
from tkinter import filedialog
from typing import Optional, Callable, List
import customtkinter as ctk

import config
from models.user import User
from models.diary import DiaryEntry
from services.diary_service import DiaryService
from services.authentication_service import AuthenticationService
from services.backup_service import BackupService
from utils.date_utils import (
    get_today_iso,
    format_date_br,
    format_date_long_br,
    add_days_to_iso,
    parse_date_input,
)
from views.components.dialogs import UnsavedChangesDialog, show_message
from views.components.responsive_toolbar import ResponsiveToolbar
from services.spellcheck_service import WindowsSpellCheckService, SpellingError
from utils.syntax_highlighter import (
    convert_selection_case,
    format_and_highlight_xml,
    format_and_highlight_sql,
    clear_syntax_tags,
    auto_highlight_content,
    configure_syntax_tags,
    enable_undo_redo,
    perform_undo,
    perform_redo,
    reset_undo_stack,
)


class DiaryView(ctk.CTkFrame):
    """
    Tela principal de edição e registro do diário diário.
    - Área ampla e confortável para textos longos
    - Salvamento manual (botão e Ctrl+S) e salvamento automático opcional
    - Indicador visual em tempo real de alterações não salvas
    - Navegação rápida entre datas (anterior, hoje, próxima)
    - Suporte a seleção de usuário para perfis com permissão
    - Corretor ortográfico nativo do Windows integrado com sugestões no botão direito
    """

    def __init__(
        self,
        master,
        current_user: User,
        diary_service: DiaryService,
        auth_service: AuthenticationService,
        backup_service: BackupService,
        spell_service: Optional[WindowsSpellCheckService] = None,
        on_navigate_to_search: Optional[Callable[[], None]] = None,
        on_navigate_to_history: Optional[Callable[[str], None]] = None,
        on_navigate_to_import: Optional[Callable[[], None]] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.diary_service = diary_service
        self.auth_service = auth_service
        self.backup_service = backup_service
        self.spell_service = spell_service or WindowsSpellCheckService()

        self.on_navigate_to_search = on_navigate_to_search
        self.on_navigate_to_history = on_navigate_to_history
        self.on_navigate_to_import = on_navigate_to_import

        # O usuário cujas anotações estão sendo exibidas (pode ser outro usuário se admin autorizado)
        self.target_user = current_user
        self.current_date_iso = get_today_iso()
        self.active_entry: Optional[DiaryEntry] = None

        self.has_unsaved_changes = False
        self.autosave_timer_id = None
        self.autosave_enabled = tk.BooleanVar(value=True)

        # Controle do corretor ortográfico nativo do Windows
        self.spellcheck_timer_id = None
        self.spellcheck_enabled = tk.BooleanVar(value=self.spell_service.is_available)

        self._build_ui()
        self._load_entry_for_current_date()

        # Vincula atalho Ctrl+S na caixa de texto e na janela
        self.txt_content.bind("<Control-s>", lambda e: (self.save_current_entry(), "break")[1])
        self.txt_content.bind("<Control-S>", lambda e: (self.save_current_entry(), "break")[1])
        try:
            top = self.winfo_toplevel()
            top.bind("<Control-s>", lambda e: (self.save_current_entry(), "break")[1])
            top.bind("<Control-S>", lambda e: (self.save_current_entry(), "break")[1])
        except Exception:
            pass

    def _build_ui(self):
        # 1. Barra Superior com Navegação de Data e Usuário
        self.top_bar = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.top_bar.pack(fill="x", padx=20, pady=(15, 10))

        # Seletor de data e botões
        self.date_nav_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        self.date_nav_frame.pack(side="left", padx=15, pady=12)

        self.btn_prev_day = ctk.CTkButton(
            self.date_nav_frame,
            text="◀ Anterior",
            width=90,
            height=34,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._on_prev_day,
        )
        self.btn_prev_day.pack(side="left", padx=(0, 6))

        self.btn_today = ctk.CTkButton(
            self.date_nav_frame,
            text="📅 Hoje",
            width=75,
            height=34,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._on_go_today,
        )
        self.btn_today.pack(side="left", padx=(0, 6))

        self.btn_next_day = ctk.CTkButton(
            self.date_nav_frame,
            text="Próximo ▶",
            width=90,
            height=34,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._on_next_day,
        )
        self.btn_next_day.pack(side="left", padx=(0, 15))

        # Data atual por extenso em destaque
        self.lbl_current_date = ctk.CTkLabel(
            self.top_bar,
            text="",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_current_date.pack(side="left", padx=10)

        # Seletor de Usuário (Apenas para perfis autorizados)
        if self.current_user.can_view_other_diaries:
            self.user_select_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
            self.user_select_frame.pack(side="right", padx=15, pady=12)

            self.lbl_viewing_user = ctk.CTkLabel(
                self.user_select_frame,
                text="Diário de:",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=config.COLORS["text_muted"],
            )
            self.lbl_viewing_user.pack(side="left", padx=(0, 6))

            self.all_users = self.auth_service.list_users(self.current_user)
            user_options = [f"{u.full_name} ({u.username})" for u in self.all_users]
            current_idx = 0
            for idx, u in enumerate(self.all_users):
                if u.id == self.current_user.id:
                    current_idx = idx
                    break

            self.combo_users = ctk.CTkComboBox(
                self.user_select_frame,
                values=user_options,
                width=220,
                height=34,
                corner_radius=8,
                fg_color=config.COLORS["card_dark_alt"],
                text_color=config.COLORS["text_dark"],
                button_color=config.COLORS["card_dark_alt"],
                button_hover_color=config.COLORS["primary"],
                dropdown_fg_color=config.COLORS["card_dark"],
                dropdown_text_color=config.COLORS["text_dark"],
                dropdown_hover_color=config.COLORS["primary"],
                command=self._on_user_changed,
            )
            self.combo_users.set(user_options[current_idx] if user_options else "")
            self.combo_users.pack(side="left")

        # 2. Barra de Ações (Botões Principais com Suporte a Overflow '»')
        self.action_toolbar = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.action_toolbar.pack(fill="x", padx=20, pady=(0, 10))

        # Switch de Salvamento Automático fixado à direita
        self.switch_autosave = ctk.CTkSwitch(
            self.action_toolbar,
            text="Salvar automaticamente",
            variable=self.autosave_enabled,
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_dark"],
            progress_color=config.COLORS["primary"],
        )
        self.switch_autosave.pack(side="right", padx=15, pady=8)

        # Barra responsiva de botões de ação (esquerda)
        self.responsive_action_bar = ResponsiveToolbar(
            self.action_toolbar,
            height=36,
            item_spacing=4,
        )
        self.responsive_action_bar.pack(side="left", fill="x", expand=True, padx=(10, 8), pady=6)

        self.btn_save = self.responsive_action_bar.add_button(
            key="save",
            symbol_text="💾 Salvar",
            full_label="💾 Salvar Anotação (Ctrl+S)",
            command=self.save_current_entry,
            width=88,
            height=32,
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
        )

        self.btn_new = self.responsive_action_bar.add_button(
            key="new",
            symbol_text="➕ Nova",
            full_label="➕ Nova Anotação em Branco",
            command=self._on_new_note,
            width=78,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_search = self.responsive_action_bar.add_button(
            key="search",
            symbol_text="🔍 Buscar",
            full_label="🔍 Pesquisa Avançada no Diário",
            command=self._on_search_clicked,
            width=82,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_import = self.responsive_action_bar.add_button(
            key="import",
            symbol_text="📥 Importar",
            full_label="📥 Importar Anotações de Arquivo TXT",
            command=self._on_import_clicked,
            width=90,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_history = self.responsive_action_bar.add_button(
            key="history",
            symbol_text="📅 Histórico",
            full_label="📅 Histórico & Calendário",
            command=self._on_history_clicked,
            width=90,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_export = self.responsive_action_bar.add_button(
            key="export",
            symbol_text="📤 Exportar",
            full_label="📤 Exportar Anotação para TXT",
            command=self._on_export_clicked,
            width=88,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_print = self.responsive_action_bar.add_button(
            key="print",
            symbol_text="🖨️ Imprimir",
            full_label="🖨️ Imprimir Anotação do Dia",
            command=self._on_print_clicked,
            width=88,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        # 3. Área de Edição do Diário (Confortável e Ampla)
        self.editor_container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.editor_container.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # 3.1 Barra de Formatação de Texto Responsiva (Desfazer, Refazer, Recortar, Imprimir, MAIÚSCULO, minúsculo, XML, SQL)
        self.responsive_format_bar = ResponsiveToolbar(
            self.editor_container,
            height=36,
            fg_color=config.COLORS["card_dark_alt"],
            corner_radius=8,
            item_spacing=3,
        )
        self.responsive_format_bar.pack(fill="x", padx=12, pady=(8, 0))

        self.btn_undo = self.responsive_format_bar.add_button(
            key="undo",
            symbol_text="↩️",
            full_label="↩️ Desfazer (Ctrl+Z)",
            command=self._on_undo_clicked,
            width=36,
            height=28,
        )

        self.btn_redo = self.responsive_format_bar.add_button(
            key="redo",
            symbol_text="↪️",
            full_label="↪️ Refazer (Ctrl+Y)",
            command=self._on_redo_clicked,
            width=36,
            height=28,
        )

        self.btn_cut = self.responsive_format_bar.add_button(
            key="cut",
            symbol_text="✂️",
            full_label="✂️ Recortar Seleção (Ctrl+X)",
            command=self._on_cut_clicked,
            width=36,
            height=28,
        )

        self.btn_fmt_print = self.responsive_format_bar.add_button(
            key="print_fmt",
            symbol_text="🖨️",
            full_label="🖨️ Imprimir / Visualizar Impressão",
            command=self._on_print_clicked,
            width=36,
            height=28,
        )

        self.responsive_format_bar.add_separator(key="sep1", width=10)

        self.btn_uppercase = self.responsive_format_bar.add_button(
            key="uppercase",
            symbol_text="🔠",
            full_label="🔠 Converter para MAIÚSCULO",
            command=self._on_uppercase_clicked,
            width=36,
            height=28,
        )

        self.btn_lowercase = self.responsive_format_bar.add_button(
            key="lowercase",
            symbol_text="🔡",
            full_label="🔡 Converter para minúsculo",
            command=self._on_lowercase_clicked,
            width=36,
            height=28,
        )

        self.responsive_format_bar.add_separator(key="sep2", width=10)

        self.btn_format_xml = self.responsive_format_bar.add_button(
            key="xml",
            symbol_text="</>",
            full_label="</> Formatar e Colorir XML",
            command=self._on_format_xml_clicked,
            width=42,
            height=28,
            hover_color="#0284C7",
        )

        self.btn_format_sql = self.responsive_format_bar.add_button(
            key="sql",
            symbol_text="SQL",
            full_label="🗄️ Formatar e Colorir SQL",
            command=self._on_format_sql_clicked,
            width=42,
            height=28,
            hover_color="#BE185D",
        )

        self.btn_clear_colors = self.responsive_format_bar.add_button(
            key="clear_colors",
            symbol_text="🎨",
            full_label="🎨 Limpar Cores de Sintaxe",
            command=self._on_clear_syntax_colors_clicked,
            width=36,
            height=28,
            fg_color="transparent",
        )

        self.txt_content = ctk.CTkTextbox(
            self.editor_container,
            wrap="word",
            font=ctk.CTkFont(family="Segoe UI", size=15),
            corner_radius=10,
            border_width=0,
            fg_color="transparent",
            text_color=config.COLORS["text_dark"],
            undo=True,
            autoseparators=True,
            maxundo=-1,
        )
        self.txt_content.pack(fill="both", expand=True, padx=15, pady=(6, 15))
        self.txt_content.bind("<KeyRelease>", self._on_text_modified)
        self.txt_content._textbox.bind("<<Paste>>", self._on_paste)
        enable_undo_redo(self.txt_content, on_change_callback=self._on_text_modified)

        # Configura sublinhado de erros ortográficos, cores de sintaxe e menu de contexto do botão direito
        self._configure_spellcheck_tags()
        configure_syntax_tags(self.txt_content._textbox)
        self.txt_content._textbox.bind("<Button-3>", self._on_textbox_context_menu)
        self.txt_content._textbox.bind("<Button-2>", self._on_textbox_context_menu)

        # 4. Barra de Status Inferior
        self.status_bar = ctk.CTkFrame(
            self,
            height=36,
            corner_radius=8,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.status_bar.pack(fill="x", padx=20, pady=(0, 15))

        self.lbl_save_status = ctk.CTkLabel(
            self.status_bar,
            text="🟢 Carregado",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["success"],
        )
        self.lbl_save_status.pack(side="left", padx=15, pady=6)

        # Botão/indicador do Corretor Ortográfico Nativo do Windows
        lang_label = self.spell_service.active_language or "pt-BR"
        initial_spell_text = f"🔤 Ortografia: {lang_label}" if self.spell_service.is_available else "🔤 Ortografia: Indisponível"
        self.btn_spell_status = ctk.CTkButton(
            self.status_bar,
            text=initial_spell_text,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_muted"],
            command=self._toggle_spellcheck,
        )
        self.btn_spell_status.pack(side="left", padx=10, pady=5)

        self.lbl_word_count = ctk.CTkLabel(
            self.status_bar,
            text="0 palavras | 0 caracteres",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_word_count.pack(side="right", padx=15, pady=6)

    def _update_date_header(self):
        long_date = format_date_long_br(self.current_date_iso)
        self.lbl_current_date.configure(text=long_date)

    def _load_entry_for_current_date(self):
        """Carrega a anotação para a data selecionada no editor."""
        self._update_date_header()

        # Cancela qualquer timer de autosave anterior
        if self.autosave_timer_id:
            self.after_cancel(self.autosave_timer_id)
            self.autosave_timer_id = None

        self.active_entry = self.diary_service.get_or_create_entry(
            self.target_user.id, self.current_date_iso
        )

        content = self.active_entry.content or ""
        self.txt_content.delete("1.0", "end")
        self.txt_content.insert("1.0", content)
        reset_undo_stack(self.txt_content)
        auto_highlight_content(self.txt_content)

        self.has_unsaved_changes = False
        self._update_status_indicator(saved=True, timestamp=self.active_entry.updated_at)
        self._update_counts()
        self._schedule_spellcheck()

    def _update_counts(self):
        text = self.txt_content.get("1.0", "end-1c")
        chars = len(text)
        words = len(text.split()) if text.strip() else 0
        self.lbl_word_count.configure(text=f"{words} palavras | {chars:,} caracteres")

    def _on_text_modified(self, event=None):
        """Detecta digitação e agenda o salvamento automático se habilitado."""
        self._update_counts()
        self._schedule_spellcheck()

        current_text = self.txt_content.get("1.0", "end-1c")
        original_text = self.active_entry.content if self.active_entry else ""

        if current_text != original_text:
            if not self.has_unsaved_changes:
                self.has_unsaved_changes = True
                self._update_status_indicator(saved=False)

            # Agenda autosave se habilitado
            if self.autosave_enabled.get():
                if self.autosave_timer_id:
                    self.after_cancel(self.autosave_timer_id)
                self.autosave_timer_id = self.after(
                    config.AUTOSAVE_DELAY_SECONDS * 1000, self._handle_autosave
                )
        else:
            if self.has_unsaved_changes:
                self.has_unsaved_changes = False
                self._update_status_indicator(saved=True, timestamp=self.active_entry.updated_at if self.active_entry else "")

    def _update_status_indicator(self, saved: bool, timestamp: str = ""):
        if saved:
            if timestamp:
                self.lbl_save_status.configure(
                    text=f"🟢 Salvo às {timestamp.split(' ')[-1]}",
                    text_color=config.COLORS["success"],
                )
            else:
                self.lbl_save_status.configure(
                    text="🟢 Salvo",
                    text_color=config.COLORS["success"],
                )
        else:
            self.lbl_save_status.configure(
                text="⚪ Alterações não salvas *",
                text_color=config.COLORS["warning"],
            )

    def _handle_autosave(self):
        """Executa o salvamento automático silencioso."""
        if self.has_unsaved_changes:
            self.save_current_entry(silent=True)

    def save_current_entry(self, silent: bool = False) -> bool:
        """Salva a anotação atual no banco de dados."""
        if self.autosave_timer_id:
            self.after_cancel(self.autosave_timer_id)
            self.autosave_timer_id = None

        content = self.txt_content.get("1.0", "end-1c")
        try:
            self.lbl_save_status.configure(
                text="🟡 Salvando...",
                text_color=config.COLORS["warning"],
            )
            self.update_idletasks()

            saved_entry = self.diary_service.save_entry(
                self.target_user.id, self.current_date_iso, content
            )
            self.active_entry = saved_entry
            self.has_unsaved_changes = False
            self._update_status_indicator(saved=True, timestamp=saved_entry.updated_at)

            if not silent:
                # Feedback sutil de sucesso
                self.btn_save.configure(fg_color=config.COLORS["success"])
                self.after(800, lambda: self.btn_save.configure(fg_color=config.COLORS["primary"]))

            return True
        except Exception as e:
            self.lbl_save_status.configure(
                text=f"❌ Erro ao salvar: {str(e)}",
                text_color=config.COLORS["danger"],
            )
            if not silent:
                show_message(self, "Erro", f"Não foi possível salvar a anotação:\n{str(e)}", kind="danger")
            return False

    def confirm_discard_if_unsaved(self) -> bool:
        """
        Verifica se há alterações pendentes antes de mudar de tela ou data.
        Retorna True para prosseguir, False para abortar.
        """
        if not self.has_unsaved_changes:
            return True

        diag = UnsavedChangesDialog(self, format_date_br(self.current_date_iso))
        if diag.result == "save":
            return self.save_current_entry()
        elif diag.result == "discard":
            self.has_unsaved_changes = False
            return True
        else:
            return False

    def set_date(self, date_iso: str) -> bool:
        """Define a data exibida, verificando alterações pendentes."""
        if not self.confirm_discard_if_unsaved():
            return False
        self.current_date_iso = date_iso
        self._load_entry_for_current_date()
        return True

    def _on_prev_day(self):
        new_date = add_days_to_iso(self.current_date_iso, -1)
        self.set_date(new_date)

    def _on_next_day(self):
        new_date = add_days_to_iso(self.current_date_iso, 1)
        self.set_date(new_date)

    def _on_go_today(self):
        self.set_date(get_today_iso())

    def _on_new_note(self):
        """Prepara uma nova anotação em branco para a data selecionada."""
        if not self.confirm_discard_if_unsaved():
            return
        try:
            self.txt_content._textbox.edit_separator()
        except Exception:
            pass
        self.txt_content.delete("1.0", "end")
        try:
            self.txt_content._textbox.edit_separator()
        except Exception:
            pass
        self.txt_content.focus_set()
        self._on_text_modified()

    def _on_user_changed(self, selected_str: str):
        if not self.confirm_discard_if_unsaved():
            # Restaura seleção anterior no combobox
            current_label = f"{self.target_user.full_name} ({self.target_user.username})"
            self.combo_users.set(current_label)
            return

        for u in self.all_users:
            if f"{u.full_name} ({u.username})" == selected_str:
                self.target_user = u
                break
        self._load_entry_for_current_date()

    def _on_search_clicked(self):
        if not self.confirm_discard_if_unsaved():
            return
        if self.on_navigate_to_search:
            self.on_navigate_to_search()

    def _on_history_clicked(self):
        if not self.confirm_discard_if_unsaved():
            return
        if self.on_navigate_to_history:
            self.on_navigate_to_history(self.current_date_iso)

    def _on_import_clicked(self):
        if not self.confirm_discard_if_unsaved():
            return
        if self.on_navigate_to_import:
            self.on_navigate_to_import()

    def _on_export_clicked(self):
        """Exporta a anotação do dia para um arquivo TXT."""
        date_br = format_date_br(self.current_date_iso).replace("/", " ")
        suggested_name = f"{date_br}.txt"

        file_path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar Anotação para TXT",
            initialfile=suggested_name,
            defaultextension=".txt",
            filetypes=[("Arquivos de Texto", "*.txt")],
        )
        if file_path:
            # Salva antes de exportar para garantir dados atualizados
            self.save_current_entry(silent=True)
            if self.active_entry:
                ok, msg = self.backup_service.export_entry_to_txt(self.active_entry, file_path)
                if ok:
                    show_message(self, "Sucesso", msg, kind="success")
                else:
                    show_message(self, "Erro", msg, kind="danger")

    # =========================================================================
    # Métodos do Corretor Ortográfico Nativo do Windows
    # =========================================================================

    def _configure_spellcheck_tags(self):
        """Configura a tag visual para realce de palavras com erros ortográficos."""
        try:
            mode = ctk.get_appearance_mode()
            is_dark = (mode == "Dark")
            danger_color = config.COLORS["danger"][1 if is_dark else 0]
            self.txt_content._textbox.tag_configure(
                "spelling_error",
                underline=True,
                underlinefg=danger_color,
            )
        except Exception:
            pass

    def _schedule_spellcheck(self):
        """Agenda uma verificação ortográfica com debounce para não impactar a digitação."""
        if not self.spellcheck_enabled.get() or not self.spell_service.is_available:
            self._clear_spelling_tags()
            return

        if self.spellcheck_timer_id is not None:
            try:
                self.after_cancel(self.spellcheck_timer_id)
            except Exception:
                pass

        self.spellcheck_timer_id = self.after(400, self._run_spellcheck)

    def _clear_spelling_tags(self):
        """Remove todas as marcações de erros ortográficos da área de texto."""
        try:
            self.txt_content._textbox.tag_remove("spelling_error", "1.0", "end")
        except Exception:
            pass

    def _run_spellcheck(self):
        """Executa a verificação ortográfica nativa do Windows no conteúdo atual."""
        self.spellcheck_timer_id = None
        try:
            if not self.winfo_exists() or not self.txt_content.winfo_exists():
                return
        except Exception:
            return

        if not self.spellcheck_enabled.get() or not self.spell_service.is_available:
            self._clear_spelling_tags()
            return

        self._configure_spellcheck_tags()
        text = self.txt_content.get("1.0", "end-1c")
        if not text or not text.strip():
            self._clear_spelling_tags()
            lang = self.spell_service.active_language or "pt-BR"
            self.btn_spell_status.configure(
                text=f"🔤 Ortografia: {lang}",
                text_color=config.COLORS["text_muted"],
            )
            return

        errors = self.spell_service.check_text(text)
        self._clear_spelling_tags()

        tb = self.txt_content._textbox
        active_errors_count = 0
        for err in errors:
            start_idx = f"1.0 + {err.start} chars"
            end_idx = f"1.0 + {err.start + err.length} chars"
            try:
                # Não sublinha palavras que já fazem parte de tags XML ou comandos SQL coloridos
                if any(t.startswith("syntax_") for t in tb.tag_names(start_idx)):
                    continue
                tb.tag_add("spelling_error", start_idx, end_idx)
                active_errors_count += 1
            except Exception:
                pass

        lang = self.spell_service.active_language or "pt-BR"
        if active_errors_count == 0:
            self.btn_spell_status.configure(
                text=f"🔤 Ortografia: {lang} (OK)",
                text_color=config.COLORS["text_muted"],
            )
        else:
            qtd = active_errors_count
            sufixo = "erro" if qtd == 1 else "erros"
            self.btn_spell_status.configure(
                text=f"🔤 {qtd} {sufixo}",
                text_color=config.COLORS["danger"],
            )

    def _toggle_spellcheck(self):
        """Alterna a ativação do corretor ortográfico."""
        if not self.spell_service.is_available:
            show_message(
                self,
                "Corretor Ortográfico",
                "A API de correção ortográfica nativa do Windows não está disponível neste sistema.",
                kind="warning",
            )
            return

        new_state = not self.spellcheck_enabled.get()
        self.spellcheck_enabled.set(new_state)

        if new_state:
            lang = self.spell_service.active_language or "pt-BR"
            self.btn_spell_status.configure(
                text=f"🔤 Ortografia: {lang}",
                text_color=config.COLORS["text_muted"],
            )
            self._run_spellcheck()
        else:
            self._clear_spelling_tags()
            self.btn_spell_status.configure(
                text="🔤 Corretor: Desativado",
                text_color=config.COLORS["text_muted"],
            )

    def _on_textbox_context_menu(self, event):
        """Exibe o menu de contexto moderno do botão direito com sugestões ortográficas."""
        text_widget = self.txt_content._textbox
        click_idx = text_widget.index(f"@{event.x},{event.y}")

        # Se não houver seleção de texto ativa, posiciona o cursor onde foi clicado
        if not text_widget.tag_ranges("sel"):
            text_widget.mark_set("insert", click_idx)

        # Detecta se o clique foi sobre uma palavra com erro
        tags_at_click = text_widget.tag_names(click_idx)
        has_spelling_error = "spelling_error" in tags_at_click

        word_range = None
        err_word = ""
        if has_spelling_error:
            # Localiza o range exato da palavra com erro
            r = text_widget.tag_prevrange("spelling_error", click_idx + "+1c")
            if r:
                word_range = r
                err_word = text_widget.get(r[0], r[1]).strip()

        # Configura cores do menu de acordo com o tema
        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")
        menu_bg = config.COLORS["card_dark"][1 if is_dark else 0]
        menu_fg = config.COLORS["text_dark"][1 if is_dark else 0]
        active_bg = config.COLORS["primary"][1 if is_dark else 0]
        active_fg = "#FFFFFF"

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=menu_bg,
            fg=menu_fg,
            activebackground=active_bg,
            activeforeground=active_fg,
            font=("Segoe UI", 10),
            relief="flat",
            bd=1,
        )

        # Se houver erro ortográfico identificado na palavra clicada
        if has_spelling_error and err_word and word_range:
            suggestions = self.spell_service.get_suggestions(err_word, limit=5)
            if suggestions:
                for sug in suggestions:
                    menu.add_command(
                        label=f"✔  {sug}",
                        font=("Segoe UI", 10, "bold"),
                        command=lambda s=sug, st=word_range[0], en=word_range[1]: self._replace_spelling_error(st, en, s),
                    )
            else:
                menu.add_command(label="(Nenhuma sugestão do Windows)", state="disabled")

            menu.add_separator()
            menu.add_command(
                label=f"➕ Adicionar '{err_word}' ao Dicionário",
                command=lambda w=err_word: self._add_to_dict_and_refresh(w),
            )
            menu.add_command(
                label=f"👁️ Ignorar '{err_word}'",
                command=lambda w=err_word: self._ignore_word_and_refresh(w),
            )
            menu.add_separator()

        # Comandos padrão de edição
        has_selection = bool(text_widget.tag_ranges("sel"))
        menu.add_command(
            label="↩️ Desfazer (Ctrl+Z)",
            command=self._on_undo_clicked,
        )
        menu.add_command(
            label="↪️ Refazer (Ctrl+Y)",
            command=self._on_redo_clicked,
        )
        menu.add_separator()
        menu.add_command(
            label="✂ Recortar",
            state="normal" if has_selection else "disabled",
            command=lambda: text_widget.event_generate("<<Cut>>"),
        )
        menu.add_command(
            label="📋 Copiar",
            state="normal" if has_selection else "disabled",
            command=lambda: text_widget.event_generate("<<Copy>>"),
        )
        menu.add_command(
            label="📄 Colar",
            command=self._on_paste,
        )
        menu.add_separator()
        menu.add_command(
            label="🔠 Converter Seleção para MAIÚSCULO",
            state="normal" if has_selection else "disabled",
            command=self._on_uppercase_clicked,
        )
        menu.add_command(
            label="🔡 Converter Seleção para minúsculo",
            state="normal" if has_selection else "disabled",
            command=self._on_lowercase_clicked,
        )
        menu.add_separator()
        menu.add_command(
            label="</> Formatar / Colorir como XML",
            command=self._on_format_xml_clicked,
        )
        menu.add_command(
            label="🗄️ Formatar / Colorir como SQL",
            command=self._on_format_sql_clicked,
        )
        menu.add_command(
            label="🎨 Limpar Cores de Sintaxe",
            command=self._on_clear_syntax_colors_clicked,
        )
        menu.add_separator()
        menu.add_command(
            label="Selecionar Tudo",
            command=self._select_all_text,
        )

        if self.spell_service.is_available:
            menu.add_separator()
            toggle_text = "🔲 Desativar Corretor Ortográfico" if self.spellcheck_enabled.get() else "☑ Ativar Corretor Ortográfico"
            menu.add_command(label=toggle_text, command=self._toggle_spellcheck)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _replace_spelling_error(self, start_idx: str, end_idx: str, replacement: str):
        """Substitui uma palavra com erro pela sugestão escolhida pelo usuário."""
        text_widget = self.txt_content._textbox
        try:
            text_widget.edit_separator()
        except Exception:
            pass
        text_widget.delete(start_idx, end_idx)
        text_widget.insert(start_idx, replacement)
        try:
            text_widget.edit_separator()
        except Exception:
            pass
        self._on_text_modified()
        self._run_spellcheck()

    def _on_undo_clicked(self):
        """Desfaz a última ação (digitação, colagem ou formatação)."""
        perform_undo(self.txt_content, on_change_callback=self._on_text_modified)

    def _on_redo_clicked(self):
        """Refaz a última ação desfeita."""
        perform_redo(self.txt_content, on_change_callback=self._on_text_modified)

    def _add_to_dict_and_refresh(self, word: str):
        """Adiciona ao dicionário personalizado do Windows e re-executa checagem."""
        self.spell_service.add_to_dictionary(word)
        self._run_spellcheck()

    def _ignore_word_and_refresh(self, word: str):
        """Ignora a palavra na sessão e remove a marcação de erro."""
        self.spell_service.ignore_word(word)
        self._run_spellcheck()

    def _select_all_text(self):
        """Seleciona todo o texto do diário."""
        text_widget = self.txt_content._textbox
        text_widget.tag_add("sel", "1.0", "end-1c")
        text_widget.mark_set("insert", "1.0")

    def _on_uppercase_clicked(self):
        """Converte o texto selecionado para MAIÚSCULO."""
        ok, msg = convert_selection_case(self.txt_content, uppercase=True)
        if not ok:
            show_message(self, "Converter para MAIÚSCULO", msg, kind="info")
            return
        self._on_text_modified()

    def _on_lowercase_clicked(self):
        """Converte o texto selecionado para minúsculo."""
        ok, msg = convert_selection_case(self.txt_content, uppercase=False)
        if not ok:
            show_message(self, "Converter para minúsculo", msg, kind="info")
            return
        self._on_text_modified()

    def _on_format_xml_clicked(self):
        """Formata e aplica cores de sintaxe XML ao texto selecionado (ou a toda a nota)."""
        if not format_and_highlight_xml(self.txt_content, indent_xml=True):
            show_message(self, "Formatar XML", "Não há texto na anotação para formatar como XML.", kind="info")
            return
        self._on_text_modified()

    def _on_format_sql_clicked(self):
        """Formata e aplica cores de sintaxe SQL ao texto selecionado (ou a toda a nota)."""
        if not format_and_highlight_sql(self.txt_content, format_keywords=True):
            show_message(self, "Formatar SQL", "Não há texto na anotação para formatar como SQL.", kind="info")
            return
        self._on_text_modified()

    def _on_clear_syntax_colors_clicked(self):
        """Remove a coloração de sintaxe XML/SQL do trecho selecionado ou de todo o texto."""
        tb = self.txt_content._textbox
        sel = tb.tag_ranges("sel")
        if sel:
            clear_syntax_tags(tb, tb.index("sel.first"), tb.index("sel.last"))
        else:
            clear_syntax_tags(tb, "1.0", "end")
        self._run_spellcheck()

    def _on_paste(self, event=None):
        """
        Trata a colagem de texto no Diário do Dia garantindo que o cursor vá para
        o fim do texto, role a visualização para exibir a última informação colada
        e registre um separador de Undo para que o Ctrl+Z desfaça exatamente o que foi colado.
        """
        text_widget = self.txt_content._textbox
        try:
            clipboard_text = self.clipboard_get()
        except tk.TclError:
            return "break"

        if not clipboard_text:
            return "break"

        try:
            text_widget.edit_separator()
        except Exception:
            pass

        # Se houver texto selecionado, substitui a seleção
        if text_widget.tag_ranges("sel"):
            text_widget.delete("sel.first", "sel.last")

        # Insere o texto colado na posição atual do cursor
        text_widget.insert("insert", clipboard_text)

        try:
            text_widget.edit_separator()
        except Exception:
            pass

        auto_highlight_content(self.txt_content)

        # Move o cursor para o fim do texto e rola a visão até a última linha colada
        text_widget.mark_set("insert", "end-1c")
        text_widget.see("insert")
        text_widget.update_idletasks()
        text_widget.see("end-1c")
        text_widget.focus_set()

        self._on_text_modified()
        self.after(15, self._scroll_to_cursor_end)
        return "break"

    def _scroll_to_cursor_end(self):
        """Garante que após o cálculo de quebra de linhas (word wrap) a visão mostre o fim do texto."""
        try:
            if not self.winfo_exists() or not self.txt_content.winfo_exists():
                return
            text_widget = self.txt_content._textbox
            text_widget.mark_set("insert", "end-1c")
            text_widget.see("end-1c")
        except Exception:
            pass

    def _on_cut_clicked(self):
        """Recorta o texto selecionado e registra no histórico de desfazer."""
        try:
            self.txt_content._textbox.event_generate("<<Cut>>")
            self._on_text_modified()
        except Exception:
            pass

    def _on_print_clicked(self):
        """Gera visualização de impressão e abre para imprimir."""
        self._print_entry()

    def _print_entry(self):
        """Salva temporariamente e abre a janela nativa de impressão do Windows."""
        try:
            date_br = format_date_br(self.current_date_iso)
            author = self.target_user.full_name or self.target_user.username
            content = self.txt_content.get("1.0", "end-1c")

            import tempfile
            import subprocess
            temp_file = os.path.join(tempfile.gettempdir(), f"diario_{self.current_date_iso}.txt")
            header = f"DIÁRIO DE ANOTAÇÕES - {date_br}\nAutor: {author}\n" + ("=" * 50) + "\n\n"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(header + content)

            if os.name == "nt":
                # Abre no Notepad para visualização ou impressão direta
                os.startfile(temp_file, "open")
            else:
                subprocess.Popen(["xdg-open", temp_file])
        except Exception as e:
            show_message(self, "Imprimir", f"Não foi possível abrir o arquivo para impressão:\n{e}", kind="warning")

    def destroy(self):
        """Cancela timers pendentes antes de destruir a view."""
        if self.spellcheck_timer_id is not None:
            try:
                self.after_cancel(self.spellcheck_timer_id)
            except Exception:
                pass
            self.spellcheck_timer_id = None

        if self.autosave_timer_id is not None:
            try:
                self.after_cancel(self.autosave_timer_id)
            except Exception:
                pass
            self.autosave_timer_id = None

        super().destroy()
