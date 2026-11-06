import os
import tkinter as tk
from typing import Optional
import customtkinter as ctk
from PIL import Image

import config
from models.user import User
from database.connection import get_connection
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService
from services.note_service import NoteService
from services.search_service import SearchService
from services.import_service import ImportService
from services.backup_service import BackupService
from services.spellcheck_service import WindowsSpellCheckService

from views.login_view import LoginView
from views.diary_view import DiaryView
from views.notes_view import NotesView
from views.search_view import SearchView
from views.history_view import HistoryView
from views.import_view import ImportView
from views.backup_view import BackupView
from views.users_view import UsersView
from views.components.dialogs import show_message, ask_confirmation


class SelfPasswordChangeDialog(ctk.CTkToplevel):
    """Modal para o usuário conectado alterar sua própria senha."""
    def __init__(self, parent, user_id: int, auth_service: AuthenticationService):
        super().__init__(parent)
        self.title("Alterar Minha Senha")
        self.geometry("380x280")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.user_id = user_id
        self.auth_service = auth_service

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() // 2) - 190
        py = parent.winfo_y() + (parent.winfo_height() // 2) - 140
        self.geometry(f"+{max(50, px)}+{max(50, py)}")

        self.container = ctk.CTkFrame(self, corner_radius=12, fg_color=config.COLORS["card_dark"])
        self.container.pack(fill="both", expand=True, padx=15, pady=15)

        self.lbl_title = ctk.CTkLabel(
            self.container,
            text="🔑 Alteração de Senha",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.lbl_title.pack(pady=(10, 12))

        self.entry_curr = ctk.CTkEntry(
            self.container, height=36, placeholder_text="Senha Atual", show="•", corner_radius=6
        )
        self.entry_curr.pack(fill="x", padx=20, pady=(0, 8))

        self.entry_new = ctk.CTkEntry(
            self.container, height=36, placeholder_text="Nova Senha (mínimo 4 caracteres)", show="•", corner_radius=6
        )
        self.entry_new.pack(fill="x", padx=20, pady=(0, 8))

        self.entry_confirm = ctk.CTkEntry(
            self.container, height=36, placeholder_text="Confirme a Nova Senha", show="•", corner_radius=6
        )
        self.entry_confirm.pack(fill="x", padx=20, pady=(0, 15))

        self.btn_save = ctk.CTkButton(
            self.container,
            text="Salvar Nova Senha",
            height=36,
            corner_radius=8,
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            command=self._on_save,
        )
        self.btn_save.pack(fill="x", padx=20, pady=(0, 10))

    def _on_save(self):
        curr = self.entry_curr.get()
        new_p = self.entry_new.get()
        conf = self.entry_confirm.get()

        if not curr:
            show_message(self, "Aviso", "Informe sua senha atual.", kind="warning")
            return

        if new_p != conf:
            show_message(self, "Aviso", "A nova senha e a confirmação não coincidem.", kind="warning")
            return

        ok, msg = self.auth_service.update_password(self.user_id, curr, new_p)
        if ok:
            show_message(self, "Sucesso", msg, kind="success")
            self.destroy()
        else:
            show_message(self, "Erro", msg, kind="danger")


class MainWindow(ctk.CTk):
    """
    Janela principal da aplicação desktop Diário de Anotações Inteligente.
    Gerencia a navegação entre telas, autenticação, tema e proteção contra perda de dados.
    """

    def __init__(self, db_path: Optional[str] = None):
        super().__init__()

        self.db_path = db_path or config.DB_PATH
        self.auth_service = AuthenticationService(db_path=self.db_path)

        initial_theme = self.auth_service.get_last_theme_preference() or config.APPEARANCE_MODE
        ctk.set_appearance_mode(initial_theme)
        ctk.set_default_color_theme(config.DEFAULT_COLOR_THEME)

        self.title(config.APP_NAME)
        self.minsize(1050, 680)
        self.geometry("1240x780")

        self._icon_photo = None
        self._brand_ctk_image = None
        self._apply_window_icon()
        # Reaplica após 250ms pois o CustomTkinter redefine o ícone padrão da janela aos 200ms no Windows
        self.after(250, self._apply_window_icon)

        # Inicializa Serviços
        self.diary_service = DiaryService(db_path=self.db_path)
        self.note_service = NoteService(db_path=self.db_path)
        self.search_service = SearchService(db_path=self.db_path)
        self.import_service = ImportService(diary_service=self.diary_service, db_path=self.db_path)
        self.backup_service = BackupService(db_path=self.db_path)
        self.spell_service = WindowsSpellCheckService(db_path=self.db_path)

        self.current_user: Optional[User] = None
        self.active_view = None
        self.nav_buttons = {}
        self._auto_backup_timer_id = None

        # Intercepta evento de fechar janela
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self._show_login_screen()
        self._schedule_auto_backup_check(delay_ms=4000)

    def _apply_window_icon(self):
        """Aplica o ícone personalizado do aplicativo na barra de título e barra de tarefas do Windows."""
        try:
            if not self.winfo_exists():
                return
            if os.path.isfile(config.ICON_ICO_PATH):
                self.iconbitmap(config.ICON_ICO_PATH)
                self.wm_iconbitmap(config.ICON_ICO_PATH)
            if os.path.isfile(config.ICON_PNG_PATH):
                self._icon_photo = tk.PhotoImage(file=config.ICON_PNG_PATH)
                self.wm_iconphoto(True, self._icon_photo)
        except Exception:
            pass

    def _show_login_screen(self):
        """Exibe a tela de login ou configuração inicial."""
        self.current_user = None

        # Limpa todos os widgets
        for widget in self.winfo_children():
            widget.destroy()

        self.login_view = LoginView(
            self,
            auth_service=self.auth_service,
            on_login_success=self._on_login_success,
        )
        self.login_view.pack(fill="both", expand=True)

    def _on_login_success(self, user: User):
        """Invocado após autenticação com sucesso."""
        self.current_user = user
        user_theme = "light" if str(getattr(user, "theme_preference", "dark")).lower() == "light" else "dark"
        ctk.set_appearance_mode(user_theme)
        self._build_main_layout()
        self.navigate_to("diary")

    def _build_main_layout(self):
        """Monta a barra lateral de navegação e o container de conteúdo principal."""
        for widget in self.winfo_children():
            widget.destroy()

        # Layout com grid de 2 colunas: Menu Lateral (col 0) | Conteúdo (col 1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Barra Lateral (Sidebar)
        self.sidebar = ctk.CTkFrame(
            self,
            width=240,
            corner_radius=0,
            fg_color=config.COLORS["sidebar"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Cabeçalho da Marca
        self.brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.brand_frame.pack(fill="x", padx=16, pady=(20, 15))

        if os.path.isfile(config.ICON_PNG_PATH):
            try:
                pil_logo = Image.open(config.ICON_PNG_PATH)
                self._brand_ctk_image = ctk.CTkImage(
                    light_image=pil_logo,
                    dark_image=pil_logo,
                    size=(34, 34),
                )
            except Exception:
                self._brand_ctk_image = None

        if self._brand_ctk_image is not None:
            self.lbl_logo = ctk.CTkLabel(
                self.brand_frame,
                text="",
                image=self._brand_ctk_image,
            )
        else:
            self.lbl_logo = ctk.CTkLabel(
                self.brand_frame,
                text="📓",
                font=ctk.CTkFont(size=28),
            )
        self.lbl_logo.pack(side="left", padx=(0, 10))

        self.lbl_app = ctk.CTkLabel(
            self.brand_frame,
            text="Diário de\nAnotações",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["text_dark"],
            justify="left",
        )
        self.lbl_app.pack(side="left")

        # Card do Usuário Logado
        self.user_card = ctk.CTkFrame(
            self.sidebar,
            corner_radius=10,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.user_card.pack(fill="x", padx=14, pady=(0, 18))

        lbl_user_name = ctk.CTkLabel(
            self.user_card,
            text=f"👤 {self.current_user.full_name}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        lbl_user_name.pack(fill="x", padx=12, pady=(10, 2))

        role_label = "🛡️ Administrador" if self.current_user.is_admin else "👤 Usuário"
        lbl_role = ctk.CTkLabel(
            self.user_card,
            text=role_label,
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        lbl_role.pack(fill="x", padx=12, pady=(0, 8))

        # Botões de perfil (Trocar senha e Sair)
        user_actions = ctk.CTkFrame(self.user_card, fg_color="transparent")
        user_actions.pack(fill="x", padx=10, pady=(0, 10))

        btn_pass = ctk.CTkButton(
            user_actions,
            text="🔑 Senha",
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._open_change_password_dialog,
        )
        btn_pass.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_logout = ctk.CTkButton(
            user_actions,
            text="🚪 Sair",
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["danger"],
            text_color=config.COLORS["button_text"],
            command=self._handle_logout,
        )
        btn_logout.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Itens do Menu de Navegação
        self.nav_menu_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.nav_menu_frame.pack(fill="both", expand=True, padx=14, pady=0)

        nav_items = [
            ("diary", "📝 Diário do Dia"),
            ("notes", "🗂️ Notas & Pastas"),
            ("search", "🔍 Pesquisa Avançada"),
            ("history", "📅 Histórico & Calendário"),
            ("import", "📥 Importar TXT"),
            ("backup", "💾 Exportar & Backup"),
        ]

        if self.current_user.is_admin:
            nav_items.append(("users", "👥 Gerenciar Usuários"))

        self.nav_buttons.clear()
        for key, label in nav_items:
            btn = ctk.CTkButton(
                self.nav_menu_frame,
                text=label,
                height=42,
                corner_radius=8,
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="transparent",
                text_color=config.COLORS["text_dark"],
                hover_color=config.COLORS["card_dark_alt"],
                command=lambda k=key: self.navigate_to(k),
            )
            btn.pack(fill="x", pady=3)
            self.nav_buttons[key] = btn

        # Rodapé da Barra Lateral: Alternador de Tema e Versão
        self.sidebar_footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.sidebar_footer.pack(side="bottom", fill="x", padx=14, pady=15)

        is_light_theme = (str(getattr(self.current_user, "theme_preference", "dark")).lower() == "light")
        self.switch_theme = ctk.CTkSwitch(
            self.sidebar_footer,
            text="Modo Claro" if is_light_theme else "Modo Escuro",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_dark"],
            command=self._toggle_theme,
        )
        if is_light_theme:
            self.switch_theme.deselect()
        else:
            self.switch_theme.select()
        self.switch_theme.pack(anchor="w", pady=(0, 6))

        lbl_ver = ctk.CTkLabel(
            self.sidebar_footer,
            text=f"v{config.APP_VERSION} • Windows",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
        )
        lbl_ver.pack(anchor="w")

        # 2. Container de Conteúdo Principal
        self.content_frame = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color="transparent",
        )
        self.content_frame.grid(row=0, column=1, sticky="nsew")

    def _toggle_theme(self):
        if self.switch_theme.get():
            new_theme = "dark"
            ctk.set_appearance_mode("dark")
            self.switch_theme.configure(text="Modo Escuro")
        else:
            new_theme = "light"
            ctk.set_appearance_mode("light")
            self.switch_theme.configure(text="Modo Claro")

        if self.current_user:
            self.current_user.theme_preference = new_theme
            self.auth_service.update_theme_preference(self.current_user.id, new_theme)

    def _open_change_password_dialog(self):
        SelfPasswordChangeDialog(self, self.current_user.id, self.auth_service)

    def _handle_logout(self):
        """Verifica alterações não salvas antes de efetuar logout."""
        if hasattr(self.active_view, "confirm_discard_if_unsaved"):
            if not self.active_view.confirm_discard_if_unsaved():
                return

        confirmed = ask_confirmation(
            self, "Sair da Conta", "Deseja realmente sair da sua conta e bloquear o acesso?", kind="warning"
        )
        if confirmed:
            self._show_login_screen()

    def _on_close_window(self):
        """Verifica alterações não salvas antes de fechar o aplicativo."""
        if hasattr(self.active_view, "confirm_discard_if_unsaved"):
            if not self.active_view.confirm_discard_if_unsaved():
                return
        if self._auto_backup_timer_id is not None:
            try:
                self.after_cancel(self._auto_backup_timer_id)
            except Exception:
                pass
            self._auto_backup_timer_id = None
        self.destroy()

    def _schedule_auto_backup_check(self, delay_ms: int = 15000):
        """Agenda verificação periódica do backup automático agendado."""
        try:
            if not self.winfo_exists():
                return
            if self._auto_backup_timer_id is not None:
                try:
                    self.after_cancel(self._auto_backup_timer_id)
                except Exception:
                    pass
            self._auto_backup_timer_id = self.after(delay_ms, self._run_auto_backup_check)
        except Exception:
            pass

    def _run_auto_backup_check(self):
        """Verifica se há backup automático agendado para o horário atual e o executa."""
        self._auto_backup_timer_id = None
        try:
            if not self.winfo_exists():
                return
            ran, _ = self.backup_service.check_and_run_due_auto_backup()
            if ran and hasattr(self.active_view, "refresh_auto_backup_status"):
                self.active_view.refresh_auto_backup_status()
        except Exception:
            pass
        finally:
            self._schedule_auto_backup_check(delay_ms=15000)

    def navigate_to(self, view_name: str, **kwargs):
        """Troca a visualização principal garantindo verificação de dados pendentes."""
        if hasattr(self.active_view, "confirm_discard_if_unsaved"):
            if not self.active_view.confirm_discard_if_unsaved():
                return

        # Atualiza destaques nos botões da barra lateral
        for key, btn in self.nav_buttons.items():
            if key == view_name:
                btn.configure(
                    fg_color=config.COLORS["primary"],
                    hover_color=config.COLORS["primary_hover"],
                    text_color="#FFFFFF",
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    hover_color=config.COLORS["card_dark_alt"],
                    text_color=config.COLORS["text_dark"],
                )

        # Destrói a tela ativa anterior
        if self.active_view:
            self.active_view.destroy()
            self.active_view = None

        # Instancia a nova tela
        if view_name == "diary":
            target_date = kwargs.get("date_iso")
            target_user_id = kwargs.get("user_id")

            self.active_view = DiaryView(
                self.content_frame,
                current_user=self.current_user,
                diary_service=self.diary_service,
                auth_service=self.auth_service,
                backup_service=self.backup_service,
                spell_service=self.spell_service,
                on_navigate_to_search=lambda: self.navigate_to("search"),
                on_navigate_to_history=lambda d: self.navigate_to("history", initial_date=d),
                on_navigate_to_import=lambda: self.navigate_to("import"),
            )
            self.active_view.pack(fill="both", expand=True)

            if target_user_id and self.current_user.can_view_other_diaries:
                all_u = self.auth_service.list_users(self.current_user)
                for u in all_u:
                    if u.id == target_user_id:
                        self.active_view.target_user = u
                        break

            if target_date:
                self.active_view.set_date(target_date)

        elif view_name == "notes":
            self.active_view = NotesView(
                self.content_frame,
                current_user=self.current_user,
                note_service=self.note_service,
                spell_service=self.spell_service,
            )
            self.active_view.pack(fill="both", expand=True)

        elif view_name == "search":
            self.active_view = SearchView(
                self.content_frame,
                current_user=self.current_user,
                search_service=self.search_service,
                auth_service=self.auth_service,
                backup_service=self.backup_service,
                on_open_diary_date=self._open_diary_from_search,
                diary_service=self.diary_service,
            )
            self.active_view.pack(fill="both", expand=True)

        elif view_name == "history":
            initial_date = kwargs.get("initial_date")
            self.active_view = HistoryView(
                self.content_frame,
                current_user=self.current_user,
                diary_service=self.diary_service,
                on_open_diary_date=self._open_diary_from_history,
                initial_date_iso=initial_date,
            )
            self.active_view.pack(fill="both", expand=True)

        elif view_name == "import":
            self.active_view = ImportView(
                self.content_frame,
                current_user=self.current_user,
                import_service=self.import_service,
                on_import_completed=self._on_import_finished,
                on_open_diary_date=self._open_diary_from_search,
            )
            self.active_view.pack(fill="both", expand=True)

        elif view_name == "backup":
            self.active_view = BackupView(
                self.content_frame,
                current_user=self.current_user,
                backup_service=self.backup_service,
                diary_service=self.diary_service,
                spell_service=self.spell_service,
                on_data_restored=lambda: self.navigate_to("diary"),
            )
            self.active_view.pack(fill="both", expand=True)

        elif view_name == "users":
            if not self.current_user.is_admin:
                show_message(self, "Acesso Negado", "Apenas administradores podem gerenciar usuários.", kind="danger")
                self.navigate_to("diary")
                return

            self.active_view = UsersView(
                self.content_frame,
                current_user=self.current_user,
                auth_service=self.auth_service,
            )
            self.active_view.pack(fill="both", expand=True)

    def _open_diary_from_search(self, date_iso: str, user_id: Optional[int] = None):
        self.navigate_to("diary", date_iso=date_iso, user_id=user_id)

    def _open_diary_from_history(self, date_iso: str, user_id: Optional[int] = None):
        self.navigate_to("diary", date_iso=date_iso, user_id=user_id)

    def _on_import_finished(self):
        # Callback opcional após importação
        pass
