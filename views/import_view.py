import os
import tkinter as tk
from tkinter import filedialog
from typing import Optional, Callable, List, Dict, Any, Tuple
import customtkinter as ctk

import config
from models.user import User
from services.import_service import ImportService, ConflictResolution
from services.note_service import NoteService
from utils.date_utils import format_date_br
from views.components.dialogs import show_message, ask_confirmation
from views.notes_view import FolderDialog, SelectImportFolderDialog


class ImportView(ctk.CTkFrame):
    """
    Tela para importação de arquivos TXT (individuais ou em lote) diretamente para Pastas.
    - Não exige formato de data no nome do arquivo (qualquer arquivo .txt é aceito)
    - Pergunta em qual pasta o usuário deseja colocar a(s) nota(s) ou se deseja criar uma nova pasta
    - Exibe em destaque o último arquivo TXT importado pelo usuário
    - Detecta codificações automaticamente (UTF-8 e Windows-1252)
    - Opções claras de resolução de duplicidade (ignorar, substituir, mesclar)
    - Resumo detalhado e log em tempo real
    """

    def __init__(
        self,
        master,
        current_user: User,
        import_service: ImportService,
        note_service: Optional[NoteService] = None,
        on_import_completed: Optional[Callable[[], None]] = None,
        on_open_diary_date: Optional[Callable[[str, int], None]] = None,
        on_open_imported_note: Optional[Callable[[Optional[int], Optional[int]], None]] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.import_service = import_service
        self.note_service = note_service or self.import_service.note_service
        self.on_import_completed = on_import_completed
        self.on_open_diary_date = on_open_diary_date
        self.on_open_imported_note = on_open_imported_note

        self.import_mode = tk.StringVar(value="file")  # 'file' ou 'folder'
        self.conflict_mode = tk.StringVar(value=ConflictResolution.SKIP.value)
        self.selected_files: List[str] = []
        self.last_imported_info: Optional[Dict[str, Any]] = None
        self.folder_options: List[Tuple[Optional[int], str]] = []

        self._build_ui()
        self._refresh_target_folder_options()
        self._refresh_last_imported_info()

    def _build_ui(self):
        # 1. Cabeçalho
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
            text="📥 Importação de Notas TXT para Pastas",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(side="left", padx=15, pady=12)

        self.lbl_subtitle = ctk.CTkLabel(
            self.header_card,
            text="Sem necessidade de formato de data • Escolha ou crie a pasta de destino",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_subtitle.pack(side="right", padx=15, pady=12)

        # Card / Indicador do Último TXT Importado (no cabeçalho/topo da tela)
        self.last_import_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.last_import_card.pack(fill="x", padx=20, pady=(0, 10))

        self.lbl_last_import_title = ctk.CTkLabel(
            self.last_import_card,
            text="📄 Último TXT Importado:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["primary"],
        )
        self.lbl_last_import_title.pack(side="left", padx=(15, 8), pady=10)

        self.lbl_last_import_value = ctk.CTkLabel(
            self.last_import_card,
            text="Nenhum arquivo TXT importado até o momento.",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        self.lbl_last_import_value.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=10)

        self.btn_open_last_imported = ctk.CTkButton(
            self.last_import_card,
            text="🗂️ Abrir em Notas & Pastas",
            width=180,
            height=30,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._on_open_last_imported,
        )

        # 2. Painel de Configurações da Importação
        self.settings_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.settings_card.pack(fill="x", padx=20, pady=(0, 10))

        # Seleção de Modo (Arquivos vs Pasta do Computador)
        self.mode_frame = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.mode_frame.pack(fill="x", padx=15, pady=(12, 6))

        self.lbl_mode = ctk.CTkLabel(
            self.mode_frame,
            text="Origem da Importação:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_mode.pack(side="left", padx=(0, 15))

        self.rb_file = ctk.CTkRadioButton(
            self.mode_frame,
            text="📄 Arquivo(s) TXT (um ou vários, qualquer nome)",
            variable=self.import_mode,
            value="file",
            text_color=config.COLORS["text_dark"],
            command=self._on_mode_changed,
        )
        self.rb_file.pack(side="left", padx=10)

        self.rb_folder = ctk.CTkRadioButton(
            self.mode_frame,
            text="📁 Pasta do computador (todos os TXTs da pasta)",
            variable=self.import_mode,
            value="folder",
            text_color=config.COLORS["text_dark"],
            command=self._on_mode_changed,
        )
        self.rb_folder.pack(side="left", padx=10)

        # Seleção do Caminho dos Arquivos
        self.path_frame = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.path_frame.pack(fill="x", padx=15, pady=6)

        self.entry_path = ctk.CTkEntry(
            self.path_frame,
            height=38,
            placeholder_text="Selecione um ou vários arquivos TXT (qualquer nome, sem precisar de data)...",
            font=ctk.CTkFont(size=13),
            corner_radius=8,
        )
        self.entry_path.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_browse = ctk.CTkButton(
            self.path_frame,
            text="Selecionar...",
            width=120,
            height=38,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._browse_path,
        )
        self.btn_browse.pack(side="left")

        # Seleção Prévia da Pasta de Destino (em Notas & Pastas) + Botão Nova Pasta
        self.dest_folder_frame = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.dest_folder_frame.pack(fill="x", padx=15, pady=(4, 4))

        self.lbl_dest_folder = ctk.CTkLabel(
            self.dest_folder_frame,
            text="📂 Pasta de Destino da(s) Nota(s):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_dest_folder.pack(side="left", padx=(0, 10))

        self.combo_target_folder = ctk.CTkComboBox(
            self.dest_folder_frame,
            values=["📁 Sem pasta (Raiz)"],
            width=280,
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
        self.combo_target_folder.pack(side="left", padx=(0, 8))

        self.btn_new_folder = ctk.CTkButton(
            self.dest_folder_frame,
            text="📁+ Criar Nova Pasta",
            width=150,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._on_create_new_folder_clicked,
        )
        self.btn_new_folder.pack(side="left")

        # Dica explicativa
        self.lbl_folder_tip = ctk.CTkLabel(
            self.settings_card,
            text="💡 Dica: Não é necessário formato de data no nome do arquivo. Ao iniciar a importação, o sistema confirmará em qual pasta deseja colocar a(s) nota(s) ou permitirá criar uma nova pasta na hora.",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
            wraplength=760,
            justify="left",
            anchor="w",
        )
        self.lbl_folder_tip.pack(fill="x", padx=15, pady=(2, 8))

        # Opções de Resolução de Duplicidades
        self.conflict_frame = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.conflict_frame.pack(fill="x", padx=15, pady=(4, 12))

        self.lbl_conflict = ctk.CTkLabel(
            self.conflict_frame,
            text="Se já existir uma nota com o mesmo nome na pasta escolhida:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_conflict.pack(anchor="w", pady=(0, 6))

        self.rb_skip = ctk.CTkRadioButton(
            self.conflict_frame,
            text="Ignorar o arquivo (preserva a nota existente)",
            variable=self.conflict_mode,
            value=ConflictResolution.SKIP.value,
            text_color=config.COLORS["text_dark"],
        )
        self.rb_skip.pack(anchor="w", padx=15, pady=2)

        self.rb_merge = ctk.CTkRadioButton(
            self.conflict_frame,
            text="Mesclar conteúdos (adiciona o novo conteúdo ao final da nota existente)",
            variable=self.conflict_mode,
            value=ConflictResolution.MERGE.value,
            text_color=config.COLORS["text_dark"],
        )
        self.rb_merge.pack(anchor="w", padx=15, pady=2)

        self.rb_replace = ctk.CTkRadioButton(
            self.conflict_frame,
            text="Substituir nota existente (sobrescreve o conteúdo pelo novo arquivo)",
            variable=self.conflict_mode,
            value=ConflictResolution.REPLACE.value,
            text_color=config.COLORS["text_dark"],
        )
        self.rb_replace.pack(anchor="w", padx=15, pady=2)

        # Botão Iniciar Importação
        self.btn_start = ctk.CTkButton(
            self.settings_card,
            text="🚀 Iniciar Importação e Escolher Pasta",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._start_import,
        )
        self.btn_start.pack(fill="x", padx=15, pady=(4, 15))

        # Barra de Progresso
        self.progress_bar = ctk.CTkProgressBar(
            self.settings_card,
            height=8,
            corner_radius=4,
            progress_color=config.COLORS["success"],
        )
        self.progress_bar.set(0)

        # 3. Painel de Resumo dos Resultados
        self.summary_card = ctk.CTkFrame(
            self,
            height=45,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.summary_card.pack(fill="x", padx=20, pady=(0, 10))

        self.lbl_summary = ctk.CTkLabel(
            self.summary_card,
            text="Aguardando seleção de arquivos para importar em pastas.",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_summary.pack(side="left", padx=15, pady=10)

        # 4. Log em Tempo Real da Importação
        self.log_container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.log_container.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        self.lbl_log_title = ctk.CTkLabel(
            self.log_container,
            text="📋 Detalhes do Processamento:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_log_title.pack(anchor="w", padx=15, pady=(10, 4))

        self.txt_log = ctk.CTkTextbox(
            self.log_container,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.txt_log.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def _refresh_target_folder_options(self, selected_folder_id: Optional[int] = None):
        """Atualiza o seletor de pastas disponíveis para importação."""
        self.folder_options = self.note_service.get_folder_tree_options(self.current_user.id)
        labels = [lbl for _, lbl in self.folder_options]
        self.combo_target_folder.configure(values=labels)

        chosen = labels[0] if labels else "📁 Sem pasta (Raiz)"
        for fid, lbl in self.folder_options:
            if fid == selected_folder_id:
                chosen = lbl
                break
        self.combo_target_folder.set(chosen)

    def _get_preselected_folder_id(self) -> Optional[int]:
        chosen = self.combo_target_folder.get()
        for fid, lbl in self.folder_options:
            if lbl == chosen:
                return fid
        return None

    def _on_create_new_folder_clicked(self):
        current_sel = self._get_preselected_folder_id()
        diag = FolderDialog(
            self,
            note_service=self.note_service,
            user_id=self.current_user.id,
            folder=None,
            default_parent_id=current_sel,
        )
        if diag.result_folder:
            self._refresh_target_folder_options(selected_folder_id=diag.result_folder.id)

    def _refresh_last_imported_info(self):
        """Consulta e exibe na tela o último arquivo TXT importado pelo usuário."""
        info = self.import_service.get_last_imported_txt(self.current_user.id)
        self.last_imported_info = info

        if not info:
            self.lbl_last_import_value.configure(
                text="Nenhum arquivo TXT importado até o momento.",
                text_color=config.COLORS["text_muted"],
            )
            if self.btn_open_last_imported.winfo_ismapped():
                self.btn_open_last_imported.pack_forget()
            return

        filename = info.get("filename", "")
        target_type = info.get("target_type", "note")
        folder_name = info.get("folder_name", "Raiz (Sem pasta)")
        date_br = info.get("date_br", "")
        imported_at = info.get("imported_at", "")

        imported_at_display = imported_at
        if imported_at and " " in imported_at:
            d_part, t_part = imported_at.split(" ", 1)
            imported_at_display = f"{format_date_br(d_part)} às {t_part}"

        if target_type == "note" or not date_br:
            display_text = f"{filename}   •   Pasta: 📁 {folder_name}"
            btn_label = "🗂️ Abrir em Notas & Pastas"
        else:
            display_text = f"{filename}   •   Data no Diário: {date_br}"
            btn_label = "📖 Abrir no Diário"

        if imported_at_display:
            display_text += f"   •   Importado em: {imported_at_display}"

        self.lbl_last_import_value.configure(
            text=display_text,
            text_color=config.COLORS["success"],
        )
        self.btn_open_last_imported.configure(text=btn_label)
        if not self.btn_open_last_imported.winfo_ismapped():
            self.btn_open_last_imported.pack(side="right", padx=15, pady=8)

    def _on_open_last_imported(self):
        if not self.last_imported_info:
            return
        target_type = self.last_imported_info.get("target_type", "note")
        if target_type == "note" and self.on_open_imported_note:
            folder_id = self.last_imported_info.get("folder_id")
            note_id = self.last_imported_info.get("note_id")
            self.on_open_imported_note(folder_id, note_id)
        elif self.on_open_diary_date:
            entry_date = self.last_imported_info.get("entry_date")
            if entry_date:
                self.on_open_diary_date(entry_date, self.current_user.id)

    def _on_mode_changed(self):
        self.entry_path.delete(0, "end")
        self.selected_files.clear()
        mode = self.import_mode.get()
        if mode == "folder":
            self.entry_path.configure(placeholder_text="Selecione a pasta do computador com os arquivos TXT...")
            self.lbl_folder_tip.configure(
                text="💡 Dica: Todos os arquivos .txt da pasta selecionada serão importados como notas (sem exigir formato de data). "
                     "Ao clicar em Iniciar, você poderá confirmar em qual pasta do sistema deseja colocá-las ou criar uma nova pasta."
            )
        else:
            self.entry_path.configure(
                placeholder_text="Selecione um ou vários arquivos TXT (qualquer nome, sem precisar de data)..."
            )
            self.lbl_folder_tip.configure(
                text="💡 Dica: Selecione um ou vários arquivos .txt (com qualquer nome). O nome do arquivo será usado como título da nota "
                     "e o sistema perguntará em qual pasta deseja salvar ou se deseja criar uma nova pasta."
            )

    def _browse_path(self):
        mode = self.import_mode.get()
        if mode == "folder":
            folder = filedialog.askdirectory(parent=self, title="Selecione a pasta com os arquivos TXT")
            if folder:
                self.selected_files.clear()
                self.entry_path.delete(0, "end")
                self.entry_path.insert(0, folder)
        else:
            file_paths = filedialog.askopenfilenames(
                parent=self,
                title="Selecione os arquivos TXT para importar como Notas (Ctrl+A para selecionar todos)",
                filetypes=[("Arquivos de Texto", "*.txt"), ("Todos os Arquivos", "*.*")],
            )
            if file_paths:
                self.selected_files = list(file_paths)
                self.entry_path.delete(0, "end")
                if len(self.selected_files) == 1:
                    self.entry_path.insert(0, self.selected_files[0])
                else:
                    folder_name = os.path.basename(os.path.dirname(self.selected_files[0]))
                    self.entry_path.insert(
                        0, f"{len(self.selected_files)} arquivos TXT selecionados (pasta: {folder_name})"
                    )

    def _log(self, text: str):
        self.txt_log.insert("end", text + "\n")
        self.txt_log.see("end")
        self.update_idletasks()

    def _start_import(self):
        path = self.entry_path.get().strip()
        if not path and not self.selected_files:
            show_message(
                self,
                "Aviso",
                "Por favor, selecione um ou mais arquivos TXT (ou uma pasta) antes de iniciar.",
                kind="warning",
            )
            return

        mode = self.import_mode.get()
        conflict = ConflictResolution(self.conflict_mode.get())

        # Valida arquivos antes de abrir a pergunta de pasta
        files_to_process: List[str] = []
        if mode == "file":
            files_to_process = (
                self.selected_files
                if self.selected_files
                else ([path] if os.path.isfile(path) else [])
            )
            if not files_to_process:
                show_message(self, "Erro", "Nenhum arquivo TXT válido foi encontrado.", kind="danger")
                return
            if len(files_to_process) == 1:
                files_desc = f"📄 Arquivo selecionado: {os.path.basename(files_to_process[0])}"
            else:
                files_desc = f"📄 {len(files_to_process)} arquivos TXT selecionados para importação."
        else:
            if not os.path.isdir(path):
                show_message(self, "Erro", "A pasta especificada não existe.", kind="danger")
                return
            txt_in_dir = [
                f for f in os.listdir(path)
                if f.lower().endswith(".txt") and os.path.isfile(os.path.join(path, f))
            ]
            if not txt_in_dir:
                show_message(
                    self,
                    "Aviso",
                    "Não foram encontrados arquivos .txt na pasta selecionada.",
                    kind="warning",
                )
                return
            files_desc = f"📁 {len(txt_in_dir)} arquivo(s) TXT encontrados na pasta '{os.path.basename(path)}'."

        # Pergunta ao usuário em qual pasta deseja colocar a(s) nota(s) ou se precisa criar uma nova pasta
        preselected_folder_id = self._get_preselected_folder_id()
        folder_dialog = SelectImportFolderDialog(
            self,
            note_service=self.note_service,
            user_id=self.current_user.id,
            files_description=files_desc,
            default_folder_id=preselected_folder_id,
        )
        if not folder_dialog.confirmed:
            return

        target_folder_id = folder_dialog.selected_folder_id
        self._refresh_target_folder_options(selected_folder_id=target_folder_id)

        path_map = self.note_service.get_folder_path_map(self.current_user.id)
        target_folder_label = (
            path_map.get(target_folder_id, "Raiz (Sem pasta)")
            if target_folder_id is not None
            else "Raiz (Sem pasta)"
        )

        if conflict == ConflictResolution.REPLACE:
            confirmed = ask_confirmation(
                self,
                "Confirmação de Substituição",
                f"Você selecionou a opção de SUBSTITUIR notas existentes na pasta '{target_folder_label}'.\n"
                "Caso já exista uma nota com o mesmo nome, seu conteúdo atual será sobrescrito.\n\n"
                "Deseja continuar?",
                kind="warning",
            )
            if not confirmed:
                return

        self.txt_log.delete("1.0", "end")
        self.btn_start.configure(state="disabled")
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 10))
        self.progress_bar.set(0)

        try:
            if mode == "file":
                total_files = len(files_to_process)
                imported_count = 0
                skipped_count = 0
                error_count = 0

                self._log(
                    f"Iniciando importação de {total_files} arquivo(s) TXT para a pasta '{target_folder_label}'..."
                )

                for idx, fpath in enumerate(files_to_process, start=1):
                    progress = idx / max(1, total_files)
                    self.progress_bar.set(progress)
                    filename = os.path.basename(fpath)
                    self._log(f"[{idx}/{total_files}] Importando: {filename}...")

                    res = self.import_service.import_note_file(
                        file_path=fpath,
                        user_id=self.current_user.id,
                        folder_id=target_folder_id,
                        conflict_resolution=conflict,
                    )

                    if res["status"] == "imported":
                        imported_count += 1
                        self._log(f"✅ {filename} -> {res['message']}")
                    elif res["status"] == "skipped":
                        skipped_count += 1
                        self._log(f"⚠️ {filename} -> {res['message']}")
                    else:
                        error_count += 1
                        self._log(f"❌ {filename} -> {res['message']}")

                self._log("\n" + "=" * 55)
                self._log(f"RESUMO FINAL DA IMPORTAÇÃO (Pasta: {target_folder_label}):")
                self._log(f"Total de arquivos analisados: {total_files}")
                self._log(f"Notas importadas com sucesso: {imported_count}")
                self._log(f"Ignoradas: {skipped_count}")
                self._log(f"Erros: {error_count}")
                self._log("=" * 55)

                self.lbl_summary.configure(
                    text=(
                        f"Pasta '{target_folder_label}': {imported_count} importada(s) | "
                        f"{skipped_count} ignorada(s) | {error_count} erro(s)."
                    ),
                    text_color=config.COLORS["success"] if error_count == 0 else config.COLORS["warning"],
                )

            else:  # mode == "folder"
                self._log(
                    f"Iniciando importação dos arquivos TXT de '{path}' para a pasta '{target_folder_label}'..."
                )

                def progress_cb(current, total, filename):
                    progress = current / max(1, total)
                    self.progress_bar.set(progress)
                    self._log(f"[{current}/{total}] Importando: {filename}...")

                report = self.import_service.import_folder_to_notes(
                    folder_path=path,
                    user_id=self.current_user.id,
                    target_folder_id=target_folder_id,
                    default_conflict=conflict,
                    progress_callback=progress_cb,
                )

                self._log("\n" + "=" * 55)
                self._log(f"RESUMO FINAL DA IMPORTAÇÃO (Pasta: {target_folder_label}):")
                self._log(f"Total de arquivos analisados: {report['total']}")
                self._log(f"Notas importadas com sucesso: {report['imported']}")
                self._log(f"Ignoradas: {report['skipped']}")
                self._log(f"Erros: {report['errors']}")
                self._log("=" * 55)

                for item in report["details"]:
                    status_icon = (
                        "✅" if item["status"] == "imported" else ("⚠️" if item["status"] == "skipped" else "❌")
                    )
                    self._log(f"{status_icon} {item['filename']} -> {item['message']}")

                self.lbl_summary.configure(
                    text=(
                        f"Pasta '{target_folder_label}': {report['imported']} importada(s) | "
                        f"{report['skipped']} ignorada(s) | {report['errors']} erro(s)."
                    ),
                    text_color=config.COLORS["success"] if report["errors"] == 0 else config.COLORS["warning"],
                )

            # Atualiza o card do Último TXT Importado imediatamente após o processamento
            self._refresh_last_imported_info()

            if self.on_import_completed:
                self.on_import_completed()

        except Exception as e:
            self._log(f"❌ Ocorreu um erro fatal durante a importação: {str(e)}")
            show_message(self, "Erro", f"Erro no processo de importação: {str(e)}", kind="danger")
        finally:
            self.btn_start.configure(state="normal")
