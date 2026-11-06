import os
import tkinter as tk
from tkinter import filedialog
from typing import Optional, Callable, List, Dict, Any
import customtkinter as ctk

import config
from models.user import User
from services.import_service import ImportService, ConflictResolution
from utils.date_utils import format_date_br, parse_date_input
from views.components.dialogs import show_message, ask_confirmation


class ImportView(ctk.CTkFrame):
    """
    Tela para importação de arquivos TXT individuais ou em lote.
    - Suporta padrão DD MM AAAA.txt (ex: 01 10 2026.txt)
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
        on_import_completed: Optional[Callable[[], None]] = None,
        on_open_diary_date: Optional[Callable[[str, int], None]] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.import_service = import_service
        self.on_import_completed = on_import_completed
        self.on_open_diary_date = on_open_diary_date

        self.import_mode = tk.StringVar(value="folder")  # 'folder' ou 'file'
        self.conflict_mode = tk.StringVar(value=ConflictResolution.SKIP.value)
        self.selected_files: List[str] = []
        self.last_imported_info: Optional[Dict[str, Any]] = None

        self._build_ui()
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
            text="📥 Importação de Arquivos TXT para o Diário",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(side="left", padx=15, pady=12)

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

        self.btn_open_last_diary = ctk.CTkButton(
            self.last_import_card,
            text="📖 Abrir no Diário",
            width=135,
            height=30,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._on_open_last_imported_diary,
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

        # Seleção de Modo (Pasta vs Arquivos)
        self.mode_frame = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.mode_frame.pack(fill="x", padx=15, pady=(12, 6))

        self.lbl_mode = ctk.CTkLabel(
            self.mode_frame,
            text="Origem da Importação:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_mode.pack(side="left", padx=(0, 15))

        self.rb_folder = ctk.CTkRadioButton(
            self.mode_frame,
            text="📁 Pasta completa (todos os TXTs da pasta)",
            variable=self.import_mode,
            value="folder",
            text_color=config.COLORS["text_dark"],
            command=self._on_mode_changed,
        )
        self.rb_folder.pack(side="left", padx=10)

        self.rb_file = ctk.CTkRadioButton(
            self.mode_frame,
            text="📄 Arquivo(s) TXT (um ou vários)",
            variable=self.import_mode,
            value="file",
            text_color=config.COLORS["text_dark"],
            command=self._on_mode_changed,
        )
        self.rb_file.pack(side="left", padx=10)

        # Seleção do Caminho
        self.path_frame = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.path_frame.pack(fill="x", padx=15, pady=6)

        self.entry_path = ctk.CTkEntry(
            self.path_frame,
            height=38,
            placeholder_text="Selecione a pasta com os arquivos TXT...",
            font=ctk.CTkFont(size=13),
            corner_radius=8,
        )
        self.entry_path.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_browse = ctk.CTkButton(
            self.path_frame,
            text="Selecionar...",
            width=110,
            height=38,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._browse_path,
        )
        self.btn_browse.pack(side="left")

        # Dica explicativa sobre a janela de seleção de pastas do Windows
        self.lbl_folder_tip = ctk.CTkLabel(
            self.settings_card,
            text="💡 Dica sobre pastas no Windows: Na janela de selecionar pasta, os arquivos de texto (.txt) não aparecem na listagem porque ela serve apenas para escolher pastas. "
                 "Não se preocupe: basta entrar na pasta desejada e clicar no botão 'Selecionar pasta' no rodapé. Se preferir ver e selecionar os arquivos individualmente, use a opção 'Arquivo(s) TXT' acima.",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
            wraplength=700,
            justify="left",
            anchor="w",
        )
        self.lbl_folder_tip.pack(fill="x", padx=15, pady=(2, 8))

        # Opções de Resolução de Duplicidades
        self.conflict_frame = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.conflict_frame.pack(fill="x", padx=15, pady=(6, 12))

        self.lbl_conflict = ctk.CTkLabel(
            self.conflict_frame,
            text="Se já existir anotação para a data:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_conflict.pack(anchor="w", pady=(0, 6))

        self.rb_skip = ctk.CTkRadioButton(
            self.conflict_frame,
            text="Ignorar o arquivo (preserva a anotação existente)",
            variable=self.conflict_mode,
            value=ConflictResolution.SKIP.value,
            text_color=config.COLORS["text_dark"],
        )
        self.rb_skip.pack(anchor="w", padx=15, pady=2)

        self.rb_merge = ctk.CTkRadioButton(
            self.conflict_frame,
            text="Mesclar conteúdos (adiciona o novo conteúdo ao final, com separador datado)",
            variable=self.conflict_mode,
            value=ConflictResolution.MERGE.value,
            text_color=config.COLORS["text_dark"],
        )
        self.rb_merge.pack(anchor="w", padx=15, pady=2)

        self.rb_replace = ctk.CTkRadioButton(
            self.conflict_frame,
            text="Substituir anotação existente (sobrescreve o conteúdo pelo novo arquivo)",
            variable=self.conflict_mode,
            value=ConflictResolution.REPLACE.value,
            text_color=config.COLORS["text_dark"],
        )
        self.rb_replace.pack(anchor="w", padx=15, pady=2)

        # Botão Iniciar Importação
        self.btn_start = ctk.CTkButton(
            self.settings_card,
            text="🚀 Iniciar Importação",
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
            text="Aguardando seleção de arquivos.",
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

    def _refresh_last_imported_info(self):
        """Consulta e exibe na tela o último arquivo TXT importado pelo usuário."""
        info = self.import_service.get_last_imported_txt(self.current_user.id)
        self.last_imported_info = info

        if not info:
            self.lbl_last_import_value.configure(
                text="Nenhum arquivo TXT importado até o momento.",
                text_color=config.COLORS["text_muted"],
            )
            if self.btn_open_last_diary.winfo_ismapped():
                self.btn_open_last_diary.pack_forget()
            return

        filename = info.get("filename", "")
        date_br = info.get("date_br", "")
        imported_at = info.get("imported_at", "")

        # Formata o timestamp de importação (YYYY-MM-DD HH:MM:SS -> DD/MM/AAAA às HH:MM:SS)
        imported_at_display = imported_at
        if imported_at and " " in imported_at:
            d_part, t_part = imported_at.split(" ", 1)
            imported_at_display = f"{format_date_br(d_part)} às {t_part}"

        display_text = f"{filename}   •   Data no Diário: {date_br}"
        if imported_at_display:
            display_text += f"   •   Importado em: {imported_at_display}"

        self.lbl_last_import_value.configure(
            text=display_text,
            text_color=config.COLORS["success"],
        )
        if not self.btn_open_last_diary.winfo_ismapped():
            self.btn_open_last_diary.pack(side="right", padx=15, pady=8)

    def _on_open_last_imported_diary(self):
        if self.last_imported_info and self.on_open_diary_date:
            entry_date = self.last_imported_info.get("entry_date")
            if entry_date:
                self.on_open_diary_date(entry_date, self.current_user.id)

    def _on_mode_changed(self):
        self.entry_path.delete(0, "end")
        self.selected_files.clear()
        mode = self.import_mode.get()
        if mode == "folder":
            self.entry_path.configure(placeholder_text="Selecione a pasta com os arquivos TXT...")
            self.lbl_folder_tip.configure(
                text="💡 Dica sobre pastas no Windows: Na janela de selecionar pasta, os arquivos de texto (.txt) não aparecem na listagem porque ela serve apenas para escolher pastas. "
                     "Não se preocupe: basta entrar na pasta desejada e clicar no botão 'Selecionar pasta' no rodapé. Se preferir ver e selecionar os arquivos individualmente, use a opção 'Arquivo(s) TXT' acima."
            )
        else:
            self.entry_path.configure(placeholder_text="Selecione um ou vários arquivos TXT...")
            self.lbl_folder_tip.configure(
                text="💡 Dica: Nesta opção, a janela do Windows exibirá todos os seus arquivos .txt. Você pode selecionar um ou vários (segurando Ctrl ou Shift, ou pressionando Ctrl+A para selecionar todos)."
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
                title="Selecione os arquivos TXT (Ctrl+A para selecionar todos)",
                filetypes=[("Arquivos de Texto", "*.txt"), ("Todos os Arquivos", "*.*")],
            )
            if file_paths:
                self.selected_files = list(file_paths)
                self.entry_path.delete(0, "end")
                if len(self.selected_files) == 1:
                    self.entry_path.insert(0, self.selected_files[0])
                else:
                    folder_name = os.path.basename(os.path.dirname(self.selected_files[0]))
                    self.entry_path.insert(0, f"{len(self.selected_files)} arquivos TXT selecionados (pasta: {folder_name})")

    def _log(self, text: str):
        self.txt_log.insert("end", text + "\n")
        self.txt_log.see("end")
        self.update_idletasks()

    def _start_import(self):
        path = self.entry_path.get().strip()
        if not path and not self.selected_files:
            show_message(self, "Aviso", "Por favor, selecione uma pasta ou arquivo(s) antes de iniciar.", kind="warning")
            return

        mode = self.import_mode.get()
        conflict = ConflictResolution(self.conflict_mode.get())

        if conflict == ConflictResolution.REPLACE:
            confirmed = ask_confirmation(
                self,
                "Confirmação de Substituição",
                "Você selecionou a opção de SUBSTITUIR anotações existentes.\n"
                "Caso uma data já exista no diário, seu conteúdo atual será sobrescrito.\n\n"
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
                files_to_process = self.selected_files if self.selected_files else ([path] if os.path.isfile(path) else [])
                if not files_to_process:
                    show_message(self, "Erro", "Nenhum arquivo TXT válido foi encontrado.", kind="danger")
                    return

                total_files = len(files_to_process)
                imported_count = 0
                skipped_count = 0
                error_count = 0

                self._log(f"Iniciando importação de {total_files} arquivo(s) TXT...")

                for idx, fpath in enumerate(files_to_process, start=1):
                    progress = idx / max(1, total_files)
                    self.progress_bar.set(progress)
                    filename = os.path.basename(fpath)
                    self._log(f"[{idx}/{total_files}] Processando: {filename}...")

                    res = self.import_service.import_file(
                        file_path=fpath,
                        user_id=self.current_user.id,
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

                self._log("\n" + "=" * 50)
                self._log("RESUMO FINAL DA IMPORTAÇÃO:")
                self._log(f"Total de arquivos analisados: {total_files}")
                self._log(f"Importados com sucesso: {imported_count}")
                self._log(f"Ignorados: {skipped_count}")
                self._log(f"Erros: {error_count}")
                self._log("=" * 50)

                self.lbl_summary.configure(
                    text=f"Concluído: {imported_count} importados | {skipped_count} ignorados | {error_count} erros.",
                    text_color=config.COLORS["success"] if error_count == 0 else config.COLORS["warning"],
                )

            else:  # mode == "folder"
                if not os.path.isdir(path):
                    show_message(self, "Erro", "A pasta especificada não existe.", kind="danger")
                    return

                self._log(f"Iniciando varredura na pasta: {path} ...")

                def progress_cb(current, total, filename):
                    progress = current / max(1, total)
                    self.progress_bar.set(progress)
                    self._log(f"[{current}/{total}] Processando: {filename}...")

                report = self.import_service.import_folder(
                    folder_path=path,
                    user_id=self.current_user.id,
                    default_conflict=conflict,
                    progress_callback=progress_cb,
                )

                self._log("\n" + "=" * 50)
                self._log("RESUMO FINAL DA IMPORTAÇÃO:")
                self._log(f"Total de arquivos analisados: {report['total']}")
                self._log(f"Importados com sucesso: {report['imported']}")
                self._log(f"Ignorados: {report['skipped']}")
                self._log(f"Erros / Não reconhecidos: {report['errors']}")
                self._log("=" * 50)

                for item in report["details"]:
                    status_icon = "✅" if item["status"] == "imported" else ("⚠️" if item["status"] == "skipped" else "❌")
                    self._log(f"{status_icon} {item['filename']} -> {item['message']}")

                self.lbl_summary.configure(
                    text=f"Concluído: {report['imported']} importados | {report['skipped']} ignorados | {report['errors']} erros.",
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
