import os
import tkinter as tk
import customtkinter as ctk
from typing import Optional, Callable, Tuple
import config
from services.diary_service import DiaryService
from utils.date_utils import format_date_br, format_date_long_br
from views.components.responsive_toolbar import ResponsiveToolbar
from utils.window_utils import center_modal_on_parent
from utils.syntax_highlighter import (
    convert_selection_case,
    format_and_highlight_xml,
    format_and_highlight_sql,
    auto_highlight_content,
    configure_syntax_tags,
    enable_undo_redo,
    perform_undo,
    perform_redo,
    reset_undo_stack,
    highlight_search_matches,
    focus_search_match,
    clear_search_highlights,
)
from utils.rich_text import (
    RichTextController,
    AVAILABLE_FONTS,
    AVAILABLE_FONT_SIZES,
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
)
from utils.editor_history import (
    commit_history_before_action,
    record_history_after_action,
)


def _fit_modal_height(win, parent, width: int, min_height: int, max_height: int = 580):
    """Ajusta a altura do modal ao conteúdo real sem esmagar os botões inferiores."""
    try:
        win.update_idletasks()
        try:
            scaling = float(win._get_window_scaling()) or 1.0
        except Exception:
            scaling = 1.0
        req_h = int(win.winfo_reqheight() / scaling) + 12
        final_h = max(min_height, min(max_height, req_h))
        center_modal_on_parent(win, parent, width, final_h)
    except Exception:
        pass


class UnsavedChangesDialog(ctk.CTkToplevel):
    """
    Diálogo moderno com 3 opções ao tentar sair com alterações não salvas:
    - Salvar e Continuar
    - Descartar Alterações
    - Cancelar
    """
    def __init__(self, parent, date_br: str, custom_message: Optional[str] = None):
        super().__init__(parent)
        self.title("Alterações Não Salvas")
        self.geometry("460x240")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = "cancel"

        center_modal_on_parent(self, parent, 460, 240)

        self.container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.container.pack(fill="both", expand=True, padx=15, pady=15)

        self.lbl_title = ctk.CTkLabel(
            self.container,
            text="⚠️ Atenção: Alterações Não Salvas",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["warning"],
        )
        self.lbl_title.pack(pady=(15, 8))

        self.btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.btn_frame.pack(side="bottom", fill="x", pady=(10, 15), padx=15)

        self.btn_save = ctk.CTkButton(
            self.btn_frame,
            text="💾 Salvar",
            width=110,
            height=34,
            fg_color=config.COLORS["success"],
            hover_color=config.COLORS["success_hover"],
            text_color="#FFFFFF",
            command=self._on_save,
        )
        self.btn_save.pack(side="left", padx=5)

        self.btn_discard = ctk.CTkButton(
            self.btn_frame,
            text="🗑️ Descartar",
            width=110,
            height=34,
            fg_color=config.COLORS["danger"],
            hover_color=config.COLORS["danger_hover"],
            text_color="#FFFFFF",
            command=self._on_discard,
        )
        self.btn_discard.pack(side="left", padx=5)

        self.btn_cancel = ctk.CTkButton(
            self.btn_frame,
            text="Cancelar",
            width=90,
            height=34,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._on_cancel,
        )
        self.btn_cancel.pack(side="right", padx=5)

        msg_text = custom_message or (
            f"A anotação do dia {date_br} possui alterações que ainda não foram salvas no banco de dados.\n\nO que você deseja fazer?"
        )
        self.lbl_msg = ctk.CTkLabel(
            self.container,
            text=msg_text,
            font=ctk.CTkFont(size=13),
            text_color=config.COLORS["text_dark"],
            wraplength=400,
            justify="center",
        )
        self.lbl_msg.pack(pady=5, padx=15, expand=True)

        _fit_modal_height(self, parent, 460, min_height=230)
        self.wait_window(self)

    def _on_save(self):
        self.result = "save"
        self.destroy()

    def _on_discard(self):
        self.result = "discard"
        self.destroy()

    def _on_cancel(self):
        self.result = "cancel"
        self.destroy()


class MessageDialog(ctk.CTkToplevel):
    """Diálogo modal customizado moderno para mensagens informativas, alertas e confirmações."""
    def __init__(self, parent, title: str, message: str, kind: str = "info", show_cancel: bool = False):
        super().__init__(parent)
        self.title(title)
        self.geometry("460x220")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = False

        center_modal_on_parent(self, parent, 460, 220)

        self.container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.container.pack(fill="both", expand=True, padx=15, pady=15)

        icon_map = {
            "info": ("ℹ️", config.COLORS["primary"]),
            "success": ("✅", config.COLORS["success"]),
            "warning": ("⚠️", config.COLORS["warning"]),
            "danger": ("❌", config.COLORS["danger"]),
        }
        icon, color = icon_map.get(kind, ("ℹ️", config.COLORS["primary"]))

        self.lbl_title = ctk.CTkLabel(
            self.container,
            text=f"{icon} {title}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=color,
        )
        self.lbl_title.pack(pady=(15, 8))

        # Empacota os botões primeiro com side="bottom" para garantir altura integral
        self.btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.btn_frame.pack(side="bottom", pady=(8, 15))

        if show_cancel:
            self.btn_confirm = ctk.CTkButton(
                self.btn_frame,
                text="Confirmar",
                width=110,
                height=34,
                fg_color=color if kind in ("danger", "success") else config.COLORS["primary"],
                hover_color=config.COLORS["primary_hover"],
                text_color="#FFFFFF",
                command=self._confirm,
            )
            self.btn_confirm.pack(side="left", padx=10)

            self.btn_cancel = ctk.CTkButton(
                self.btn_frame,
                text="Cancelar",
                width=110,
                height=34,
                fg_color=config.COLORS["card_dark_alt"],
                hover_color=config.COLORS["border_dark"],
                text_color=config.COLORS["button_text"],
                command=self._cancel,
            )
            self.btn_cancel.pack(side="right", padx=10)
        else:
            self.btn_ok = ctk.CTkButton(
                self.btn_frame,
                text="OK",
                width=120,
                height=34,
                fg_color=config.COLORS["primary"],
                hover_color=config.COLORS["primary_hover"],
                text_color="#FFFFFF",
                command=self._confirm,
            )
            self.btn_ok.pack()

        self.lbl_msg = ctk.CTkLabel(
            self.container,
            text=message,
            font=ctk.CTkFont(size=13),
            text_color=config.COLORS["text_dark"],
            wraplength=400,
            justify="center",
        )
        self.lbl_msg.pack(pady=5, padx=15, expand=True)

        _fit_modal_height(self, parent, 460, min_height=210)
        self.wait_window(self)

    def _confirm(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


def show_message(parent, title: str, message: str, kind: str = "info"):
    MessageDialog(parent, title, message, kind=kind, show_cancel=False)


def ask_confirmation(parent, title: str, message: str, kind: str = "warning") -> bool:
    diag = MessageDialog(parent, title, message, kind=kind, show_cancel=True)
    return diag.result


class DiaryNoteReaderDialog(ctk.CTkToplevel):
    """
    Janela dedicada de leitura de anotação do diário (aberta a partir da Pesquisa Avançada
    ou do Histórico & Calendário).
    Inicia em modo somente leitura e oferece um botão '✏️ Editar Nota' caso o usuário
    deseje habilitar a edição ou abrir no Diário do Dia.
    """

    def __init__(
        self,
        parent,
        diary_service: DiaryService,
        user_id: int,
        date_iso: str,
        author_label: Optional[str] = None,
        highlight_query: Optional[str] = None,
        on_entry_saved: Optional[Callable[[], None]] = None,
        on_open_in_diary: Optional[Callable[[str, int], None]] = None,
    ):
        super().__init__(parent.winfo_toplevel())
        self.diary_service = diary_service
        self.user_id = user_id
        self.date_iso = date_iso
        self.author_label = author_label
        self.highlight_query = (highlight_query or "").strip()
        self._search_matches = []
        self._current_match_idx = -1
        self.on_entry_saved = on_entry_saved
        self.on_open_in_diary = on_open_in_diary

        self.date_br = format_date_br(self.date_iso)
        self.date_long = format_date_long_br(self.date_iso)

        self.title(f"Visualização de Anotação - {self.date_br}")
        self.geometry("820x600")
        self.minsize(640, 440)
        self.transient(parent.winfo_toplevel())

        self._icon_photo = None
        self._apply_icon()
        self.after(220, self._apply_icon)

        center_modal_on_parent(self, parent.winfo_toplevel(), 820, 600)

        self.entry = self.diary_service.get_or_create_entry(self.user_id, self.date_iso)
        self.original_content = self.entry.content or ""
        self.original_formatting = getattr(self.entry, "formatting_json", "") or ""
        self.is_editing = False
        self.has_unsaved_changes = False

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_escape())
        self.bind("<Control-s>", lambda e: self._on_ctrl_s())
        self.bind("<Control-S>", lambda e: self._on_ctrl_s())

        self._build_ui()
        self._load_content_into_viewer()
        self.lift()
        self.focus_force()

    def _apply_icon(self):
        try:
            if not self.winfo_exists():
                return
            if os.path.isfile(config.ICON_ICO_PATH):
                self.iconbitmap(config.ICON_ICO_PATH)
            if os.path.isfile(config.ICON_PNG_PATH):
                self._icon_photo = tk.PhotoImage(file=config.ICON_PNG_PATH)
                self.wm_iconphoto(False, self._icon_photo)
        except Exception:
            pass

    def _build_ui(self):
        # 1. Cabeçalho com Data, Autor e Badge de Modo (Somente Leitura / Edição)
        self.header_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.header_card.pack(fill="x", padx=18, pady=(15, 8))

        header_top = ctk.CTkFrame(self.header_card, fg_color="transparent")
        header_top.pack(fill="x", padx=16, pady=(12, 4))

        self.lbl_date_title = ctk.CTkLabel(
            header_top,
            text=f"📅 {self.date_long}",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        self.lbl_date_title.pack(side="left")

        self.lbl_mode_badge = ctk.CTkLabel(
            header_top,
            text="🔒 Somente Leitura",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
            corner_radius=6,
            padx=10,
            pady=4,
        )
        self.lbl_mode_badge.pack(side="right")

        header_sub = ctk.CTkFrame(self.header_card, fg_color="transparent")
        header_sub.pack(fill="x", padx=16, pady=(0, 10))

        self.lbl_meta = ctk.CTkLabel(
            header_sub,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        self.lbl_meta.pack(side="left")

        # 2. Barra de Ações (Botão de Edição, Salvar, Copiar, Ir para Diário)
        self.toolbar = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.toolbar.pack(fill="x", padx=18, pady=(0, 8))

        self.btn_edit = ctk.CTkButton(
            self.toolbar,
            text="✏️ Editar Nota",
            width=140,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._enable_edit_mode,
        )
        self.btn_edit.pack(side="left", padx=(12, 6), pady=8)

        self.btn_save = ctk.CTkButton(
            self.toolbar,
            text="💾 Salvar Alterações (Ctrl+S)",
            width=195,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["success"],
            hover_color=config.COLORS["success_hover"],
            text_color="#FFFFFF",
            command=self.save_changes,
        )

        self.btn_cancel_edit = ctk.CTkButton(
            self.toolbar,
            text="↩️ Cancelar Edição",
            width=135,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._cancel_edit_mode,
        )

        self.btn_copy = ctk.CTkButton(
            self.toolbar,
            text="📋 Copiar Texto",
            width=125,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._copy_to_clipboard,
        )
        self.btn_copy.pack(side="left", padx=6, pady=8)

        if self.on_open_in_diary is not None:
            self.btn_open_diary = ctk.CTkButton(
                self.toolbar,
                text="📝 Abrir no Diário do Dia",
                width=175,
                height=34,
                corner_radius=8,
                font=ctk.CTkFont(size=12),
                fg_color=config.COLORS["card_dark_alt"],
                hover_color=config.COLORS["primary"],
                text_color=config.COLORS["button_text"],
                command=self._handle_open_in_diary,
            )
            self.btn_open_diary.pack(side="left", padx=6, pady=8)

        self.btn_close = ctk.CTkButton(
            self.toolbar,
            text="Fechar",
            width=90,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["danger"],
            text_color=config.COLORS["button_text"],
            command=self._on_close,
        )
        self.btn_close.pack(side="right", padx=12, pady=8)

        # 3. Área de Texto da Nota
        self.text_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.text_card.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        # Barra de formatação rápida responsiva com suporte a overflow '»'
        self.responsive_format_bar = ResponsiveToolbar(
            self.text_card,
            height=34,
            fg_color=config.COLORS["card_dark_alt"],
            corner_radius=8,
            item_spacing=3,
        )
        self.responsive_format_bar.pack(fill="x", padx=12, pady=(8, 0))

        self.btn_undo = self.responsive_format_bar.add_button(
            key="undo",
            symbol_text="↩️",
            full_label="↩️ Desfazer (Ctrl+Z)",
            command=self._on_undo,
            width=36,
            height=26,
        )

        self.btn_redo = self.responsive_format_bar.add_button(
            key="redo",
            symbol_text="↪️",
            full_label="↪️ Refazer (Ctrl+Y)",
            command=self._on_redo,
            width=36,
            height=26,
        )

        self.btn_cut = self.responsive_format_bar.add_button(
            key="cut",
            symbol_text="✂️",
            full_label="✂️ Recortar Seleção (Ctrl+X)",
            command=self._on_cut,
            width=36,
            height=26,
        )

        self.btn_print_fmt = self.responsive_format_bar.add_button(
            key="print_fmt",
            symbol_text="🖨️",
            full_label="🖨️ Imprimir Anotação",
            command=self._on_print,
            width=36,
            height=26,
        )

        self.responsive_format_bar.add_separator(key="sep1", width=10)

        self.combo_font_family = ctk.CTkComboBox(
            self.responsive_format_bar,
            values=AVAILABLE_FONTS,
            width=120,
            height=26,
            corner_radius=6,
            state="readonly",
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark"],
            border_color=config.COLORS["border_dark"],
            border_width=1,
            text_color=config.COLORS["text_dark"],
            button_color=config.COLORS["border_dark"],
            button_hover_color=config.COLORS["primary"],
            dropdown_fg_color=config.COLORS["card_dark"],
            dropdown_text_color=config.COLORS["text_dark"],
            dropdown_hover_color=config.COLORS["primary"],
            command=lambda fam: self.rich_text.apply_font_family(fam) if hasattr(self, "rich_text") else None,
        )
        self.combo_font_family.set(DEFAULT_FONT_FAMILY)
        self.responsive_format_bar.add_widget(
            key="font_family",
            widget=self.combo_font_family,
            width=120,
            tooltip_text="Selecionar Fonte",
        )

        self.combo_font_size = ctk.CTkComboBox(
            self.responsive_format_bar,
            values=AVAILABLE_FONT_SIZES,
            width=60,
            height=26,
            corner_radius=6,
            state="readonly",
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark"],
            border_color=config.COLORS["border_dark"],
            border_width=1,
            text_color=config.COLORS["text_dark"],
            button_color=config.COLORS["border_dark"],
            button_hover_color=config.COLORS["primary"],
            dropdown_fg_color=config.COLORS["card_dark"],
            dropdown_text_color=config.COLORS["text_dark"],
            dropdown_hover_color=config.COLORS["primary"],
            command=lambda sz: self.rich_text.apply_font_size(sz) if hasattr(self, "rich_text") else None,
        )
        self.combo_font_size.set(str(DEFAULT_FONT_SIZE))
        self.responsive_format_bar.add_widget(
            key="font_size",
            widget=self.combo_font_size,
            width=60,
            tooltip_text="Tamanho da Fonte",
        )

        self.btn_bold = self.responsive_format_bar.add_button(
            key="bold",
            symbol_text="B",
            full_label="Negrito (Ctrl+B)",
            command=lambda: self.rich_text.toggle_bold() if hasattr(self, "rich_text") else None,
            width=30,
            height=26,
            font_size=13,
            font_weight="bold",
        )

        self.btn_italic = self.responsive_format_bar.add_button(
            key="italic",
            symbol_text="I",
            full_label="Itálico (Ctrl+I)",
            command=lambda: self.rich_text.toggle_italic() if hasattr(self, "rich_text") else None,
            width=30,
            height=26,
            font_size=13,
            font_weight="bold",
            font_slant="italic",
        )

        self.btn_underline = self.responsive_format_bar.add_button(
            key="underline",
            symbol_text="U",
            full_label="Sublinhado (Ctrl+U)",
            command=lambda: self.rich_text.toggle_underline() if hasattr(self, "rich_text") else None,
            width=30,
            height=26,
            font_size=13,
            font_weight="bold",
            font_underline=True,
        )

        self.btn_overstrike = self.responsive_format_bar.add_button(
            key="overstrike",
            symbol_text="S",
            full_label="Riscado",
            command=lambda: self.rich_text.toggle_overstrike() if hasattr(self, "rich_text") else None,
            width=30,
            height=26,
            font_size=13,
            font_weight="bold",
            font_overstrike=True,
        )

        self.responsive_format_bar.add_separator(key="sep_rich", width=10)

        self.btn_uppercase = self.responsive_format_bar.add_button(
            key="uppercase",
            symbol_text="🔠",
            full_label="🔠 Converter para MAIÚSCULO",
            command=self._on_uppercase,
            width=36,
            height=26,
        )

        self.btn_lowercase = self.responsive_format_bar.add_button(
            key="lowercase",
            symbol_text="🔡",
            full_label="🔡 Converter para minúsculo",
            command=self._on_lowercase,
            width=36,
            height=26,
        )

        self.responsive_format_bar.add_separator(key="sep2", width=10)

        self.btn_xml = self.responsive_format_bar.add_button(
            key="xml",
            symbol_text="</>",
            full_label="</> Formatar e Colorir XML",
            command=self._on_format_xml,
            width=42,
            height=26,
            hover_color="#0284C7",
        )

        self.btn_sql = self.responsive_format_bar.add_button(
            key="sql",
            symbol_text="SQL",
            full_label="🗄️ Formatar e Colorir SQL",
            command=self._on_format_sql,
            width=42,
            height=26,
            hover_color="#BE185D",
        )

        self.txt_content = ctk.CTkTextbox(
            self.text_card,
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
        self.txt_content.pack(fill="both", expand=True, padx=14, pady=(6, 14))
        self.txt_content.bind("<KeyRelease>", self._on_text_modified)
        enable_undo_redo(self.txt_content, on_change_callback=self._on_text_modified)
        configure_syntax_tags(self.txt_content._textbox)

        # Controlador de formatação rica (Fonte, Tamanho, Negrito, Sublinhado e Riscado)
        self.rich_text = RichTextController(
            self.txt_content,
            on_change_callback=self._on_text_modified,
        )
        self.rich_text.attach_toolbar_widgets(
            combo_font=self.combo_font_family,
            combo_size=self.combo_font_size,
            btn_bold=self.btn_bold,
            btn_italic=self.btn_italic,
            btn_underline=self.btn_underline,
            btn_overstrike=self.btn_overstrike,
        )

        # Tag para destacar termos pesquisados
        try:
            self.txt_content._textbox.tag_configure(
                "search_highlight",
                background="#F59E0B",
                foreground="#0F172A",
            )
        except Exception:
            pass

        # 4. Barra de Status Inferior
        self.status_bar = ctk.CTkFrame(
            self,
            height=34,
            corner_radius=8,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.status_bar.pack(fill="x", padx=18, pady=(0, 15))

        self.lbl_status = ctk.CTkLabel(
            self.status_bar,
            text="📖 Modo somente leitura — clique em '✏️ Editar Nota' caso deseje alterar o conteúdo.",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_status.pack(side="left", padx=14, pady=5)

        self.lbl_counts = ctk.CTkLabel(
            self.status_bar,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_counts.pack(side="right", padx=14, pady=5)

        self.btn_next_match = ctk.CTkButton(
            self.status_bar,
            text="",
            width=120,
            height=24,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=config.COLORS["warning"],
            hover_color=config.COLORS["primary"],
            text_color="#0F172A",
            command=self._next_search_match,
        )

        # Vincula F3 / Shift+F3 para navegar entre ocorrências da palavra-chave
        self.bind("<F3>", lambda e: (self._next_search_match(), "break")[1])
        self.bind("<Shift-F3>", lambda e: (self._prev_search_match(), "break")[1])
        self.txt_content._textbox.bind("<F3>", lambda e: (self._next_search_match(), "break")[1])
        self.txt_content._textbox.bind("<Shift-F3>", lambda e: (self._prev_search_match(), "break")[1])

    def _update_meta_and_counts(self, current_text: str):
        words = len(current_text.split()) if current_text.strip() else 0
        chars = len(current_text)
        self.lbl_counts.configure(text=f"{words} palavras | {chars:,} caracteres")

        parts = []
        if self.author_label:
            parts.append(f"👤 {self.author_label}")
        if self.entry and self.entry.updated_at:
            parts.append(f"🕒 Última alteração: {self.entry.updated_at}")
        self.lbl_meta.configure(text="   •   ".join(parts) if parts else "Anotação do diário")

    def _load_content_into_viewer(self):
        self.txt_content.configure(state="normal")
        self.txt_content.delete("1.0", "end")
        self.txt_content.insert("1.0", self.original_content)
        auto_highlight_content(self.txt_content)
        if hasattr(self, "rich_text"):
            self.rich_text.load(self.original_formatting)
        reset_undo_stack(self.txt_content)

        # Destaca termos pesquisados se houver query
        if self.highlight_query:
            self._highlight_search_terms(self.highlight_query)

        # Bloqueia para somente leitura
        self.txt_content.configure(state="disabled")
        self._update_meta_and_counts(self.original_content)
        self._update_format_buttons_state()

    def _update_format_buttons_state(self):
        case_state = "normal" if self.is_editing else "disabled"
        combo_state = "readonly" if self.is_editing else "disabled"
        if hasattr(self, "combo_font_family"):
            self.combo_font_family.configure(state=combo_state)
        if hasattr(self, "combo_font_size"):
            self.combo_font_size.configure(state=combo_state)
        if hasattr(self, "btn_bold"):
            self.btn_bold.configure(state=case_state)
        if hasattr(self, "btn_italic"):
            self.btn_italic.configure(state=case_state)
        if hasattr(self, "btn_underline"):
            self.btn_underline.configure(state=case_state)
        if hasattr(self, "btn_overstrike"):
            self.btn_overstrike.configure(state=case_state)
        if hasattr(self, "btn_uppercase"):
            self.btn_uppercase.configure(state=case_state)
        if hasattr(self, "btn_lowercase"):
            self.btn_lowercase.configure(state=case_state)
        if hasattr(self, "btn_undo"):
            self.btn_undo.configure(state=case_state)
        if hasattr(self, "btn_redo"):
            self.btn_redo.configure(state=case_state)
        if hasattr(self, "btn_cut"):
            self.btn_cut.configure(state=case_state)

    def _on_undo(self):
        if not self.is_editing:
            return
        perform_undo(self.txt_content, on_change_callback=self._on_text_modified)

    def _on_redo(self):
        if not self.is_editing:
            return
        perform_redo(self.txt_content, on_change_callback=self._on_text_modified)

    def _on_cut(self):
        if not self.is_editing:
            return
        try:
            commit_history_before_action(self.txt_content)
            self.txt_content._textbox.event_generate("<<Cut>>")
            record_history_after_action(self.txt_content)
            self._on_text_modified()
        except Exception:
            pass

    def _on_print(self):
        content = self.txt_content.get("1.0", "end-1c")
        if not content.strip():
            show_message(self, "Imprimir", "Não há conteúdo para imprimir.", kind="warning")
            return
        try:
            import tempfile
            import subprocess
            temp_file = os.path.join(tempfile.gettempdir(), f"nota_{self.date_br.replace('/', '_')}.txt")
            header = f"DIÁRIO DE ANOTAÇÕES - {self.date_br}\n" + ("=" * 50) + "\n\n"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(header + content)
            if os.name == "nt":
                os.startfile(temp_file, "open")
            else:
                subprocess.Popen(["xdg-open", temp_file])
        except Exception as e:
            show_message(self, "Imprimir", f"Não foi possível abrir o arquivo para impressão:\n{e}", kind="warning")

    def _on_uppercase(self):
        if not self.is_editing:
            return
        ok, msg = convert_selection_case(self.txt_content, uppercase=True)
        if not ok:
            show_message(self, "Converter para MAIÚSCULO", msg, kind="info")
            return
        self._on_text_modified()

    def _on_lowercase(self):
        if not self.is_editing:
            return
        ok, msg = convert_selection_case(self.txt_content, uppercase=False)
        if not ok:
            show_message(self, "Converter para minúsculo", msg, kind="info")
            return
        self._on_text_modified()

    def _on_format_xml(self):
        was_readonly = not self.is_editing
        if was_readonly:
            self.txt_content.configure(state="normal")
        format_and_highlight_xml(self.txt_content, indent_xml=self.is_editing)
        if was_readonly:
            self.txt_content.configure(state="disabled")
        else:
            self._on_text_modified()

    def _on_format_sql(self):
        was_readonly = not self.is_editing
        if was_readonly:
            self.txt_content.configure(state="normal")
        format_and_highlight_sql(self.txt_content, format_keywords=self.is_editing)
        if was_readonly:
            self.txt_content.configure(state="disabled")
        else:
            self._on_text_modified()

    def _highlight_search_terms(self, query: str):
        try:
            self._search_matches = highlight_search_matches(self.txt_content, query)
            if self._search_matches:
                self._current_match_idx = focus_search_match(
                    self.txt_content, self._search_matches, 0
                )
            else:
                self._current_match_idx = -1
            self._update_match_indicator()
        except Exception:
            pass

    def _update_match_indicator(self):
        if hasattr(self, "btn_next_match"):
            if self._search_matches and self._current_match_idx >= 0:
                total = len(self._search_matches)
                curr = self._current_match_idx + 1
                self.btn_next_match.configure(text=f"🔍 {curr}/{total} (F3 ▸)")
                self.btn_next_match.pack(side="right", padx=(0, 8), pady=5)
            else:
                self.btn_next_match.pack_forget()

    def _next_search_match(self):
        if not self.highlight_query:
            return
        if not self._search_matches or self.is_editing:
            self._search_matches = highlight_search_matches(self.txt_content, self.highlight_query)
            if not self._search_matches:
                self._current_match_idx = -1
                self._update_match_indicator()
                return
        next_idx = 0 if self._current_match_idx < 0 else (self._current_match_idx + 1) % len(self._search_matches)
        self._current_match_idx = focus_search_match(self.txt_content, self._search_matches, next_idx)
        self._update_match_indicator()

    def _prev_search_match(self):
        if not self.highlight_query:
            return
        if not self._search_matches or self.is_editing:
            self._search_matches = highlight_search_matches(self.txt_content, self.highlight_query)
            if not self._search_matches:
                self._current_match_idx = -1
                self._update_match_indicator()
                return
        prev_idx = (len(self._search_matches) - 1) if self._current_match_idx <= 0 else (self._current_match_idx - 1)
        self._current_match_idx = focus_search_match(self.txt_content, self._search_matches, prev_idx)
        self._update_match_indicator()

    def _enable_edit_mode(self):
        """Ativa o modo de edição na própria janela."""
        self.is_editing = True
        self.txt_content.configure(state="normal")
        clear_search_highlights(self.txt_content)
        reset_undo_stack(self.txt_content)

        self.title(f"Editando Anotação - {self.date_br}")
        self.lbl_mode_badge.configure(
            text="✏️ Modo de Edição",
            fg_color=config.COLORS["primary"],
            text_color="#FFFFFF",
        )
        self.lbl_status.configure(
            text="✏️ Edição habilitada — faça suas alterações e clique em '💾 Salvar Alterações'.",
            text_color=config.COLORS["text_dark"],
        )

        # Troca botão Editar por Salvar + Cancelar Edição
        self.btn_edit.pack_forget()
        self.btn_save.pack(side="left", padx=(12, 6), pady=8, before=self.btn_copy)
        self.btn_cancel_edit.pack(side="left", padx=6, pady=8, before=self.btn_copy)

        self._update_format_buttons_state()
        self.txt_content.focus_set()

    def _cancel_edit_mode(self):
        """Retorna ao modo somente leitura descartando edições não salvas após confirmação."""
        if self.has_unsaved_changes:
            confirmed = ask_confirmation(
                self,
                "Descartar Alterações",
                "Deseja descartar as alterações feitas e voltar ao modo somente leitura?",
                kind="warning",
            )
            if not confirmed:
                return

        self.is_editing = False
        self.has_unsaved_changes = False
        self.title(f"Visualização de Anotação - {self.date_br}")
        self.lbl_mode_badge.configure(
            text="🔒 Somente Leitura",
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_status.configure(
            text="📖 Modo somente leitura — clique em '✏️ Editar Nota' caso deseje alterar o conteúdo.",
            text_color=config.COLORS["text_muted"],
        )

        self.btn_save.pack_forget()
        self.btn_cancel_edit.pack_forget()
        self.btn_edit.pack(side="left", padx=(12, 6), pady=8, before=self.btn_copy)

        self._load_content_into_viewer()

    def _on_text_modified(self, event=None):
        if not self.is_editing:
            return
        current_text = self.txt_content.get("1.0", "end-1c")
        current_fmt = self.rich_text.serialize() if hasattr(self, "rich_text") else ""
        self._update_meta_and_counts(current_text)

        if current_text != self.original_content or current_fmt != self.original_formatting:
            self.has_unsaved_changes = True
            self.lbl_status.configure(
                text="⚪ Alterações não salvas *",
                text_color=config.COLORS["warning"],
            )
        else:
            self.has_unsaved_changes = False
            self.lbl_status.configure(
                text="✏️ Modo de edição (sem alterações pendentes)",
                text_color=config.COLORS["text_muted"],
            )

    def save_changes(self) -> bool:
        """Salva o conteúdo editado no banco e retorna ao modo somente leitura atualizado."""
        if not self.is_editing:
            return True

        new_content = self.txt_content.get("1.0", "end-1c")
        fmt_json = self.rich_text.serialize() if hasattr(self, "rich_text") else ""
        try:
            saved_entry = self.diary_service.save_entry(
                self.user_id,
                self.date_iso,
                new_content,
                formatting_json=fmt_json,
            )
            self.entry = saved_entry
            self.original_content = saved_entry.content or ""
            self.original_formatting = getattr(saved_entry, "formatting_json", "") or ""
            self.has_unsaved_changes = False
            self.is_editing = False

            self.title(f"Visualização de Anotação - {self.date_br}")
            self.lbl_mode_badge.configure(
                text="🔒 Somente Leitura",
                fg_color=config.COLORS["card_dark_alt"],
                text_color=config.COLORS["text_dark"],
            )
            self.lbl_status.configure(
                text=f"🟢 Alterações salvas com sucesso às {saved_entry.updated_at.split(' ')[-1]}",
                text_color=config.COLORS["success"],
            )

            self.btn_save.pack_forget()
            self.btn_cancel_edit.pack_forget()
            self.btn_edit.pack(side="left", padx=(12, 6), pady=8, before=self.btn_copy)

            self._load_content_into_viewer()

            if self.on_entry_saved:
                self.on_entry_saved()
            return True
        except Exception as e:
            show_message(self, "Erro ao Salvar", f"Não foi possível salvar a anotação:\n{e}", kind="danger")
            return False

    def _copy_to_clipboard(self):
        text = self.txt_content.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        orig_text = self.btn_copy.cget("text")
        self.btn_copy.configure(text="✅ Copiado!")
        self.after(1200, lambda: self.btn_copy.configure(text=orig_text) if self.winfo_exists() else None)

    def _confirm_can_close(self) -> bool:
        if not (self.is_editing and self.has_unsaved_changes):
            return True
        diag = UnsavedChangesDialog(self, self.date_br)
        if diag.result == "save":
            return self.save_changes()
        elif diag.result == "discard":
            self.has_unsaved_changes = False
            return True
        return False

    def _handle_open_in_diary(self):
        if not self._confirm_can_close():
            return
        cb = self.on_open_in_diary
        d_iso = self.date_iso
        u_id = self.user_id
        self.destroy()
        if cb:
            cb(d_iso, u_id)

    def _on_ctrl_s(self):
        if self.is_editing:
            self.save_changes()
        return "break"

    def _on_escape(self):
        self._on_close()

    def _on_close(self):
        if not self._confirm_can_close():
            return
        self.destroy()
