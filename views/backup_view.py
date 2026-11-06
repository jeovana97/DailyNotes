import os
import datetime
import subprocess
import tkinter as tk
from tkinter import filedialog
from typing import Optional, Callable
import customtkinter as ctk

import config
from models.user import User
from services.backup_service import BackupService
from services.diary_service import DiaryService
from services.spellcheck_service import WindowsSpellCheckService
from utils.date_utils import format_date_br, parse_date_input, get_today_iso
from utils.text_utils import normalize_text
from views.components.dialogs import show_message, ask_confirmation


class BackupView(ctk.CTkFrame):
    """
    Tela de Cópia de Segurança (Backup), Restauração, Exportação em Lote e
    Gerenciamento do Dicionário Personalizado do Corretor Ortográfico.
    - Backup consistente usando a API nativa do SQLite
    - Restauração com validação de esquema e cópia preventiva
    - Exportação em lote de anotações para arquivos TXT com padrão 'DD MM AAAA.txt'
    - Gerenciamento das palavras adicionadas ao Dicionário do Corretor Ortográfico (adicionar e remover)
    """

    def __init__(
        self,
        master,
        current_user: User,
        backup_service: BackupService,
        diary_service: DiaryService,
        spell_service: Optional[WindowsSpellCheckService] = None,
        on_data_restored: Optional[Callable[[], None]] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.backup_service = backup_service
        self.diary_service = diary_service
        self.spell_service = spell_service or WindowsSpellCheckService(db_path=self.backup_service.db_path)
        self.on_data_restored = on_data_restored

        self._build_ui()
        self._refresh_dictionary_list()
        self._load_auto_backup_ui()

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
            text="💾 Backup, Exportação e Dicionário Ortográfico",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(side="left", padx=15, pady=12)

        # 2. Container com rolagem para as seções
        self.scroll_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_container.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # =====================================================================
        # Card 1: Dicionário Personalizado do Corretor Ortográfico
        # =====================================================================
        self.card_dict = ctk.CTkFrame(
            self.scroll_container,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.card_dict.pack(fill="x", pady=(0, 15))

        dict_header = ctk.CTkFrame(self.card_dict, fg_color="transparent")
        dict_header.pack(fill="x", padx=20, pady=(15, 4))

        self.lbl_dict_title = ctk.CTkLabel(
            dict_header,
            text="🔤 Dicionário do Corretor Ortográfico",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["success"],
        )
        self.lbl_dict_title.pack(side="left")

        self.lbl_dict_count = ctk.CTkLabel(
            dict_header,
            text="0 palavras",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_dict_count.pack(side="right")

        self.lbl_dict_desc = ctk.CTkLabel(
            self.card_dict,
            text="Gerencie as palavras personalizadas adicionadas ao corretor ortográfico (siglas, termos técnicos, comandos SQL, nomes próprios). "
                 "Você pode cadastrar novas palavras ou remover palavras adicionadas anteriormente.",
            font=ctk.CTkFont(size=13),
            text_color=config.COLORS["text_muted"],
            wraplength=760,
            justify="left",
        )
        self.lbl_dict_desc.pack(anchor="w", padx=20, pady=(0, 12))

        # Barra de adição de nova palavra + filtro de pesquisa
        dict_controls = ctk.CTkFrame(self.card_dict, fg_color="transparent")
        dict_controls.pack(fill="x", padx=20, pady=(0, 10))

        self.entry_new_word = ctk.CTkEntry(
            dict_controls,
            width=260,
            height=36,
            placeholder_text="Digite uma nova palavra (ex: PLSQL, NFe)...",
            corner_radius=8,
            font=ctk.CTkFont(size=13),
        )
        self.entry_new_word.pack(side="left", padx=(0, 8))
        self.entry_new_word.bind("<Return>", lambda e: self._handle_add_dictionary_word())

        self.btn_add_word = ctk.CTkButton(
            dict_controls,
            text="➕ Adicionar ao Dicionário",
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["success"],
            hover_color=config.COLORS["success_hover"],
            text_color="#FFFFFF",
            command=self._handle_add_dictionary_word,
        )
        self.btn_add_word.pack(side="left", padx=(0, 16))

        self.entry_filter_word = ctk.CTkEntry(
            dict_controls,
            width=220,
            height=36,
            placeholder_text="🔍 Filtrar palavra cadastrada...",
            corner_radius=8,
            font=ctk.CTkFont(size=12),
        )
        self.entry_filter_word.pack(side="right")
        self.entry_filter_word.bind("<KeyRelease>", lambda e: self._refresh_dictionary_list())

        # Lista rolável de palavras do dicionário
        self.dict_list_frame = ctk.CTkScrollableFrame(
            self.card_dict,
            height=170,
            corner_radius=8,
            fg_color=config.COLORS["sidebar"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.dict_list_frame.pack(fill="x", padx=20, pady=(0, 18))

        # =====================================================================
        # Card 2: Criar Backup do Banco de Dados (Manual e Automático)
        # =====================================================================
        self.card_backup = ctk.CTkFrame(
            self.scroll_container,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.card_backup.pack(fill="x", pady=(0, 15))

        self.lbl_backup_title = ctk.CTkLabel(
            self.card_backup,
            text="🛡️ Cópia de Segurança do Banco de Dados (Backup)",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["primary"],
        )
        self.lbl_backup_title.pack(anchor="w", padx=20, pady=(15, 6))

        self.lbl_backup_desc = ctk.CTkLabel(
            self.card_backup,
            text="Gera uma cópia completa e consistente do banco de dados SQLite (incluindo usuários, notas, pastas, diários e dicionário personalizado). "
                 "Utiliza a API nativa de backup do SQLite para garantir consistência mesmo durante gravações.",
            font=ctk.CTkFont(size=13),
            text_color=config.COLORS["text_muted"],
            wraplength=760,
            justify="left",
        )
        self.lbl_backup_desc.pack(anchor="w", padx=20, pady=(0, 12))

        self.btn_create_backup = ctk.CTkButton(
            self.card_backup,
            text="💾 Gerar Cópia de Segurança (.db)",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._handle_create_backup,
        )
        self.btn_create_backup.pack(anchor="w", padx=20, pady=(0, 14))

        # Sub-painel de Configuração de Backup Automático
        self.auto_backup_box = ctk.CTkFrame(
            self.card_backup,
            corner_radius=10,
            fg_color=config.COLORS["sidebar"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.auto_backup_box.pack(fill="x", padx=20, pady=(0, 18))

        auto_header = ctk.CTkFrame(self.auto_backup_box, fg_color="transparent")
        auto_header.pack(fill="x", padx=16, pady=(12, 8))

        self.lbl_auto_title = ctk.CTkLabel(
            auto_header,
            text="⏰ Configuração de Backup Automático",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_auto_title.pack(side="left")

        self.auto_enabled_var = tk.BooleanVar(value=False)
        self.switch_auto_backup = ctk.CTkSwitch(
            auto_header,
            text="Backup Automático Ativo",
            variable=self.auto_enabled_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
            progress_color=config.COLORS["success"],
        )
        self.switch_auto_backup.pack(side="right")

        # Linha 1: Local para salvar o arquivo
        dir_row = ctk.CTkFrame(self.auto_backup_box, fg_color="transparent")
        dir_row.pack(fill="x", padx=16, pady=(2, 8))

        lbl_local = ctk.CTkLabel(
            dir_row,
            text="📁 Local para salvar o arquivo:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
            width=205,
            anchor="w",
        )
        lbl_local.pack(side="left")

        self.entry_auto_dir = ctk.CTkEntry(
            dir_row,
            height=34,
            placeholder_text="Selecione a pasta onde os backups automáticos serão salvos...",
            corner_radius=8,
            font=ctk.CTkFont(size=12),
        )
        self.entry_auto_dir.pack(side="left", fill="x", expand=True, padx=(6, 8))

        self.btn_browse_auto_dir = ctk.CTkButton(
            dir_row,
            text="📂 Escolher Local...",
            width=140,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._handle_browse_auto_backup_dir,
        )
        self.btn_browse_auto_dir.pack(side="left", padx=(0, 6))

        self.btn_open_auto_dir = ctk.CTkButton(
            dir_row,
            text="🗂️ Abrir Pasta",
            width=105,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._handle_open_auto_backup_dir,
        )
        self.btn_open_auto_dir.pack(side="left")

        # Linha 2: Data e Horário do Backup
        dt_row = ctk.CTkFrame(self.auto_backup_box, fg_color="transparent")
        dt_row.pack(fill="x", padx=16, pady=(2, 10))

        lbl_date = ctk.CTkLabel(
            dt_row,
            text="📅 Data do Backup:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_date.pack(side="left", padx=(0, 6))

        self.entry_auto_date = ctk.CTkEntry(
            dt_row,
            width=115,
            height=34,
            placeholder_text="DD/MM/AAAA",
            corner_radius=8,
            font=ctk.CTkFont(size=13),
        )
        self.entry_auto_date.pack(side="left", padx=(0, 6))

        self.btn_today_auto = ctk.CTkButton(
            dt_row,
            text="Hoje",
            width=58,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._set_auto_date_today,
        )
        self.btn_today_auto.pack(side="left", padx=(0, 18))

        lbl_time = ctk.CTkLabel(
            dt_row,
            text="🕒 Horário do Backup (HH:MM):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        lbl_time.pack(side="left", padx=(0, 6))

        self.entry_auto_time = ctk.CTkEntry(
            dt_row,
            width=85,
            height=34,
            placeholder_text="18:00",
            corner_radius=8,
            font=ctk.CTkFont(size=13),
        )
        self.entry_auto_time.pack(side="left", padx=(0, 18))

        self.repeat_daily_var = tk.BooleanVar(value=True)
        self.chk_repeat_daily = ctk.CTkCheckBox(
            dt_row,
            text="Repetir diariamente neste horário",
            variable=self.repeat_daily_var,
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_dark"],
            corner_radius=6,
        )
        self.chk_repeat_daily.pack(side="left")

        # Linha 3: Botão Salvar Configuração + Status do Agendamento
        action_row = ctk.CTkFrame(self.auto_backup_box, fg_color="transparent")
        action_row.pack(fill="x", padx=16, pady=(2, 14))

        self.btn_save_auto_cfg = ctk.CTkButton(
            action_row,
            text="💾 Salvar Configuração de Backup Automático",
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["success"],
            hover_color=config.COLORS["success_hover"],
            text_color="#FFFFFF",
            command=self._handle_save_auto_backup_settings,
        )
        self.btn_save_auto_cfg.pack(side="left", padx=(0, 14))

        self.lbl_auto_status = ctk.CTkLabel(
            action_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
            justify="left",
            anchor="w",
        )
        self.lbl_auto_status.pack(side="left", fill="x", expand=True)

        # =====================================================================
        # Card 3: Restauração do Banco de Dados
        # =====================================================================
        self.card_restore = ctk.CTkFrame(
            self.scroll_container,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.card_restore.pack(fill="x", pady=(0, 15))

        self.lbl_restore_title = ctk.CTkLabel(
            self.card_restore,
            text="🔄 Restaurar Banco de Dados a partir de um Backup",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["warning"],
        )
        self.lbl_restore_title.pack(anchor="w", padx=20, pady=(15, 6))

        self.lbl_restore_desc = ctk.CTkLabel(
            self.card_restore,
            text="Permite recuperar seus dados a partir de um arquivo de backup previamente gerado (.db ou .bak).\n"
                 "⚠️ ATENÇÃO: A restauração substituirá os dados atuais da aplicação. O sistema criará automaticamente uma cópia preventiva antes de aplicar o backup.",
            font=ctk.CTkFont(size=13),
            text_color=config.COLORS["text_muted"],
            wraplength=700,
            justify="left",
        )
        self.lbl_restore_desc.pack(anchor="w", padx=20, pady=(0, 15))

        self.btn_restore = ctk.CTkButton(
            self.card_restore,
            text="🔄 Selecionar Arquivo e Restaurar",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["warning"],
            text_color=config.COLORS["button_text"],
            command=self._handle_restore_backup,
        )
        self.btn_restore.pack(anchor="w", padx=20, pady=(0, 20))

        # =====================================================================
        # Card 4: Exportação de Anotações em Lote para TXT
        # =====================================================================
        self.card_export = ctk.CTkFrame(
            self.scroll_container,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.card_export.pack(fill="x", pady=(0, 15))

        self.lbl_export_title = ctk.CTkLabel(
            self.card_export,
            text="📂 Exportar Anotações em Lote para Arquivos TXT",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["secondary"],
        )
        self.lbl_export_title.pack(anchor="w", padx=20, pady=(15, 6))

        self.lbl_export_desc = ctk.CTkLabel(
            self.card_export,
            text="Exporta todas as suas anotações para uma pasta do seu computador. "
                 "Cada diário será salvo em um arquivo TXT individual com o padrão 'DD MM AAAA.txt' (ex: '27 10 2026.txt').",
            font=ctk.CTkFont(size=13),
            text_color=config.COLORS["text_muted"],
            wraplength=700,
            justify="left",
        )
        self.lbl_export_desc.pack(anchor="w", padx=20, pady=(0, 15))

        self.btn_export_all = ctk.CTkButton(
            self.card_export,
            text="📂 Exportar Minhas Anotações para Pasta...",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["secondary"],
            hover_color=config.COLORS["secondary_hover"],
            text_color="#FFFFFF",
            command=self._handle_export_all_txt,
        )
        self.btn_export_all.pack(anchor="w", padx=20, pady=(0, 20))

    # =========================================================================
    # Métodos do Dicionário Personalizado
    # =========================================================================

    def _refresh_dictionary_list(self):
        """Atualiza a listagem visual das palavras adicionadas ao dicionário."""
        for widget in self.dict_list_frame.winfo_children():
            widget.destroy()

        all_words = self.spell_service.list_custom_words()
        total = len(all_words)
        self.lbl_dict_count.configure(
            text=f"{total} {'palavra cadastrada' if total == 1 else 'palavras cadastradas'}"
        )

        filter_query = normalize_text(self.entry_filter_word.get().strip())
        if filter_query:
            filtered_words = [w for w in all_words if filter_query in normalize_text(w)]
        else:
            filtered_words = all_words

        if not filtered_words:
            empty_msg = (
                "Nenhuma palavra encontrada para o filtro informado."
                if filter_query
                else "Nenhuma palavra personalizada adicionada ao dicionário ainda.\n"
                     "Adicione palavras pelo campo acima ou clicando com o botão direito sobre uma palavra no editor."
            )
            lbl_empty = ctk.CTkLabel(
                self.dict_list_frame,
                text=empty_msg,
                font=ctk.CTkFont(size=12),
                text_color=config.COLORS["text_muted"],
                justify="center",
            )
            lbl_empty.pack(fill="x", padx=15, pady=25)
            return

        for word in filtered_words:
            row = ctk.CTkFrame(
                self.dict_list_frame,
                corner_radius=8,
                fg_color=config.COLORS["card_dark"],
                border_width=1,
                border_color=config.COLORS["border_dark"],
            )
            row.pack(fill="x", padx=6, pady=3)

            lbl_word = ctk.CTkLabel(
                row,
                text=f"🔤  {word}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=config.COLORS["text_dark"],
                anchor="w",
            )
            lbl_word.pack(side="left", padx=12, pady=6)

            btn_remove = ctk.CTkButton(
                row,
                text="🗑️ Remover",
                width=95,
                height=28,
                corner_radius=6,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=config.COLORS["card_dark_alt"],
                hover_color=config.COLORS["danger"],
                text_color=config.COLORS["button_text"],
                command=lambda w=word: self._handle_remove_dictionary_word(w),
            )
            btn_remove.pack(side="right", padx=10, pady=5)

    def _handle_add_dictionary_word(self):
        raw_input = self.entry_new_word.get().strip()
        if not raw_input:
            show_message(self, "Aviso", "Digite uma palavra para adicionar ao dicionário.", kind="warning")
            self.entry_new_word.focus_set()
            return

        # Permite adicionar uma palavra (ou múltiplas palavras separadas por espaço/vírgula)
        tokens = [t.strip() for t in raw_input.replace(",", " ").split() if t.strip()]
        if not tokens:
            return

        added_count = 0
        for token in tokens:
            if self.spell_service.add_to_dictionary(token):
                added_count += 1

        self.entry_new_word.delete(0, "end")
        self._refresh_dictionary_list()

        if added_count == 1:
            show_message(
                self,
                "Palavra Adicionada",
                f"A palavra '{tokens[0]}' foi adicionada ao dicionário do corretor ortográfico.",
                kind="success",
            )
        elif added_count > 1:
            show_message(
                self,
                "Palavras Adicionadas",
                f"{added_count} palavras foram adicionadas ao dicionário do corretor ortográfico.",
                kind="success",
            )

    def _handle_remove_dictionary_word(self, word: str):
        confirmed = ask_confirmation(
            self,
            "Remover do Dicionário",
            f"Deseja remover a palavra '{word}' do dicionário personalizado do corretor ortográfico?",
            kind="warning",
        )
        if not confirmed:
            return

        self.spell_service.remove_from_dictionary(word)
        self._refresh_dictionary_list()

    # =========================================================================
    # Métodos de Backup, Restauração e Exportação
    # =========================================================================

    def _load_auto_backup_ui(self):
        """Carrega nos campos da tela as configurações salvas de backup automático."""
        settings = self.backup_service.get_auto_backup_settings()
        self.auto_enabled_var.set(bool(settings.get("enabled", False)))

        self.entry_auto_dir.delete(0, "end")
        self.entry_auto_dir.insert(0, settings.get("target_dir", ""))

        sched_date_iso = settings.get("schedule_date") or get_today_iso()
        self.entry_auto_date.delete(0, "end")
        self.entry_auto_date.insert(0, format_date_br(sched_date_iso))

        self.entry_auto_time.delete(0, "end")
        self.entry_auto_time.insert(0, settings.get("schedule_time", "18:00"))

        self.repeat_daily_var.set(bool(settings.get("repeat_daily", True)))
        self.refresh_auto_backup_status()

    def refresh_auto_backup_status(self):
        """Atualiza o texto informativo de status do agendamento e último backup automático."""
        settings = self.backup_service.get_auto_backup_settings()
        enabled = bool(settings.get("enabled"))
        date_br = format_date_br(settings.get("schedule_date") or get_today_iso())
        time_str = settings.get("schedule_time") or "18:00"
        repeat_txt = "Diariamente" if settings.get("repeat_daily") else f"Em {date_br}"
        last_run = settings.get("last_run_at") or ""
        last_file = settings.get("last_backup_file") or ""

        if enabled:
            status_line = f"🟢 Agendado: {repeat_txt} às {time_str} (Início/Data: {date_br})"
            color = config.COLORS["success"]
        else:
            status_line = f"⚪ Backup automático desativado (Configurado: {date_br} às {time_str})"
            color = config.COLORS["text_muted"]

        if last_run:
            fname = os.path.basename(last_file) if last_file else "backup.db"
            status_line += f"\n📄 Último gerado em: {last_run} ({fname})"

        self.lbl_auto_status.configure(text=status_line, text_color=color)

    def _set_auto_date_today(self):
        self.entry_auto_date.delete(0, "end")
        self.entry_auto_date.insert(0, format_date_br(get_today_iso()))

    def _handle_browse_auto_backup_dir(self):
        current_dir = self.entry_auto_dir.get().strip()
        initial_dir = current_dir if (current_dir and os.path.isdir(current_dir)) else config.BASE_DIR
        chosen = filedialog.askdirectory(
            parent=self,
            title="Selecione a pasta para salvar os Backups Automáticos",
            initialdir=initial_dir,
        )
        if chosen:
            self.entry_auto_dir.delete(0, "end")
            self.entry_auto_dir.insert(0, os.path.normpath(chosen))

    def _handle_open_auto_backup_dir(self):
        target_dir = self.entry_auto_dir.get().strip()
        if not target_dir:
            show_message(self, "Aviso", "Nenhum local de backup configurado.", kind="warning")
            return
        try:
            os.makedirs(target_dir, exist_ok=True)
            if os.name == "nt":
                os.startfile(target_dir)
            else:
                subprocess.Popen(["xdg-open", target_dir])
        except Exception as e:
            show_message(self, "Erro", f"Não foi possível abrir a pasta:\n{e}", kind="danger")

    def _handle_save_auto_backup_settings(self):
        enabled = bool(self.auto_enabled_var.get())
        target_dir = self.entry_auto_dir.get().strip()
        raw_date = self.entry_auto_date.get().strip()
        raw_time = self.entry_auto_time.get().strip()
        repeat_daily = bool(self.repeat_daily_var.get())

        date_iso = parse_date_input(raw_date) if raw_date else get_today_iso()
        if not date_iso:
            show_message(
                self,
                "Data Inválida",
                "Informe a Data do Backup no formato DD/MM/AAAA (ex: 05/11/2026).",
                kind="warning",
            )
            self.entry_auto_date.focus_set()
            return

        ok, msg = self.backup_service.save_auto_backup_settings(
            enabled=enabled,
            target_dir=target_dir,
            schedule_date_iso=date_iso,
            schedule_time=raw_time,
            repeat_daily=repeat_daily,
        )
        if not ok:
            show_message(self, "Aviso", msg, kind="warning")
            return

        # Atualiza os campos normalizados e verifica se já deve executar agora
        self._load_auto_backup_ui()
        ran, generated_file = self.backup_service.check_and_run_due_auto_backup()
        self.refresh_auto_backup_status()

        if ran and generated_file:
            show_message(
                self,
                "Configuração Salva e Backup Executado",
                f"{msg}\n\nComo o horário configurado já foi atingido hoje, um backup automático foi gerado imediatamente em:\n{generated_file}",
                kind="success",
            )
        else:
            show_message(self, "Configuração Salva", msg, kind="success")

    def _handle_create_backup(self):
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested_name = f"backup_diario_{now_str}.db"

        dest_file = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar Backup do Diário",
            initialfile=suggested_name,
            defaultextension=".db",
            filetypes=[("Banco de Dados SQLite", "*.db"), ("Todos os Arquivos", "*.*")],
        )

        if dest_file:
            ok, msg = self.backup_service.create_database_backup(dest_file)
            if ok:
                show_message(self, "Backup Concluído", msg, kind="success")
            else:
                show_message(self, "Erro no Backup", msg, kind="danger")

    def _handle_restore_backup(self):
        backup_file = filedialog.askopenfilename(
            parent=self,
            title="Selecione o arquivo de Backup para Restaurar",
            filetypes=[("Banco de Dados SQLite", "*.db;*.bak"), ("Todos os Arquivos", "*.*")],
        )

        if not backup_file:
            return

        confirmed = ask_confirmation(
            self,
            "Confirmação de Restauração",
            f"Você selecionou o arquivo:\n{os.path.basename(backup_file)}\n\n"
            "⚠️ Todos os dados atuais serão substituídos pelo conteúdo deste backup.\n"
            "Deseja realmente prosseguir com a restauração?",
            kind="danger",
        )

        if not confirmed:
            return

        ok, msg = self.backup_service.restore_database_backup(backup_file)
        if ok:
            self.spell_service.reload_custom_dictionary()
            show_message(self, "Restauração Concluída", msg, kind="success")
            if self.on_data_restored:
                self.on_data_restored()
        else:
            show_message(self, "Erro na Restauração", msg, kind="danger")

    def _handle_export_all_txt(self):
        target_dir = filedialog.askdirectory(
            parent=self,
            title="Selecione a pasta de destino para exportar as anotações",
        )
        if not target_dir:
            return

        # Para exportar todas, faz busca completa
        from services.search_service import SearchService
        search_svc = SearchService(db_path=self.backup_service.db_path)
        all_results = search_svc.search_diaries(
            requester=self.current_user,
            query="",
            target_user_id=self.current_user.id,
            limit=10000,
        )

        from models.diary import DiaryEntry
        all_entries = [
            DiaryEntry(
                id=r["id"],
                user_id=r["user_id"],
                entry_date=r["entry_date"],
                content=r["content"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in all_results
        ]

        if not all_entries:
            show_message(self, "Aviso", "Você não possui nenhuma anotação cadastrada para exportar.", kind="warning")
            return

        exported, errors, msg = self.backup_service.export_entries_to_folder(all_entries, target_dir)
        show_message(self, "Exportação Concluída", f"{msg}\nPasta: {target_dir}", kind="success")
