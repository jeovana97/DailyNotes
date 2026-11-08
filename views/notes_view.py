import os
import re
import tkinter as tk
from tkinter import filedialog
from typing import Optional, Dict, List, Set, Tuple
import customtkinter as ctk

import config
from models.user import User
from models.note import NoteFolder, NoteItem
from services.note_service import NoteService
from services.import_service import ImportService, ConflictResolution
from services.spellcheck_service import WindowsSpellCheckService
from views.components.dialogs import UnsavedChangesDialog, show_message, ask_confirmation
from views.components.responsive_toolbar import ResponsiveToolbar
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


class FolderDialog(ctk.CTkToplevel):
    """
    Modal para criar ou editar (renomear / mover) uma Pasta ou Subpasta.
    """

    def __init__(
        self,
        parent,
        note_service: NoteService,
        user_id: int,
        folder: Optional[NoteFolder] = None,
        default_parent_id: Optional[int] = None,
    ):
        super().__init__(parent)
        self.note_service = note_service
        self.user_id = user_id
        self.folder = folder
        self.result_folder: Optional[NoteFolder] = None

        is_edit = folder is not None
        self.title("Editar Pasta" if is_edit else "Nova Pasta / Subpasta")
        self.geometry("430x290")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() // 2) - 215
        py = parent.winfo_y() + (parent.winfo_height() // 2) - 145
        self.geometry(f"+{max(50, px)}+{max(50, py)}")

        self.container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.container.pack(fill="both", expand=True, padx=15, pady=15)

        header_icon = "✏️" if is_edit else "📁"
        header_text = "Editar Pasta" if is_edit else "Criar Nova Pasta ou Subpasta"
        self.lbl_title = ctk.CTkLabel(
            self.container,
            text=f"{header_icon} {header_text}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(pady=(14, 12))

        # Campo Nome da Pasta
        lbl_name = ctk.CTkLabel(
            self.container,
            text="Nome da Pasta:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        lbl_name.pack(fill="x", padx=20, pady=(0, 4))

        self.entry_name = ctk.CTkEntry(
            self.container,
            height=36,
            placeholder_text="Ex: Banco de Dados, PL/SQL, Senhas...",
            corner_radius=8,
        )
        self.entry_name.pack(fill="x", padx=20, pady=(0, 12))
        if is_edit:
            self.entry_name.insert(0, folder.name)

        # Seletor de Pasta Pai (para permitir criar subpastas)
        lbl_parent = ctk.CTkLabel(
            self.container,
            text="Localização (Pasta Pai):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        lbl_parent.pack(fill="x", padx=20, pady=(0, 4))

        exclude_id = folder.id if is_edit else None
        self.folder_options: List[Tuple[Optional[int], str]] = self.note_service.get_folder_tree_options(
            self.user_id, exclude_folder_id=exclude_id
        )
        option_labels = [label for _, label in self.folder_options]

        self.combo_parent = ctk.CTkComboBox(
            self.container,
            values=option_labels,
            height=34,
            corner_radius=8,
            state="readonly",
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
            button_color=config.COLORS["card_dark_alt"],
            button_hover_color=config.COLORS["primary"],
            dropdown_fg_color=config.COLORS["card_dark"],
            dropdown_text_color=config.COLORS["text_dark"],
            dropdown_hover_color=config.COLORS["primary"],
        )
        self.combo_parent.pack(fill="x", padx=20, pady=(0, 16))

        target_parent_id = folder.parent_id if is_edit else default_parent_id
        selected_label = option_labels[0]
        for fid, label in self.folder_options:
            if fid == target_parent_id:
                selected_label = label
                break
        self.combo_parent.set(selected_label)

        # Botões
        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 12))

        self.btn_save = ctk.CTkButton(
            btn_frame,
            text="💾 Salvar",
            height=36,
            corner_radius=8,
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_save,
        )
        self.btn_save.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_cancel = ctk.CTkButton(
            btn_frame,
            text="Cancelar",
            height=36,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self.destroy,
        )
        self.btn_cancel.pack(side="right", fill="x", expand=True, padx=(6, 0))

        self.entry_name.bind("<Return>", lambda e: self._on_save())
        self.after(50, self.entry_name.focus_set)
        self.wait_window(self)

    def _get_selected_parent_id(self) -> Optional[int]:
        chosen = self.combo_parent.get()
        for fid, label in self.folder_options:
            if label == chosen:
                return fid
        return None

    def _on_save(self):
        name = self.entry_name.get().strip()
        if not name:
            show_message(self, "Aviso", "Informe um nome para a pasta.", kind="warning")
            return

        parent_id = self._get_selected_parent_id()
        try:
            if self.folder is None:
                self.result_folder = self.note_service.create_folder(
                    user_id=self.user_id,
                    name=name,
                    parent_id=parent_id,
                )
            else:
                updated = self.note_service.rename_folder(
                    user_id=self.user_id,
                    folder_id=self.folder.id,
                    new_name=name,
                )
                if updated.parent_id != parent_id:
                    updated = self.note_service.move_folder(
                        user_id=self.user_id,
                        folder_id=self.folder.id,
                        new_parent_id=parent_id,
                    )
                self.result_folder = updated
            self.destroy()
        except Exception as e:
            show_message(self, "Não foi possível salvar a pasta", str(e), kind="danger")


class MoveNoteDialog(ctk.CTkToplevel):
    """
    Modal dedicado para mover uma nota para outra pasta, subpasta ou para a Raiz.
    Permite também criar uma nova pasta na hora durante a movimentação.
    """

    def __init__(
        self,
        parent,
        note_service: NoteService,
        user_id: int,
        note: NoteItem,
    ):
        super().__init__(parent)
        self.note_service = note_service
        self.user_id = user_id
        self.note = note
        self.result_note: Optional[NoteItem] = None

        self.title("Mover Nota de Pasta")
        self.geometry("440x290")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() // 2) - 220
        py = parent.winfo_y() + (parent.winfo_height() // 2) - 145
        self.geometry(f"+{max(50, px)}+{max(50, py)}")

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
            text="📂 Mover Nota de Pasta",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(pady=(14, 6))

        path_map = self.note_service.get_folder_path_map(self.user_id)
        current_folder_label = (
            path_map.get(self.note.folder_id, "Raiz (Sem pasta)")
            if self.note.folder_id is not None
            else "Raiz (Sem pasta)"
        )

        self.lbl_note_info = ctk.CTkLabel(
            self.container,
            text=f"📄 Nota: {self.note.title}\n📍 Pasta atual: {current_folder_label}",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
            justify="left",
            anchor="w",
        )
        self.lbl_note_info.pack(fill="x", padx=20, pady=(0, 12))

        lbl_dest = ctk.CTkLabel(
            self.container,
            text="Selecione a pasta de destino:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        lbl_dest.pack(fill="x", padx=20, pady=(0, 4))

        dest_row = ctk.CTkFrame(self.container, fg_color="transparent")
        dest_row.pack(fill="x", padx=20, pady=(0, 18))

        self.folder_options: List[Tuple[Optional[int], str]] = []
        self.combo_dest = ctk.CTkComboBox(
            dest_row,
            values=["📁 Sem pasta (Raiz)"],
            height=34,
            corner_radius=8,
            state="readonly",
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
            button_color=config.COLORS["card_dark_alt"],
            button_hover_color=config.COLORS["primary"],
            dropdown_fg_color=config.COLORS["card_dark"],
            dropdown_text_color=config.COLORS["text_dark"],
            dropdown_hover_color=config.COLORS["primary"],
        )
        self.combo_dest.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_create_folder = ctk.CTkButton(
            dest_row,
            text="📁+ Nova",
            width=80,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._on_quick_new_folder,
        )
        self.btn_create_folder.pack(side="right")

        self._reload_options(selected_id=self.note.folder_id)

        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 12))

        self.btn_move = ctk.CTkButton(
            btn_frame,
            text="📂 Mover Nota",
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_confirm_move,
        )
        self.btn_move.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_cancel = ctk.CTkButton(
            btn_frame,
            text="Cancelar",
            height=36,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self.destroy,
        )
        self.btn_cancel.pack(side="right", fill="x", expand=True, padx=(6, 0))

        self.wait_window(self)

    def _reload_options(self, selected_id: Optional[int] = None):
        self.folder_options = self.note_service.get_folder_tree_options(self.user_id)
        labels = [lbl for _, lbl in self.folder_options]
        self.combo_dest.configure(values=labels)

        chosen = labels[0] if labels else "📁 Sem pasta (Raiz)"
        for fid, lbl in self.folder_options:
            if fid == selected_id:
                chosen = lbl
                break
        self.combo_dest.set(chosen)

    def _get_selected_folder_id(self) -> Optional[int]:
        chosen = self.combo_dest.get()
        for fid, lbl in self.folder_options:
            if lbl == chosen:
                return fid
        return None

    def _on_quick_new_folder(self):
        current_sel = self._get_selected_folder_id()
        diag = FolderDialog(
            self,
            note_service=self.note_service,
            user_id=self.user_id,
            folder=None,
            default_parent_id=current_sel,
        )
        if diag.result_folder:
            self._reload_options(selected_id=diag.result_folder.id)

    def _on_confirm_move(self):
        target_folder_id = self._get_selected_folder_id()
        try:
            self.result_note = self.note_service.move_note(
                user_id=self.user_id,
                note_id=self.note.id,
                target_folder_id=target_folder_id,
            )
            self.destroy()
        except Exception as e:
            show_message(self, "Erro ao Mover Nota", str(e), kind="danger")


class SelectImportFolderDialog(ctk.CTkToplevel):
    """
    Modal que pergunta ao usuário em qual pasta deseja colocar a(s) nota(s) importada(s)
    ou se deseja criar uma nova pasta na hora.
    Não exige formato de data nos nomes dos arquivos.
    """

    def __init__(
        self,
        parent,
        note_service: NoteService,
        user_id: int,
        files_description: str = "",
        default_folder_id: Optional[int] = None,
    ):
        super().__init__(parent)
        self.note_service = note_service
        self.user_id = user_id
        self.confirmed: bool = False
        self.selected_folder_id: Optional[int] = default_folder_id

        self.title("Escolher Pasta para Importar Nota(s)")
        self.geometry("490x385")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() // 2) - 245
        py = parent.winfo_y() + (parent.winfo_height() // 2) - 192
        self.geometry(f"+{max(50, px)}+{max(50, py)}")

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
            text="📥 Em qual pasta deseja colocar a(s) nota(s)?",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(pady=(14, 4))

        desc_text = files_description or "Qualquer arquivo TXT pode ser importado sem necessidade de formato de data."
        self.lbl_desc = ctk.CTkLabel(
            self.container,
            text=desc_text,
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
            wraplength=430,
            justify="center",
        )
        self.lbl_desc.pack(padx=20, pady=(0, 12))

        # 1. Seleção de Pasta Existente
        lbl_dest = ctk.CTkLabel(
            self.container,
            text="1. Escolha uma pasta existente (ou deixe na Raiz):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        lbl_dest.pack(fill="x", padx=20, pady=(0, 4))

        dest_row = ctk.CTkFrame(self.container, fg_color="transparent")
        dest_row.pack(fill="x", padx=20, pady=(0, 14))

        self.folder_options: List[Tuple[Optional[int], str]] = []
        self.combo_dest = ctk.CTkComboBox(
            dest_row,
            values=["📁 Sem pasta (Raiz)"],
            height=34,
            corner_radius=8,
            state="readonly",
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
            button_color=config.COLORS["card_dark_alt"],
            button_hover_color=config.COLORS["primary"],
            dropdown_fg_color=config.COLORS["card_dark"],
            dropdown_text_color=config.COLORS["text_dark"],
            dropdown_hover_color=config.COLORS["primary"],
        )
        self.combo_dest.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_modal_new_folder = ctk.CTkButton(
            dest_row,
            text="📁+ Criar Pasta...",
            width=120,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._on_open_folder_dialog,
        )
        self.btn_modal_new_folder.pack(side="right")

        self._reload_options(selected_id=default_folder_id)

        # 2. Ou digitar diretamente o nome de uma nova pasta para criar na hora
        new_folder_box = ctk.CTkFrame(
            self.container,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        new_folder_box.pack(fill="x", padx=20, pady=(0, 16))

        lbl_quick_new = ctk.CTkLabel(
            new_folder_box,
            text="➕ Ou precisa criar uma nova pasta agora? Digite o nome abaixo (opcional):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        lbl_quick_new.pack(fill="x", padx=12, pady=(8, 4))

        self.entry_new_folder = ctk.CTkEntry(
            new_folder_box,
            height=32,
            placeholder_text="Digite o nome da nova pasta se quiser criá-la automaticamente...",
            corner_radius=6,
            font=ctk.CTkFont(size=12),
        )
        self.entry_new_folder.pack(fill="x", padx=12, pady=(0, 6))

        lbl_quick_hint = ctk.CTkLabel(
            new_folder_box,
            text="💡 Se preencher este campo, a nova pasta será criada dentro da localização selecionada acima.",
            font=ctk.CTkFont(size=10),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        lbl_quick_hint.pack(fill="x", padx=12, pady=(0, 8))

        # 3. Botões de Ação
        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 12))

        self.btn_confirm = ctk.CTkButton(
            btn_frame,
            text="📥 Importar Nota(s) Aqui",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_confirm,
        )
        self.btn_confirm.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_cancel = ctk.CTkButton(
            btn_frame,
            text="Cancelar",
            height=38,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self.destroy,
        )
        self.btn_cancel.pack(side="right", fill="x", expand=True, padx=(6, 0))

        self.entry_new_folder.bind("<Return>", lambda e: self._on_confirm())
        self.wait_window(self)

    def _reload_options(self, selected_id: Optional[int] = None):
        self.folder_options = self.note_service.get_folder_tree_options(self.user_id)
        labels = [lbl for _, lbl in self.folder_options]
        self.combo_dest.configure(values=labels)

        chosen = labels[0] if labels else "📁 Sem pasta (Raiz)"
        for fid, lbl in self.folder_options:
            if fid == selected_id:
                chosen = lbl
                break
        self.combo_dest.set(chosen)

    def _get_selected_folder_id(self) -> Optional[int]:
        chosen = self.combo_dest.get()
        for fid, lbl in self.folder_options:
            if lbl == chosen:
                return fid
        return None

    def _on_open_folder_dialog(self):
        current_sel = self._get_selected_folder_id()
        diag = FolderDialog(
            self,
            note_service=self.note_service,
            user_id=self.user_id,
            folder=None,
            default_parent_id=current_sel,
        )
        if diag.result_folder:
            self.entry_new_folder.delete(0, "end")
            self._reload_options(selected_id=diag.result_folder.id)

    def _on_confirm(self):
        parent_id = self._get_selected_folder_id()
        new_folder_name = self.entry_new_folder.get().strip()

        if new_folder_name:
            try:
                created_folder = self.note_service.create_folder(
                    user_id=self.user_id,
                    name=new_folder_name,
                    parent_id=parent_id,
                )
                self.selected_folder_id = created_folder.id
            except Exception as e:
                show_message(self, "Não foi possível criar a pasta", str(e), kind="danger")
                return
        else:
            self.selected_folder_id = parent_id

        self.confirmed = True
        self.destroy()


class NotesView(ctk.CTkFrame):
    """
    Tela de Notas Salvas e Organização por Pastas e Subpastas.
    - Independente de datas do diário
    - Não entra na Pesquisa Avançada do diário
    - Possui pesquisa própria instantânea pelo nome da nota salva
    - Permite organizar notas em pastas e subpastas em múltiplos níveis
    - Conta com editor completo, salvamento automático opcional e corretor ortográfico pt-BR
    """

    MAX_SIDEBAR_TITLE_CHARS = 28

    def __init__(
        self,
        master,
        current_user: User,
        note_service: NoteService,
        spell_service: Optional[WindowsSpellCheckService] = None,
        import_service: Optional[ImportService] = None,
        initial_folder_id: Optional[int] = None,
        initial_note_id: Optional[int] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.note_service = note_service
        self.spell_service = spell_service or WindowsSpellCheckService()
        self.import_service = import_service or ImportService(
            note_service=self.note_service,
            db_path=self.note_service.db_path,
        )

        # Estado da nota e pasta selecionadas
        self.active_note: Optional[NoteItem] = None
        self.selected_folder_id: Optional[int] = initial_folder_id
        self.expanded_folders: Set[int] = set()
        self._initial_expansion_done = False

        # Mapeamento do combo de pastas no editor
        self.editor_folder_options: List[Tuple[Optional[int], str]] = []

        # Controle de alterações não salvas e autosave
        self.has_unsaved_changes = False
        self.autosave_timer_id = None
        self.autosave_enabled = tk.BooleanVar(value=True)
        self._suppress_change_events = False

        # Controle do corretor ortográfico nativo do Windows
        self.spellcheck_timer_id = None
        self.spellcheck_enabled = tk.BooleanVar(value=self.spell_service.is_available)

        self._build_ui()
        self._refresh_folder_combo(selected_folder_id=initial_folder_id)
        self._refresh_tree()

        if initial_note_id is not None:
            self.load_note(initial_note_id)
        else:
            self._prepare_blank_note(folder_id=initial_folder_id)

        # Vincula atalho Ctrl+S
        self.txt_content.bind("<Control-s>", lambda e: (self.save_current_note(), "break")[1])
        self.txt_content.bind("<Control-S>", lambda e: (self.save_current_note(), "break")[1])
        self.entry_title.bind("<Control-s>", lambda e: (self.save_current_note(), "break")[1])
        self.entry_title.bind("<Control-S>", lambda e: (self.save_current_note(), "break")[1])
        try:
            top = self.winfo_toplevel()
            top.bind("<Control-s>", lambda e: (self._on_ctrl_s_global(), "break")[1])
            top.bind("<Control-S>", lambda e: (self._on_ctrl_s_global(), "break")[1])
        except Exception:
            pass

    def _on_ctrl_s_global(self):
        try:
            if self.winfo_exists():
                self.save_current_note()
        except Exception:
            pass

    def _build_ui(self):
        # Layout de 2 colunas: Painel lateral de Pastas/Notas (col 0) | Editor de Nota (col 1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # =====================================================================
        # 1. Painel Esquerdo: Pesquisa por Nome + Árvore de Pastas e Notas
        # =====================================================================
        self.left_panel = ctk.CTkFrame(
            self,
            width=310,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=15)
        self.left_panel.grid_propagate(False)

        # Título do Painel Lateral
        header_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        header_frame.pack(fill="x", padx=12, pady=(12, 8))

        lbl_explorer = ctk.CTkLabel(
            header_frame,
            text="🗂️ Notas & Pastas",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_explorer.pack(side="left")

        self.lbl_total_notes = ctk.CTkLabel(
            header_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_total_notes.pack(side="right")

        # Barra de Pesquisa no próprio menu (pelo nome da nota)
        search_container = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        search_container.pack(fill="x", padx=12, pady=(0, 8))

        self.entry_search = ctk.CTkEntry(
            search_container,
            height=34,
            placeholder_text="🔍 Pesquisar pelo nome da nota...",
            corner_radius=8,
            font=ctk.CTkFont(size=12),
        )
        self.entry_search.pack(side="left", fill="x", expand=True)
        self.entry_search.bind("<KeyRelease>", self._on_search_changed)

        self.btn_clear_search = ctk.CTkButton(
            search_container,
            text="✕",
            width=30,
            height=34,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["danger"],
            text_color=config.COLORS["button_text"],
            command=self._clear_search,
        )
        # Só exibe o botão limpar quando houver texto

        # Botões rápidos para Criar Nota / Criar Pasta ou Subpasta
        tree_actions = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        tree_actions.pack(fill="x", padx=12, pady=(0, 8))

        self.btn_tree_new_note = ctk.CTkButton(
            tree_actions,
            text="📄 + Nota",
            height=30,
            corner_radius=7,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_new_note_clicked,
        )
        self.btn_tree_new_note.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_tree_new_folder = ctk.CTkButton(
            tree_actions,
            text="📁 + Pasta",
            height=30,
            corner_radius=7,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._on_new_folder_clicked,
        )
        self.btn_tree_new_folder.pack(side="left", fill="x", expand=True, padx=4)

        self.btn_tree_root = ctk.CTkButton(
            tree_actions,
            text="🏠 Raiz",
            width=60,
            height=30,
            corner_radius=7,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._select_root_folder,
        )
        self.btn_tree_root.pack(side="right", padx=(4, 0))

        # Indicador de pasta ativa no painel esquerdo
        self.lbl_selected_context = ctk.CTkLabel(
            self.left_panel,
            text="📍 Local ativo: Raiz (Sem pasta)",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        self.lbl_selected_context.pack(fill="x", padx=14, pady=(0, 4))

        # Lista / Árvore Rolável de Pastas, Subpastas e Notas (estilo escuro como no exemplo)
        self.tree_scroll = ctk.CTkScrollableFrame(
            self.left_panel,
            corner_radius=8,
            fg_color=config.COLORS["sidebar"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.tree_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # =====================================================================
        # 2. Painel Direito: Editor de Nota Completo
        # =====================================================================
        self.right_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=15)

        # 2.1 Barra Superior: Nome da Nota e Seletor de Pasta
        self.top_bar = ctk.CTkFrame(
            self.right_panel,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.top_bar.pack(fill="x", pady=(0, 10))

        title_row = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        title_row.pack(fill="x", padx=15, pady=12)

        lbl_note_icon = ctk.CTkLabel(
            title_row,
            text="📄 Nome da Nota:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_note_icon.pack(side="left", padx=(0, 8))

        self.entry_title = ctk.CTkEntry(
            title_row,
            height=36,
            placeholder_text="Ex: SENHAS CIS, leiaute plsql, ERRO NO XML DA NOTA...",
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8,
        )
        self.entry_title.pack(side="left", fill="x", expand=True, padx=(0, 14))
        self.entry_title.bind("<KeyRelease>", self._on_field_modified)

        lbl_folder_sel = ctk.CTkLabel(
            title_row,
            text="📁 Pasta:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_muted"],
        )
        lbl_folder_sel.pack(side="left", padx=(0, 6))

        self.combo_folder = ctk.CTkComboBox(
            title_row,
            values=["📁 Sem pasta (Raiz)"],
            width=220,
            height=36,
            corner_radius=8,
            state="readonly",
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
            button_color=config.COLORS["card_dark_alt"],
            button_hover_color=config.COLORS["primary"],
            dropdown_fg_color=config.COLORS["card_dark"],
            dropdown_text_color=config.COLORS["text_dark"],
            dropdown_hover_color=config.COLORS["primary"],
            command=self._on_folder_combo_changed,
        )
        self.combo_folder.pack(side="left")

        # 2.2 Barra de Ações do Editor com Suporte a Overflow '»'
        self.action_toolbar = ctk.CTkFrame(
            self.right_panel,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.action_toolbar.pack(fill="x", pady=(0, 10))

        # Switch de Autosave fixado à direita
        self.switch_autosave = ctk.CTkSwitch(
            self.action_toolbar,
            text="Auto-salvar",
            variable=self.autosave_enabled,
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_dark"],
            progress_color=config.COLORS["primary"],
        )
        self.switch_autosave.pack(side="right", padx=12, pady=8)

        # Barra responsiva de botões de ação (esquerda)
        self.responsive_action_bar = ResponsiveToolbar(
            self.action_toolbar,
            height=36,
            item_spacing=4,
        )
        self.responsive_action_bar.pack(side="left", fill="x", expand=True, padx=(8, 6), pady=6)

        self.btn_save = self.responsive_action_bar.add_button(
            key="save",
            symbol_text="💾 Salvar",
            full_label="💾 Salvar Nota (Ctrl+S)",
            command=self.save_current_note,
            width=88,
            height=32,
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
        )

        self.btn_new_note = self.responsive_action_bar.add_button(
            key="new_note",
            symbol_text="➕ Nota",
            full_label="➕ Nova Nota em Branco",
            command=self._on_new_note_clicked,
            width=78,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_new_subfolder = self.responsive_action_bar.add_button(
            key="new_folder",
            symbol_text="📁 Pasta",
            full_label="📁 Nova Pasta / Subpasta",
            command=self._on_new_folder_clicked,
            width=78,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_import_txt = self.responsive_action_bar.add_button(
            key="import",
            symbol_text="📥 Importar",
            full_label="📥 Importar Notas de Arquivo TXT",
            command=self._on_import_notes_clicked,
            width=88,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_move_note = self.responsive_action_bar.add_button(
            key="move",
            symbol_text="📂 Mover",
            full_label="📂 Mover Nota de Pasta",
            command=self._on_move_current_note_clicked,
            width=78,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_export = self.responsive_action_bar.add_button(
            key="export",
            symbol_text="📤 Exportar",
            full_label="📤 Exportar Nota para TXT",
            command=self._on_export_note_clicked,
            width=84,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_print = self.responsive_action_bar.add_button(
            key="print",
            symbol_text="🖨️ Imprimir",
            full_label="🖨️ Imprimir Nota",
            command=self._on_print_clicked,
            width=84,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
        )

        self.btn_delete = self.responsive_action_bar.add_button(
            key="delete",
            symbol_text="🗑️ Excluir",
            full_label="🗑️ Excluir Nota",
            command=self._on_delete_current_note,
            width=80,
            height=32,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["danger"],
            text_color=config.COLORS["button_text"],
        )

        # 2.3 Área de Edição de Texto
        self.editor_container = ctk.CTkFrame(
            self.right_panel,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.editor_container.pack(fill="both", expand=True, pady=(0, 10))

        # 2.3.1 Barra de Formatação de Texto Responsiva (Desfazer, Refazer, Recortar, Imprimir, MAIÚSCULO, minúsculo, XML, SQL)
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
            full_label="🖨️ Imprimir Nota",
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
        self.txt_content.bind("<KeyRelease>", self._on_field_modified)
        self.txt_content._textbox.bind("<<Paste>>", self._on_paste)
        enable_undo_redo(self.txt_content, on_change_callback=self._on_field_modified)

        # Configura sublinhado de erros ortográficos, cores de sintaxe e menu de contexto do botão direito
        self._configure_spellcheck_tags()
        configure_syntax_tags(self.txt_content._textbox)
        self.txt_content._textbox.bind("<Button-3>", self._on_textbox_context_menu)
        self.txt_content._textbox.bind("<Button-2>", self._on_textbox_context_menu)

        # 2.4 Barra de Status Inferior
        self.status_bar = ctk.CTkFrame(
            self.right_panel,
            height=36,
            corner_radius=8,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.status_bar.pack(fill="x")

        self.lbl_save_status = ctk.CTkLabel(
            self.status_bar,
            text="🟢 Nova nota pronta",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["success"],
        )
        self.lbl_save_status.pack(side="left", padx=15, pady=6)

        lang_label = self.spell_service.active_language or "pt-BR"
        initial_spell_text = (
            f"🔤 Ortografia: {lang_label}" if self.spell_service.is_available else "🔤 Ortografia: Indisponível"
        )
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

    # =========================================================================
    # Utilitários de Formatação e Árvore Lateral
    # =========================================================================

    @classmethod
    def _truncate_label(cls, text: str, max_chars: int = MAX_SIDEBAR_TITLE_CHARS) -> str:
        """
        Trunca nomes longos com '...' para manter o visual limpo na lista lateral
        (ex: 'erro VALOR DA NF DEFERE DO REC...').
        """
        clean = (text or "").strip()
        if len(clean) <= max_chars:
            return clean
        return clean[: max_chars - 3].rstrip() + "..."

    def _update_selected_context_label(self):
        if self.selected_folder_id is None:
            self.lbl_selected_context.configure(text="📍 Local ativo: Raiz (Sem pasta)")
        else:
            path_map = self.note_service.get_folder_path_map(self.current_user.id)
            folder_path = path_map.get(self.selected_folder_id, "Raiz (Sem pasta)")
            self.lbl_selected_context.configure(
                text=f"📍 Pasta: {self._truncate_label(folder_path, 32)}"
            )

    def _refresh_folder_combo(self, selected_folder_id: Optional[int] = None):
        """Atualiza o combobox de seleção de pasta no topo do editor."""
        self.editor_folder_options = self.note_service.get_folder_tree_options(self.current_user.id)
        labels = [lbl for _, lbl in self.editor_folder_options]
        self.combo_folder.configure(values=labels)

        target_id = selected_folder_id
        chosen_label = labels[0] if labels else "📁 Sem pasta (Raiz)"
        for fid, lbl in self.editor_folder_options:
            if fid == target_id:
                chosen_label = lbl
                break
        self.combo_folder.set(chosen_label)

    def _get_editor_selected_folder_id(self) -> Optional[int]:
        current_label = self.combo_folder.get()
        for fid, lbl in self.editor_folder_options:
            if lbl == current_label:
                return fid
        return None

    def _refresh_tree(self):
        """
        Renderiza a lista lateral:
        - Se houver texto no campo de busca, pesquisa exclusivamente pelo nome da nota salva
          e exibe as notas correspondentes (estilo '📄 NOME DA NOTA').
        - Se a busca estiver vazia, renderiza a árvore hierárquica de pastas, subpastas e notas.
        """
        for widget in self.tree_scroll.winfo_children():
            widget.destroy()

        query = self.entry_search.get().strip()
        all_notes = self.note_service.list_notes(self.current_user.id, all_notes=True)
        self.lbl_total_notes.configure(
            text=f"{len(all_notes)} {'nota' if len(all_notes) == 1 else 'notas'}"
        )

        if query:
            if not self.btn_clear_search.winfo_ismapped():
                self.btn_clear_search.pack(side="right", padx=(4, 0))
            self._render_search_results(query)
        else:
            if self.btn_clear_search.winfo_ismapped():
                self.btn_clear_search.pack_forget()
            self._render_hierarchy_tree(all_notes)

        self._update_selected_context_label()

    def _render_search_results(self, query: str):
        """Exibe os resultados filtrados pelo nome da nota salva."""
        matching_notes = self.note_service.search_notes_by_title(self.current_user.id, query)
        path_map = self.note_service.get_folder_path_map(self.current_user.id)

        lbl_info = ctk.CTkLabel(
            self.tree_scroll,
            text=f"🔍 {len(matching_notes)} resultado(s) para '{self._truncate_label(query, 18)}'",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        lbl_info.pack(fill="x", padx=6, pady=(4, 6))

        if not matching_notes:
            lbl_empty = ctk.CTkLabel(
                self.tree_scroll,
                text="Nenhuma nota encontrada\ncom esse nome.",
                font=ctk.CTkFont(size=12),
                text_color=config.COLORS["text_muted"],
                justify="center",
            )
            lbl_empty.pack(fill="x", padx=10, pady=25)
            return

        for note in matching_notes:
            folder_path = path_map.get(note.folder_id, "") if note.folder_id else ""
            self._create_note_row_widget(
                parent=self.tree_scroll,
                note=note,
                depth=0,
                subtitle_path=folder_path,
            )

    def _render_hierarchy_tree(self, all_notes: List[NoteItem]):
        """Exibe a árvore hierárquica de pastas, subpastas e notas."""
        folders = self.note_service.list_folders(self.current_user.id)

        # Na primeira carga, expande as pastas para facilitar visualização
        if not self._initial_expansion_done and folders:
            self.expanded_folders = {f.id for f in folders if f.id is not None}
            self._initial_expansion_done = True

        children_folders: Dict[Optional[int], List[NoteFolder]] = {}
        for f in folders:
            children_folders.setdefault(f.parent_id, []).append(f)

        notes_by_folder: Dict[Optional[int], List[NoteItem]] = {}
        for n in all_notes:
            notes_by_folder.setdefault(n.folder_id, []).append(n)

        if not folders and not all_notes:
            lbl_empty = ctk.CTkLabel(
                self.tree_scroll,
                text="Nenhuma nota ou pasta criada.\n\nClique em '📄 + Nota' ou '📁 + Pasta'\npara começar a organizar!",
                font=ctk.CTkFont(size=12),
                text_color=config.COLORS["text_muted"],
                justify="center",
            )
            lbl_empty.pack(fill="x", padx=10, pady=30)
            return

        def _render_level(parent_id: Optional[int], depth: int):
            # 1. Renderiza pastas deste nível
            for folder in children_folders.get(parent_id, []):
                is_expanded = folder.id in self.expanded_folders
                self._create_folder_row_widget(
                    parent=self.tree_scroll,
                    folder=folder,
                    depth=depth,
                    is_expanded=is_expanded,
                )
                if is_expanded:
                    _render_level(folder.id, depth + 1)

            # 2. Renderiza notas pertencentes a este nível/pasta
            for note in notes_by_folder.get(parent_id, []):
                self._create_note_row_widget(
                    parent=self.tree_scroll,
                    note=note,
                    depth=depth,
                )

        _render_level(None, 0)

    def _create_folder_row_widget(
        self,
        parent,
        folder: NoteFolder,
        depth: int,
        is_expanded: bool,
    ):
        is_selected_folder = (self.selected_folder_id == folder.id)
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=(depth * 14, 0), pady=1)

        arrow = "▾" if is_expanded else "▸"
        icon = "📂" if is_expanded else "📁"
        max_len = max(14, self.MAX_SIDEBAR_TITLE_CHARS - (depth * 2) - 4)
        display_name = self._truncate_label(folder.name, max_len)

        btn_folder = ctk.CTkButton(
            row_frame,
            text=f"{arrow} {icon}  {display_name}",
            height=32,
            corner_radius=6,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"] if is_selected_folder else "transparent",
            hover_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
            command=lambda fid=folder.id: self._on_folder_row_clicked(fid),
        )
        btn_folder.pack(side="left", fill="x", expand=True)

        # Botão compacto de menu de ações da pasta
        btn_menu = ctk.CTkButton(
            row_frame,
            text="⋯",
            width=26,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent",
            hover_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_muted"],
            command=lambda f=folder, w=btn_folder: self._show_folder_context_menu_at_widget(f, w),
        )
        btn_menu.pack(side="right", padx=(2, 0))

        btn_folder.bind("<Button-3>", lambda e, f=folder: self._show_folder_context_menu(e, f))
        btn_folder.bind("<Button-2>", lambda e, f=folder: self._show_folder_context_menu(e, f))

    def _create_note_row_widget(
        self,
        parent,
        note: NoteItem,
        depth: int,
        subtitle_path: str = "",
    ):
        is_active = (self.active_note is not None and self.active_note.id == note.id)
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=(depth * 14, 0), pady=1)

        max_len = max(16, self.MAX_SIDEBAR_TITLE_CHARS - (depth * 2))
        truncated_title = self._truncate_label(note.title, max_len)

        if subtitle_path:
            short_path = self._truncate_label(subtitle_path, 22)
            label_text = f"📄  {truncated_title}\n      📁 {short_path}"
            btn_height = 44
        else:
            label_text = f"📄  {truncated_title}"
            btn_height = 32

        btn_note = ctk.CTkButton(
            row_frame,
            text=label_text,
            height=btn_height,
            corner_radius=6,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold" if is_active else "normal"),
            fg_color=config.COLORS["primary"] if is_active else "transparent",
            hover_color=config.COLORS["primary_hover"] if is_active else config.COLORS["card_dark_alt"],
            text_color="#FFFFFF" if is_active else config.COLORS["text_dark"],
            command=lambda n=note: self._on_note_row_clicked(n),
        )
        btn_note.pack(side="left", fill="x", expand=True)

        # Botão compacto de menu de ações da nota (incluindo Mover de Pasta)
        btn_note_menu = ctk.CTkButton(
            row_frame,
            text="⋯",
            width=26,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent",
            hover_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_muted"],
            command=lambda n=note, w=btn_note: self._show_note_context_menu_at_widget(n, w),
        )
        btn_note_menu.pack(side="right", padx=(2, 0))

        btn_note.bind("<Button-3>", lambda e, n=note: self._show_note_context_menu(e, n))
        btn_note.bind("<Button-2>", lambda e, n=note: self._show_note_context_menu(e, n))

    # =========================================================================
    # Interações de Pastas, Subpastas e Pesquisa
    # =========================================================================

    def _on_search_changed(self, event=None):
        self._refresh_tree()

    def _clear_search(self):
        self.entry_search.delete(0, "end")
        self._refresh_tree()

    def _select_root_folder(self):
        self.selected_folder_id = None
        if self.active_note is None:
            self._refresh_folder_combo(None)
        self._refresh_tree()

    def _on_folder_row_clicked(self, folder_id: int):
        self.selected_folder_id = folder_id
        if folder_id in self.expanded_folders:
            self.expanded_folders.remove(folder_id)
        else:
            self.expanded_folders.add(folder_id)

        # Se estiver criando uma nota nova ainda não salva, já sugere a pasta clicada
        if self.active_note is None:
            self._refresh_folder_combo(folder_id)

        self._refresh_tree()

    def _on_new_folder_clicked(self, parent_folder_id: Optional[int] = None):
        default_parent = parent_folder_id if parent_folder_id is not None else self.selected_folder_id
        diag = FolderDialog(
            self,
            note_service=self.note_service,
            user_id=self.current_user.id,
            folder=None,
            default_parent_id=default_parent,
        )
        if diag.result_folder:
            new_f = diag.result_folder
            self.expanded_folders.add(new_f.id)
            if new_f.parent_id is not None:
                self.expanded_folders.add(new_f.parent_id)
            self.selected_folder_id = new_f.id

            current_editor_folder = (
                self.active_note.folder_id if self.active_note else new_f.id
            )
            self._refresh_folder_combo(current_editor_folder)
            self._refresh_tree()

    def _on_edit_folder(self, folder: NoteFolder):
        diag = FolderDialog(
            self,
            note_service=self.note_service,
            user_id=self.current_user.id,
            folder=folder,
        )
        if diag.result_folder:
            updated = diag.result_folder
            if updated.parent_id is not None:
                self.expanded_folders.add(updated.parent_id)
            current_editor_folder = self._get_editor_selected_folder_id()
            self._refresh_folder_combo(current_editor_folder)
            self._refresh_tree()

    def _on_delete_folder(self, folder: NoteFolder):
        confirmed = ask_confirmation(
            self,
            "Excluir Pasta",
            f"Deseja realmente excluir a pasta '{folder.name}'?\n\n"
            "Atenção: Todas as subpastas e notas contidas dentro dela também serão excluídas.",
            kind="danger",
        )
        if not confirmed:
            return

        descendants = self.note_service.get_descendant_folder_ids(self.current_user.id, folder.id)
        affected_folder_ids = {folder.id} | descendants

        self.note_service.delete_folder(self.current_user.id, folder.id)

        if self.selected_folder_id in affected_folder_ids:
            self.selected_folder_id = None

        if self.active_note and self.active_note.folder_id in affected_folder_ids:
            self.has_unsaved_changes = False
            self._prepare_blank_note(folder_id=None)

        self._refresh_folder_combo(self._get_editor_selected_folder_id())
        self._refresh_tree()

    def _show_folder_context_menu_at_widget(self, folder: NoteFolder, widget):
        x = widget.winfo_rootx() + 40
        y = widget.winfo_rooty() + widget.winfo_height()
        self._popup_folder_menu(folder, x, y)

    def _show_folder_context_menu(self, event, folder: NoteFolder):
        self._popup_folder_menu(folder, event.x_root, event.y_root)

    def _popup_folder_menu(self, folder: NoteFolder, x_root: int, y_root: int):
        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")
        menu_bg = config.COLORS["card_dark"][1 if is_dark else 0]
        menu_fg = config.COLORS["text_dark"][1 if is_dark else 0]
        active_bg = config.COLORS["primary"][1 if is_dark else 0]

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=menu_bg,
            fg=menu_fg,
            activebackground=active_bg,
            activeforeground="#FFFFFF",
            font=("Segoe UI", 10),
            relief="flat",
            bd=1,
        )
        menu.add_command(
            label=f"📄 Nova Nota em '{folder.name}'",
            command=lambda: self._create_note_in_folder(folder.id),
        )
        menu.add_command(
            label=f"📁 Nova Subpasta em '{folder.name}'",
            command=lambda: self._on_new_folder_clicked(parent_folder_id=folder.id),
        )
        menu.add_separator()
        menu.add_command(
            label="✏️ Renomear / Mover Pasta",
            command=lambda: self._on_edit_folder(folder),
        )
        menu.add_command(
            label="🗑️ Excluir Pasta",
            command=lambda: self._on_delete_folder(folder),
        )
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    def _show_note_context_menu_at_widget(self, note: NoteItem, widget):
        x = widget.winfo_rootx() + 40
        y = widget.winfo_rooty() + widget.winfo_height()
        self._popup_note_menu(note, x, y)

    def _show_note_context_menu(self, event, note: NoteItem):
        self._popup_note_menu(note, event.x_root, event.y_root)

    def _popup_note_menu(self, note: NoteItem, x_root: int, y_root: int):
        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")
        menu_bg = config.COLORS["card_dark"][1 if is_dark else 0]
        menu_fg = config.COLORS["text_dark"][1 if is_dark else 0]
        active_bg = config.COLORS["primary"][1 if is_dark else 0]

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=menu_bg,
            fg=menu_fg,
            activebackground=active_bg,
            activeforeground="#FFFFFF",
            font=("Segoe UI", 10),
            relief="flat",
            bd=1,
        )
        menu.add_command(
            label=f"📄 Abrir '{self._truncate_label(note.title, 25)}'",
            command=lambda: self._on_note_row_clicked(note),
        )
        menu.add_separator()

        # Opção principal que abre o modal de mover nota
        menu.add_command(
            label="📂 Mover de Pasta...",
            font=("Segoe UI", 10, "bold"),
            command=lambda: self._open_move_note_dialog(note),
        )

        # Submenu rápido com todas as pastas para mover com 1 clique
        move_submenu = tk.Menu(
            menu,
            tearoff=0,
            bg=menu_bg,
            fg=menu_fg,
            activebackground=active_bg,
            activeforeground="#FFFFFF",
            font=("Segoe UI", 10),
            relief="flat",
            bd=1,
        )
        folder_options = self.note_service.get_folder_tree_options(self.current_user.id)
        for fid, flabel in folder_options:
            is_current = (fid == note.folder_id)
            prefix = "✔ " if is_current else "    "
            move_submenu.add_command(
                label=f"{prefix}{flabel}",
                state="disabled" if is_current else "normal",
                command=lambda target_fid=fid, n=note: self._quick_move_note_to_folder(n, target_fid),
            )
        menu.add_cascade(label="📁 Mover direto para", menu=move_submenu)

        menu.add_separator()
        menu.add_command(
            label="📤 Exportar para TXT",
            command=lambda: self._export_specific_note(note),
        )
        menu.add_command(
            label="🗑️ Excluir Nota",
            command=lambda: self._delete_specific_note(note),
        )
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    def _on_move_current_note_clicked(self):
        """Acionado pelo botão '📂 Mover de Pasta' na barra de ações do editor."""
        if self.active_note is None:
            if self.entry_title.get().strip():
                if not self.save_current_note(silent=True):
                    return
            else:
                show_message(
                    self,
                    "Mover Nota de Pasta",
                    "Selecione uma nota salva na lista à esquerda (ou salve a nota atual) para movê-la de pasta.",
                    kind="info",
                )
                return

        if self.active_note:
            self._open_move_note_dialog(self.active_note)

    def _open_move_note_dialog(self, note: NoteItem):
        """Abre o diálogo modal para escolher a pasta de destino e move a nota."""
        # Se a nota sendo movida for a nota ativa e tiver edições pendentes, salva antes
        if self.active_note and self.active_note.id == note.id and self.has_unsaved_changes:
            if self.entry_title.get().strip():
                self.save_current_note(silent=True)
                note = self.active_note

        diag = MoveNoteDialog(
            self,
            note_service=self.note_service,
            user_id=self.current_user.id,
            note=note,
        )
        if diag.result_note:
            moved = diag.result_note
            self._apply_note_moved(moved)

    def _quick_move_note_to_folder(self, note: NoteItem, target_folder_id: Optional[int]):
        """Move imediatamente uma nota para a pasta escolhida no menu rápido."""
        try:
            if self.active_note and self.active_note.id == note.id and self.has_unsaved_changes:
                if self.entry_title.get().strip():
                    self.save_current_note(silent=True)

            moved = self.note_service.move_note(
                user_id=self.current_user.id,
                note_id=note.id,
                target_folder_id=target_folder_id,
            )
            self._apply_note_moved(moved)
        except Exception as e:
            show_message(self, "Erro ao Mover Nota", str(e), kind="danger")

    def _apply_note_moved(self, moved_note: NoteItem):
        """Atualiza o estado da árvore e do editor após mover uma nota de pasta."""
        if moved_note.folder_id is not None:
            # Expande a pasta destino e todas as suas pastas ancestrais para exibir a nota movida
            all_folders = {f.id: f for f in self.note_service.list_folders(self.current_user.id)}
            curr_id = moved_note.folder_id
            visited = set()
            while curr_id is not None and curr_id in all_folders and curr_id not in visited:
                visited.add(curr_id)
                self.expanded_folders.add(curr_id)
                curr_id = all_folders[curr_id].parent_id

        self.selected_folder_id = moved_note.folder_id

        if self.active_note and self.active_note.id == moved_note.id:
            self.active_note = moved_note
            self._suppress_change_events = True
            try:
                self._refresh_folder_combo(moved_note.folder_id)
            finally:
                self._suppress_change_events = False
            self._update_status_indicator(saved=True, timestamp=moved_note.updated_at)
        else:
            self._refresh_folder_combo(self._get_editor_selected_folder_id())

        self._refresh_tree()

    # =========================================================================
    # Carregamento, Criação, Salvamento e Exclusão de Notas
    # =========================================================================

    def _create_note_in_folder(self, folder_id: Optional[int]):
        if not self.confirm_discard_if_unsaved():
            return
        self.selected_folder_id = folder_id
        if folder_id is not None:
            self.expanded_folders.add(folder_id)
        self._prepare_blank_note(folder_id=folder_id)
        self._refresh_tree()
        self.entry_title.focus_set()

    def _on_new_note_clicked(self):
        self._create_note_in_folder(self.selected_folder_id)

    def _prepare_blank_note(self, folder_id: Optional[int] = None):
        """Prepara o editor para uma nova nota em branco."""
        if self.autosave_timer_id:
            self.after_cancel(self.autosave_timer_id)
            self.autosave_timer_id = None

        self._suppress_change_events = True
        try:
            self.active_note = None
            self.entry_title.delete(0, "end")
            self.txt_content.delete("1.0", "end")
            reset_undo_stack(self.txt_content)
            self._refresh_folder_combo(folder_id)
            self.has_unsaved_changes = False
            self.lbl_save_status.configure(
                text="🟢 Nova nota (preencha o nome para salvar)",
                text_color=config.COLORS["text_muted"],
            )
            self._update_counts()
            self._clear_spelling_tags()
            clear_syntax_tags(self.txt_content._textbox)
        finally:
            self._suppress_change_events = False

    def _on_note_row_clicked(self, note: NoteItem):
        """Abre a nota clicada na barra lateral."""
        if self.active_note and self.active_note.id == note.id:
            return
        if not self.confirm_discard_if_unsaved():
            return
        self.load_note(note.id)

    def load_note(self, note_id: int) -> bool:
        """Carrega uma nota salva pelo ID no editor."""
        if self.autosave_timer_id:
            self.after_cancel(self.autosave_timer_id)
            self.autosave_timer_id = None

        fresh_note = self.note_service.get_note(self.current_user.id, note_id)
        if not fresh_note:
            show_message(self, "Aviso", "A nota selecionada não foi encontrada.", kind="warning")
            self._refresh_tree()
            return False

        self._suppress_change_events = True
        try:
            self.active_note = fresh_note
            self.selected_folder_id = fresh_note.folder_id
            if fresh_note.folder_id is not None:
                all_folders = {f.id: f for f in self.note_service.list_folders(self.current_user.id)}
                curr_id = fresh_note.folder_id
                visited = set()
                while curr_id is not None and curr_id in all_folders and curr_id not in visited:
                    visited.add(curr_id)
                    self.expanded_folders.add(curr_id)
                    curr_id = all_folders[curr_id].parent_id

            self.entry_title.delete(0, "end")
            self.entry_title.insert(0, fresh_note.title)

            self.txt_content.delete("1.0", "end")
            self.txt_content.insert("1.0", fresh_note.content or "")
            reset_undo_stack(self.txt_content)
            auto_highlight_content(self.txt_content)

            self._refresh_folder_combo(fresh_note.folder_id)
            self.has_unsaved_changes = False
            self._update_status_indicator(saved=True, timestamp=fresh_note.updated_at)
            self._update_counts()
            self._schedule_spellcheck()
        finally:
            self._suppress_change_events = False

        self._refresh_tree()
        return True

    def _on_folder_combo_changed(self, _selected_label: str):
        if self._suppress_change_events:
            return
        # Se a nota já existe no banco e possui título válido, move imediatamente para a pasta selecionada
        if self.active_note is not None and self.entry_title.get().strip():
            new_folder_id = self._get_editor_selected_folder_id()
            if new_folder_id != self.active_note.folder_id:
                if self.save_current_note(silent=True):
                    if new_folder_id is not None:
                        self._apply_note_moved(self.active_note)
                    return
        self._on_field_modified()

    def _on_field_modified(self, event=None):
        """Detecta alterações no título, pasta ou conteúdo da nota."""
        if self._suppress_change_events:
            return

        self._update_counts()
        self._schedule_spellcheck()

        curr_title = self.entry_title.get().strip()
        curr_content = self.txt_content.get("1.0", "end-1c")
        curr_folder_id = self._get_editor_selected_folder_id()

        if self.active_note is None:
            is_dirty = bool(curr_title or curr_content.strip())
        else:
            is_dirty = (
                curr_title != self.active_note.title
                or curr_content != (self.active_note.content or "")
                or curr_folder_id != self.active_note.folder_id
            )

        if is_dirty:
            if not self.has_unsaved_changes:
                self.has_unsaved_changes = True
                self._update_status_indicator(saved=False)

            # Autosave só dispara automaticamente se a nota já tiver um nome definido
            if self.autosave_enabled.get() and curr_title:
                if self.autosave_timer_id:
                    self.after_cancel(self.autosave_timer_id)
                self.autosave_timer_id = self.after(
                    config.AUTOSAVE_DELAY_SECONDS * 1000, self._handle_autosave
                )
        else:
            if self.has_unsaved_changes:
                self.has_unsaved_changes = False
                ts = self.active_note.updated_at if self.active_note else ""
                self._update_status_indicator(saved=True, timestamp=ts)

    def _update_counts(self):
        text = self.txt_content.get("1.0", "end-1c")
        chars = len(text)
        words = len(text.split()) if text.strip() else 0
        self.lbl_word_count.configure(text=f"{words} palavras | {chars:,} caracteres")

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
        if self.has_unsaved_changes and self.entry_title.get().strip():
            self.save_current_note(silent=True)

    def save_current_note(self, silent: bool = False) -> bool:
        """Salva ou atualiza a nota atual no banco de dados."""
        if self.autosave_timer_id:
            self.after_cancel(self.autosave_timer_id)
            self.autosave_timer_id = None

        title = self.entry_title.get().strip()
        content = self.txt_content.get("1.0", "end-1c")
        folder_id = self._get_editor_selected_folder_id()

        if not title:
            if not silent:
                show_message(
                    self,
                    "Nome da Nota Obrigatório",
                    "Digite um nome para a nota no campo 'Nome da Nota' antes de salvar.",
                    kind="warning",
                )
                self.entry_title.focus_set()
            return False

        try:
            self.lbl_save_status.configure(
                text="🟡 Salvando...",
                text_color=config.COLORS["warning"],
            )
            self.update_idletasks()

            note_id = self.active_note.id if self.active_note else None
            saved_note = self.note_service.save_note(
                user_id=self.current_user.id,
                title=title,
                content=content,
                folder_id=folder_id,
                note_id=note_id,
            )

            self.active_note = saved_note
            self.selected_folder_id = saved_note.folder_id
            if saved_note.folder_id is not None:
                self.expanded_folders.add(saved_note.folder_id)

            self.has_unsaved_changes = False
            self._update_status_indicator(saved=True, timestamp=saved_note.updated_at)
            self._refresh_tree()

            if not silent:
                self.btn_save.configure(fg_color=config.COLORS["success"])
                self.after(800, lambda: self.btn_save.configure(fg_color=config.COLORS["primary"]))

            return True
        except Exception as e:
            self.lbl_save_status.configure(
                text=f"❌ Erro ao salvar: {str(e)}",
                text_color=config.COLORS["danger"],
            )
            if not silent:
                show_message(self, "Erro ao Salvar Nota", str(e), kind="danger")
            return False

    def confirm_discard_if_unsaved(self) -> bool:
        """
        Verifica se há alterações não salvas antes de mudar de nota, trocar de menu ou fechar o app.
        """
        if not self.has_unsaved_changes:
            return True

        note_title = self.entry_title.get().strip() or (
            self.active_note.title if self.active_note else "Nova Nota"
        )
        custom_msg = (
            f"A nota '{note_title}' possui alterações que ainda não foram salvas no banco de dados.\n\n"
            "O que você deseja fazer?"
        )
        diag = UnsavedChangesDialog(self, note_title, custom_message=custom_msg)
        if diag.result == "save":
            return self.save_current_note()
        elif diag.result == "discard":
            self.has_unsaved_changes = False
            return True
        else:
            return False

    def _on_delete_current_note(self):
        if self.active_note is None:
            # Apenas limpa os campos se a nota ainda não foi salva
            self._prepare_blank_note(folder_id=self.selected_folder_id)
            return
        self._delete_specific_note(self.active_note)

    def _delete_specific_note(self, note: NoteItem):
        confirmed = ask_confirmation(
            self,
            "Excluir Nota",
            f"Deseja realmente excluir a nota '{note.title}'?",
            kind="danger",
        )
        if not confirmed:
            return

        self.note_service.delete_note(self.current_user.id, note.id)
        if self.active_note and self.active_note.id == note.id:
            self.has_unsaved_changes = False
            self._prepare_blank_note(folder_id=self.selected_folder_id)
        self._refresh_tree()

    def _on_export_note_clicked(self):
        if self.active_note is None and not self.entry_title.get().strip():
            show_message(self, "Aviso", "Selecione ou salve uma nota antes de exportar.", kind="warning")
            return

        if self.has_unsaved_changes and self.entry_title.get().strip():
            if not self.save_current_note(silent=True):
                return

        if self.active_note:
            self._export_specific_note(self.active_note)

    def _export_specific_note(self, note: NoteItem):
        safe_name = re.sub(r'[\\/*?:"<>|]', "_", note.title).strip() or "nota"
        file_path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar Nota para TXT",
            initialfile=f"{safe_name}.txt",
            defaultextension=".txt",
            filetypes=[("Arquivos de Texto", "*.txt")],
        )
        if file_path:
            path_map = self.note_service.get_folder_path_map(self.current_user.id)
            folder_path = path_map.get(note.folder_id, "Raiz (Sem pasta)") if note.folder_id else "Raiz (Sem pasta)"
            ok, msg = self.note_service.export_note_to_txt(note, file_path, folder_path=folder_path)
            if ok:
                show_message(self, "Sucesso", msg, kind="success")
            else:
                show_message(self, "Erro", msg, kind="danger")

    def _on_import_notes_clicked(self):
        """
        Permite selecionar um ou vários arquivos TXT e pergunta em qual pasta
        deseja colocar a(s) nota(s) ou se precisa criar uma nova pasta.
        Não exige formato de data nos nomes dos arquivos.
        """
        if not self.confirm_discard_if_unsaved():
            return

        file_paths = filedialog.askopenfilenames(
            parent=self,
            title="Selecione o(s) arquivo(s) TXT para importar como Nota(s)",
            filetypes=[("Arquivos de Texto", "*.txt"), ("Todos os Arquivos", "*.*")],
        )
        if not file_paths:
            return

        files_list = list(file_paths)
        if len(files_list) == 1:
            desc = f"📄 Arquivo selecionado: {os.path.basename(files_list[0])}"
        else:
            desc = f"📄 {len(files_list)} arquivos TXT selecionados para importação."

        diag = SelectImportFolderDialog(
            self,
            note_service=self.note_service,
            user_id=self.current_user.id,
            files_description=desc,
            default_folder_id=self.selected_folder_id,
        )
        if not diag.confirmed:
            return

        target_folder_id = diag.selected_folder_id
        imported_count = 0
        skipped_count = 0
        error_count = 0
        last_imported_note_id: Optional[int] = None

        for fpath in files_list:
            res = self.import_service.import_note_file(
                file_path=fpath,
                user_id=self.current_user.id,
                folder_id=target_folder_id,
                conflict_resolution=ConflictResolution.REPLACE,
            )
            if res["status"] == "imported":
                imported_count += 1
                last_imported_note_id = res.get("note_id") or last_imported_note_id
            elif res["status"] == "skipped":
                skipped_count += 1
            else:
                error_count += 1

        if target_folder_id is not None:
            self.expanded_folders.add(target_folder_id)
        self.selected_folder_id = target_folder_id
        self._refresh_folder_combo(target_folder_id)
        self._refresh_tree()

        if last_imported_note_id is not None:
            self.load_note(last_imported_note_id)

        path_map = self.note_service.get_folder_path_map(self.current_user.id)
        folder_label = (
            path_map.get(target_folder_id, "Raiz (Sem pasta)")
            if target_folder_id is not None
            else "Raiz (Sem pasta)"
        )
        show_message(
            self,
            "Importação Concluída",
            f"Importação para a pasta '{folder_label}':\n\n"
            f"✅ Importadas: {imported_count}\n"
            f"⚠️ Ignoradas: {skipped_count}\n"
            f"❌ Erros: {error_count}",
            kind="success" if error_count == 0 else "warning",
        )

    # =========================================================================
    # Formatação de Texto (MAIÚSCULO, minúsculo, XML e SQL com cores)
    # =========================================================================

    def _on_uppercase_clicked(self):
        """Converte o texto selecionado no editor (ou no título) para MAIÚSCULO."""
        ok, msg = convert_selection_case(
            self.txt_content,
            uppercase=True,
            fallback_entry=self.entry_title,
        )
        if not ok:
            show_message(self, "Converter para MAIÚSCULO", msg, kind="info")
            return
        self._on_field_modified()

    def _on_lowercase_clicked(self):
        """Converte o texto selecionado no editor (ou no título) para minúsculo."""
        ok, msg = convert_selection_case(
            self.txt_content,
            uppercase=False,
            fallback_entry=self.entry_title,
        )
        if not ok:
            show_message(self, "Converter para minúsculo", msg, kind="info")
            return
        self._on_field_modified()

    def _on_format_xml_clicked(self):
        """Formata e aplica cores de sintaxe XML ao texto selecionado (ou a toda a nota)."""
        if not format_and_highlight_xml(self.txt_content, indent_xml=True):
            show_message(self, "Formatar XML", "Não há texto na nota para formatar como XML.", kind="info")
            return
        self._on_field_modified()

    def _on_format_sql_clicked(self):
        """Formata e aplica cores de sintaxe SQL ao texto selecionado (ou a toda a nota)."""
        if not format_and_highlight_sql(self.txt_content, format_keywords=True):
            show_message(self, "Formatar SQL", "Não há texto na nota para formatar como SQL.", kind="info")
            return
        self._on_field_modified()

    def _on_clear_syntax_colors_clicked(self):
        """Remove a coloração de sintaxe XML/SQL do trecho selecionado ou de todo o texto."""
        tb = self.txt_content._textbox
        sel = tb.tag_ranges("sel")
        if sel:
            clear_syntax_tags(tb, tb.index("sel.first"), tb.index("sel.last"))
        else:
            clear_syntax_tags(tb, "1.0", "end")
        self._run_spellcheck()

    def _on_undo_clicked(self):
        """Desfaz a última ação (digitação, colagem ou formatação)."""
        perform_undo(self.txt_content, on_change_callback=self._on_field_modified)

    def _on_redo_clicked(self):
        """Refaz a última ação desfeita."""
        perform_redo(self.txt_content, on_change_callback=self._on_field_modified)

    def _on_cut_clicked(self):
        """Recorta o texto selecionado e registra no histórico de desfazer."""
        try:
            self.txt_content._textbox.event_generate("<<Cut>>")
            self._on_field_modified()
        except Exception:
            pass

    def _on_print_clicked(self):
        """Salva temporariamente a nota e abre para impressão no Windows."""
        try:
            title = self.entry_title.get().strip() or (self.active_note.title if self.active_note else "Nota")
            content = self.txt_content.get("1.0", "end-1c")

            import tempfile
            import subprocess
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", title).strip() or "nota"
            temp_file = os.path.join(tempfile.gettempdir(), f"{safe_title}.txt")
            header = f"NOTA: {title}\n" + ("=" * 50) + "\n\n"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(header + content)

            if os.name == "nt":
                os.startfile(temp_file, "open")
            else:
                subprocess.Popen(["xdg-open", temp_file])
        except Exception as e:
            show_message(self, "Imprimir Nota", f"Não foi possível abrir o arquivo para impressão:\n{e}", kind="warning")

    def _on_paste(self, event=None):
        """
        Trata a colagem de texto na nota registrando separadores de Undo (Ctrl+Z)
        para que seja possível desfazer a colagem de uma só vez.
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

        if text_widget.tag_ranges("sel"):
            text_widget.delete("sel.first", "sel.last")

        text_widget.insert("insert", clipboard_text)

        try:
            text_widget.edit_separator()
        except Exception:
            pass

        auto_highlight_content(self.txt_content)
        text_widget.see("insert")
        text_widget.focus_set()
        self._on_field_modified()
        return "break"

    # =========================================================================
    # Corretor Ortográfico Nativo do Windows
    # =========================================================================

    def _configure_spellcheck_tags(self):
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
        try:
            self.txt_content._textbox.tag_remove("spelling_error", "1.0", "end")
        except Exception:
            pass

    def _run_spellcheck(self):
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
        text_widget = self.txt_content._textbox
        click_idx = text_widget.index(f"@{event.x},{event.y}")

        if not text_widget.tag_ranges("sel"):
            text_widget.mark_set("insert", click_idx)

        tags_at_click = text_widget.tag_names(click_idx)
        has_spelling_error = "spelling_error" in tags_at_click

        word_range = None
        err_word = ""
        if has_spelling_error:
            r = text_widget.tag_prevrange("spelling_error", click_idx + "+1c")
            if r:
                word_range = r
                err_word = text_widget.get(r[0], r[1]).strip()

        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")
        menu_bg = config.COLORS["card_dark"][1 if is_dark else 0]
        menu_fg = config.COLORS["text_dark"][1 if is_dark else 0]
        active_bg = config.COLORS["primary"][1 if is_dark else 0]

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=menu_bg,
            fg=menu_fg,
            activebackground=active_bg,
            activeforeground="#FFFFFF",
            font=("Segoe UI", 10),
            relief="flat",
            bd=1,
        )

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
            toggle_text = (
                "🔲 Desativar Corretor Ortográfico"
                if self.spellcheck_enabled.get()
                else "☑ Ativar Corretor Ortográfico"
            )
            menu.add_command(label=toggle_text, command=self._toggle_spellcheck)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _replace_spelling_error(self, start_idx: str, end_idx: str, replacement: str):
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
        self._on_field_modified()
        self._run_spellcheck()

    def _add_to_dict_and_refresh(self, word: str):
        self.spell_service.add_to_dictionary(word)
        self._run_spellcheck()

    def _ignore_word_and_refresh(self, word: str):
        self.spell_service.ignore_word(word)
        self._run_spellcheck()

    def _select_all_text(self):
        text_widget = self.txt_content._textbox
        text_widget.tag_add("sel", "1.0", "end-1c")
        text_widget.mark_set("insert", "1.0")
        text_widget.see("insert")

