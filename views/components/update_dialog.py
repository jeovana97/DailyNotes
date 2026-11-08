"""
Diálogo moderno para notificar e realizar a atualização de versão do DailyNotes.
Garante que o banco de dados do usuário (diario.db) permaneça 100% intacto.
"""

import os
import sys
import shutil
import threading
import subprocess
import tkinter as tk
from typing import Optional, Dict, Any
import customtkinter as ctk

import config
from services.update_service import UpdateService


class UpdateAvailableDialog(ctk.CTkToplevel):
    """
    Janela modal exibida quando uma nova versão é detectada no GitHub.
    Permite ao usuário ver as novidades, baixar a atualização e executar o instalador.
    """

    def __init__(self, parent, update_info: Dict[str, Any], update_service: UpdateService):
        super().__init__(parent)
        self.update_info = update_info
        self.update_service = update_service
        self.download_thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()

        self.title("Nova Versão Disponível - DailyNotes")
        self.geometry("520x440")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() // 2) - 260
        py = parent.winfo_y() + (parent.winfo_height() // 2) - 220
        self.geometry(f"+{max(50, px)}+{max(50, py)}")

        self._build_ui()

    def _build_ui(self):
        self.container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.container.pack(fill="both", expand=True, padx=16, pady=16)

        # 1. Cabeçalho
        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        lbl_badge = ctk.CTkLabel(
            header,
            text="🚀 ATUALIZAÇÃO DISPONÍVEL",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=config.COLORS["primary"],
            text_color="#FFFFFF",
            corner_radius=6,
            padx=10,
            pady=3,
        )
        lbl_badge.pack(side="left")

        curr_ver = self.update_info.get("current_version", config.APP_VERSION)
        new_ver = self.update_info.get("latest_version", "")
        lbl_vers = ctk.CTkLabel(
            header,
            text=f"v{curr_ver}  ➔  v{new_ver}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["success"],
        )
        lbl_vers.pack(side="right")

        # Título
        rel_name = self.update_info.get("release_name") or f"DailyNotes v{new_ver}"
        lbl_title = ctk.CTkLabel(
            self.container,
            text=f"Deseja atualizar para a versão {new_ver}?",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        lbl_title.pack(fill="x", padx=16, pady=(6, 4))

        # Aviso de segurança dos dados locais
        safety_card = ctk.CTkFrame(
            self.container,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        safety_card.pack(fill="x", padx=16, pady=(0, 10))

        lbl_safety = ctk.CTkLabel(
            safety_card,
            text="🔒 SEUS DADOS ESTÃO SEGUROS: Todas as suas anotações, notas, pastas, diários "
                 "e configurações ficam preservados no seu banco de dados local durante a atualização.",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=config.COLORS["success"],
            wraplength=450,
            justify="left",
        )
        lbl_safety.pack(padx=12, pady=8)

        # Notas da Versão (Changelog)
        lbl_notes_title = ctk.CTkLabel(
            self.container,
            text="Novidades desta versão:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        lbl_notes_title.pack(fill="x", padx=16, pady=(0, 4))

        self.txt_notes = ctk.CTkTextbox(
            self.container,
            height=120,
            corner_radius=8,
            fg_color=config.COLORS["sidebar"],
            text_color=config.COLORS["text_dark"],
            font=ctk.CTkFont(size=12),
            wrap="word",
        )
        self.txt_notes.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        notes_text = (self.update_info.get("release_notes") or "").strip()
        if not notes_text:
            notes_text = "Melhorias de desempenho, correções e novas funcionalidades."
        self.txt_notes.insert("1.0", notes_text)
        self.txt_notes.configure(state="disabled")

        # Barra de Progresso do Download
        self.progress_bar = ctk.CTkProgressBar(self.container, height=10)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 4))
        self.progress_bar.pack_forget()  # Só exibe ao baixar

        self.lbl_progress_status = ctk.CTkLabel(
            self.container,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_progress_status.pack(fill="x", padx=16, pady=(0, 6))
        self.lbl_progress_status.pack_forget()

        # Botões de Ação
        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))

        self.btn_update = ctk.CTkButton(
            btn_frame,
            text="🚀 Atualizar Agora",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["success"],
            hover_color=config.COLORS["success_hover"],
            text_color="#FFFFFF",
            command=self._start_update_download,
        )
        self.btn_update.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_browser = ctk.CTkButton(
            btn_frame,
            text="🌐 Ver no GitHub",
            height=38,
            width=130,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._open_github_release,
        )
        self.btn_browser.pack(side="left", padx=(0, 8))

        self.btn_later = ctk.CTkButton(
            btn_frame,
            text="Lembrar Depois",
            height=38,
            width=120,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._on_close,
        )
        self.btn_later.pack(side="right")

    def _open_github_release(self):
        url = self.update_info.get("html_url") or config.GITHUB_RELEASES_URL
        import webbrowser
        webbrowser.open(url)

    def _start_update_download(self):
        download_url = self.update_info.get("download_url")
        if not download_url:
            # Se não houver asset compilado direto na release, abre a página de download do GitHub
            self._open_github_release()
            self.destroy()
            return

        self.btn_update.configure(state="disabled", text="Baixando atualização...")
        self.btn_later.configure(state="disabled")
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 4))
        self.lbl_progress_status.pack(fill="x", padx=16, pady=(0, 6))
        self.lbl_progress_status.configure(text="Iniciando download do instalador...")

        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(download_url,),
            daemon=True,
        )
        self.download_thread.start()

    def _download_worker(self, download_url: str):
        asset_name = self.update_info.get("asset_name") or "DiarioAnotacoes_Setup.exe"
        temp_dir = os.path.join(config.DATA_DIR, "updates")
        dest_installer = os.path.join(temp_dir, asset_name)

        def _on_progress(pct: int, downloaded: int, total: int):
            mb_down = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.after(
                0,
                lambda p=pct, d=mb_down, t=mb_total: self._update_progress_ui(p, d, t),
            )

        ok = self.update_service.download_installer(
            download_url=download_url,
            dest_path=dest_installer,
            progress_callback=_on_progress,
            cancel_event=self.cancel_event,
        )

        if ok and os.path.isfile(dest_installer):
            self.after(0, lambda: self._launch_installer_and_exit(dest_installer))
        else:
            self.after(0, self._on_download_failed)

    def _update_progress_ui(self, pct: int, mb_down: float, mb_total: float):
        try:
            self.progress_bar.set(pct / 100.0)
            self.lbl_progress_status.configure(
                text=f"Baixando: {pct}% ({mb_down:.1f} MB de {mb_total:.1f} MB)"
            )
        except Exception:
            pass

    def _on_download_failed(self):
        try:
            self.lbl_progress_status.configure(
                text="❌ Falha no download. Tente baixar diretamente pelo GitHub.",
                text_color=config.COLORS["danger"],
            )
            self.btn_update.configure(
                state="normal",
                text="🌐 Baixar pelo Navegador",
                command=self._open_github_release,
            )
            self.btn_later.configure(state="normal", text="Fechar")
        except Exception:
            pass

    def _launch_installer_and_exit(self, installer_path: str):
        """
        Executa o instalador da nova versão e fecha a aplicação atual,
        permitindo a sobreposição limpa dos binários sem lock de arquivo.
        """
        try:
            self.lbl_progress_status.configure(
                text="✅ Download concluído! Iniciando o assistente de instalação...",
                text_color=config.COLORS["success"],
            )
            self.update_idletasks()

            # Dispara o instalador desvinculado
            subprocess.Popen([installer_path], close_fds=True)

            # Encerra o aplicativo atual para liberar arquivos em uso
            self.after(1000, lambda: sys.exit(0))
        except Exception as e:
            self.lbl_progress_status.configure(
                text=f"Erro ao abrir instalador: {e}",
                text_color=config.COLORS["danger"],
            )
            self.btn_later.configure(state="normal", text="Fechar")

    def _on_close(self):
        self.cancel_event.set()
        self.destroy()

