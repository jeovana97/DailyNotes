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
from services.update_service import UpdateService
from services.schedule_service import ScheduleService
from utils.notification_utils import consume_pending_toast_action

from views.login_view import LoginView
from views.diary_view import DiaryView
from views.notes_view import NotesView
from views.schedules_view import SchedulesView
from views.search_view import SearchView
from views.history_view import HistoryView
from views.import_view import ImportView
from views.backup_view import BackupView
from views.users_view import UsersView
from views.components.dialogs import show_message, ask_confirmation
from views.components.update_dialog import UpdateAvailableDialog
from views.components.responsive_toolbar import WidgetTooltip
from utils.syntax_highlighter import configure_syntax_tags
from utils.window_utils import center_window_on_primary_screen, get_display_monitors, center_modal_on_parent


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
        center_modal_on_parent(self, parent, 380, 280)

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


class SwitchUserDialog(ctk.CTkToplevel):
    """Modal compacto para troca rápida de usuário sem sair para a tela de login."""
    def __init__(self, parent, current_user: User, auth_service: AuthenticationService):
        super().__init__(parent)
        self.title("Trocar Usuário")
        self.geometry("420x310")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.current_user = current_user
        self.auth_service = auth_service
        self.selected_user: Optional[User] = None
        center_modal_on_parent(self, parent, 420, 310)

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
            text="🔄 Troca Rápida de Usuário",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(pady=(14, 4))

        self.lbl_curr = ctk.CTkLabel(
            self.container,
            text=f"Conectado agora: {current_user.full_name} (@{current_user.username})",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_curr.pack(pady=(0, 12))

        # Lista de usuários ativos
        self._user_options = self.auth_service.list_active_login_options()
        self._label_to_username = {
            f"{full_name} (@{uname})": uname for uname, full_name in self._user_options
        }
        labels = list(self._label_to_username.keys())
        if not labels:
            labels = [f"{current_user.full_name} (@{current_user.username})"]
            self._label_to_username[labels[0]] = current_user.username

        lbl_u = ctk.CTkLabel(
            self.container,
            text="Selecione ou digite o usuário:",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        lbl_u.pack(fill="x", padx=20, pady=(0, 4))

        self.combo_user = ctk.CTkComboBox(
            self.container,
            values=labels,
            height=36,
            corner_radius=6,
        )
        # Pré-seleciona outro usuário diferente do atual se disponível
        other_label = next(
            (lbl for lbl, uname in self._label_to_username.items() if uname != current_user.username),
            labels[0],
        )
        self.combo_user.set(other_label)
        self.combo_user.pack(fill="x", padx=20, pady=(0, 10))

        lbl_p = ctk.CTkLabel(
            self.container,
            text="Senha do usuário:",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        lbl_p.pack(fill="x", padx=20, pady=(0, 4))

        pass_row = ctk.CTkFrame(self.container, fg_color="transparent")
        pass_row.pack(fill="x", padx=20, pady=(0, 6))

        self.entry_pass = ctk.CTkEntry(
            pass_row,
            height=36,
            placeholder_text="Digite a senha...",
            show="•",
            corner_radius=6,
        )
        self.entry_pass.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_pass.bind("<Return>", lambda e: self._on_switch())

        self._show_pw = False
        self.btn_eye = ctk.CTkButton(
            pass_row,
            text="Ver",
            width=46,
            height=36,
            corner_radius=6,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self._toggle_pw,
        )
        self.btn_eye.pack(side="right")

        self.lbl_error = ctk.CTkLabel(
            self.container,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=config.COLORS["danger"],
        )
        self.lbl_error.pack(fill="x", padx=20, pady=(0, 8))

        btn_row = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=20, pady=(0, 14))

        self.btn_confirm = ctk.CTkButton(
            btn_row,
            text="🔄 Trocar Agora",
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_switch,
        )
        self.btn_confirm.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_cancel = ctk.CTkButton(
            btn_row,
            text="Cancelar",
            width=100,
            height=36,
            corner_radius=8,
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["border_dark"],
            text_color=config.COLORS["button_text"],
            command=self.destroy,
        )
        self.btn_cancel.pack(side="right")

        self.after(80, lambda: self.entry_pass.focus_set() if self.winfo_exists() else None)
        self.wait_window(self)

    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        self.entry_pass.configure(show="" if self._show_pw else "•")
        self.btn_eye.configure(text="Ocultar" if self._show_pw else "Ver")

    def _on_switch(self):
        raw_val = self.combo_user.get().strip()
        username = self._label_to_username.get(raw_val, raw_val)
        password = self.entry_pass.get()

        if not username:
            self.lbl_error.configure(text="Selecione ou informe o usuário.")
            return
        if not password:
            self.lbl_error.configure(text="Informe a senha do usuário.")
            return

        user, msg = self.auth_service.authenticate(username, password)
        if user is None:
            self.lbl_error.configure(text=msg or "Usuário ou senha inválidos.")
            self.entry_pass.delete(0, "end")
            self.entry_pass.focus_set()
            return

        self.selected_user = user
        self.destroy()


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
        self._apply_centered_geometry()
        # Reaplica após 60ms e 200ms para garantir centralização exata na tela principal após cálculo de DPI
        self.after(60, self._apply_centered_geometry)
        self.after(200, self._apply_centered_geometry)

        self._icon_photo = None
        self._brand_ctk_image = None
        self._apply_window_icon()
        # Reaplica após 250ms pois o CustomTkinter redefine o ícone padrão da janela aos 200ms no Windows
        self.after(250, self._apply_window_icon)

        # Inicializa Serviços
        self.diary_service = DiaryService(db_path=self.db_path)
        self.note_service = NoteService(db_path=self.db_path)
        self.search_service = SearchService(db_path=self.db_path)
        self.import_service = ImportService(
            diary_service=self.diary_service,
            note_service=self.note_service,
            db_path=self.db_path,
        )
        self.backup_service = BackupService(db_path=self.db_path)
        self.spell_service = WindowsSpellCheckService(db_path=self.db_path)
        self.update_service = UpdateService(current_version=config.APP_VERSION)
        self.schedule_service = ScheduleService(db_path=self.db_path)

        self.current_user: Optional[User] = None
        self.active_view = None
        self.nav_buttons = {}
        self._nav_items_meta = {}
        self.sidebar_collapsed: bool = False
        self._sidebar_tooltips = []
        self._auto_backup_timer_id = None
        self._reminder_timer_id = None
        self._toast_poll_timer_id = None
        self._pending_toast_open: bool = False
        self._pending_schedule_open_id: Optional[int] = None
        self._update_checked = False

        # Intercepta evento de fechar janela
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self._show_login_screen()
        self._schedule_auto_backup_check(delay_ms=4000)
        self._schedule_reminder_check(delay_ms=3000)
        self._schedule_toast_action_poll(delay_ms=800)
        # Verifica atualizações silenciosamente em segundo plano após 2.5 segundos
        self.after(2500, self._start_background_update_check)

    def _apply_centered_geometry(self):
        """
        Centraliza a janela principal na TELA PRINCIPAL (Primary Monitor).
        Detecta e trata múltiplos monitores de forma que a aplicação nunca abra fora da tela.
        """
        try:
            if not self.winfo_exists():
                return
            center_window_on_primary_screen(
                self,
                desired_width=1240,
                desired_height=780,
                min_width=1050,
                min_height=680,
            )
        except Exception:
            pass

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
        # Verifica se há solicitação pendente para abrir um agendamento via notificação
        pending_action = consume_pending_toast_action()
        if pending_action and pending_action.get("action") == "open_schedule":
            self._pending_toast_open = True
            self._pending_schedule_open_id = pending_action.get("schedule_id")

        if self._pending_toast_open:
            sched_id = self._pending_schedule_open_id
            self._pending_toast_open = False
            self._pending_schedule_open_id = None
            self.navigate_to("schedules")
            if hasattr(self.active_view, "open_schedule_by_id"):
                self.active_view.open_schedule_by_id(sched_id)
        else:
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
        sidebar_width = 76 if self.sidebar_collapsed else 240
        self.sidebar = ctk.CTkFrame(
            self,
            width=sidebar_width,
            corner_radius=0,
            fg_color=config.COLORS["sidebar"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Cabeçalho da Marca + Botão de Recolher/Expandir Menu Lateral
        self.brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.brand_frame.pack(fill="x", padx=8, pady=(14, 10))

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
        self.lbl_logo.pack(side="left", padx=(4, 8))

        self.lbl_app = ctk.CTkLabel(
            self.brand_frame,
            text="Diário de\nAnotações",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=config.COLORS["text_dark"],
            justify="left",
        )
        self.lbl_app.pack(side="left", fill="x", expand=True)

        self.btn_toggle_sidebar = ctk.CTkButton(
            self.brand_frame,
            text="▶" if self.sidebar_collapsed else "◀",
            width=28,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._toggle_sidebar,
        )
        self.btn_toggle_sidebar.pack(side="right", padx=(2, 0))
        self._sidebar_tooltips = [
            WidgetTooltip(self.btn_toggle_sidebar, "Expandir / Recolher menu lateral")
        ]

        # Área Rolável do Menu Lateral (para suportar janelas menores sem cortar opções)
        self.sidebar_scroll = ctk.CTkScrollableFrame(
            self.sidebar,
            width=54 if self.sidebar_collapsed else 218,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=("#CBD5E1", "#334155"),
            scrollbar_button_hover_color=("#94A3B8", "#475569"),
        )
        try:
            self.sidebar_scroll._scrollbar.configure(width=6)
        except Exception:
            pass
        self.sidebar_scroll.pack(fill="both", expand=True, padx=2, pady=(0, 6))
        try:
            self.sidebar_scroll._parent_canvas.bind("<Configure>", lambda _e: self.after(10, self._update_sidebar_scrollbar), add="+")
            self.sidebar_scroll.bind("<Configure>", lambda _e: self.after(10, self._update_sidebar_scrollbar), add="+")
        except Exception:
            pass

        # Card do Usuário Logado
        self.user_card = ctk.CTkFrame(
            self.sidebar_scroll,
            corner_radius=10,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.user_card.pack(fill="x", padx=6, pady=(0, 14))

        self.lbl_user_name = ctk.CTkLabel(
            self.user_card,
            text=f"👤 {self.current_user.full_name}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        self.lbl_user_name.pack(fill="x", padx=12, pady=(10, 2))

        role_label = "🛡️ Administrador" if self.current_user.is_admin else "👤 Usuário"
        self.lbl_role = ctk.CTkLabel(
            self.user_card,
            text=role_label,
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
            anchor="w",
        )
        self.lbl_role.pack(fill="x", padx=12, pady=(0, 8))

        # Botões de perfil (Trocar senha e Sair)
        self.user_actions = ctk.CTkFrame(self.user_card, fg_color="transparent")
        self.user_actions.pack(fill="x", padx=10, pady=(0, 6))

        self.btn_pass = ctk.CTkButton(
            self.user_actions,
            text="🔑 Senha",
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._open_change_password_dialog,
        )
        self.btn_pass.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_logout = ctk.CTkButton(
            self.user_actions,
            text="🚪 Sair",
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["danger"],
            text_color=config.COLORS["button_text"],
            command=self._handle_logout,
        )
        self.btn_logout.pack(side="right", fill="x", expand=True, padx=(4, 0))

        self.btn_switch_user = ctk.CTkButton(
            self.user_card,
            text="🔄 Trocar Usuário",
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._open_switch_user_dialog,
        )
        self.btn_switch_user.pack(fill="x", padx=10, pady=(0, 10))

        self._sidebar_tooltips.extend([
            WidgetTooltip(self.btn_pass, "Alterar Minha Senha"),
            WidgetTooltip(self.btn_logout, "Sair do Sistema"),
            WidgetTooltip(self.btn_switch_user, "Trocar Usuário"),
        ])

        # Itens do Menu de Navegação
        self.nav_menu_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color="transparent")
        self.nav_menu_frame.pack(fill="x", padx=6, pady=0)

        nav_items = [
            ("diary", "📝", "📝 Diário do Dia"),
            ("notes", "📁", "📁 Notas & Pastas"),
            ("schedules", "⏰", "⏰ Agendamentos"),
            ("search", "🔍", "🔍 Pesquisa Avançada"),
            ("history", "📅", "📅 Histórico & Calendário"),
            ("import", "📥", "📥 Importar TXT"),
            ("backup", "💾", "💾 Exportar & Backup"),
        ]

        if self.current_user.is_admin:
            nav_items.append(("users", "👥", "👥 Gerenciar Usuários"))

        self.nav_buttons.clear()
        self._nav_items_meta.clear()
        for key, icon, label in nav_items:
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
            self._nav_items_meta[key] = (icon, label)
            self._sidebar_tooltips.append(WidgetTooltip(btn, label))

        # Rodapé da Barra Lateral: Alternador de Tema e Versão
        self.sidebar_footer = ctk.CTkFrame(self.sidebar_scroll, fg_color="transparent")
        self.sidebar_footer.pack(fill="x", padx=6, pady=(14, 10))

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

        self.lbl_ver = ctk.CTkLabel(
            self.sidebar_footer,
            text=f"v{config.APP_VERSION} • Windows",
            font=ctk.CTkFont(size=11),
            text_color=config.COLORS["text_muted"],
        )
        self.lbl_ver.pack(anchor="w", pady=(0, 4))

        self.btn_check_updates = ctk.CTkButton(
            self.sidebar_footer,
            text="🔄 Verificar Atualização",
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color=config.COLORS["card_dark_alt"],
            text_color=config.COLORS["text_muted"],
            anchor="w",
            command=lambda: self._check_updates_manually(),
        )
        self.btn_check_updates.pack(fill="x")
        self._sidebar_tooltips.extend([
            WidgetTooltip(self.switch_theme, "Alternar Tema Claro / Escuro"),
            WidgetTooltip(self.btn_check_updates, "Verificar Atualização"),
        ])

        # Aplica modo recolhido/expandido atual
        self._apply_sidebar_mode()

        # 2. Container de Conteúdo Principal
        self.content_frame = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color="transparent",
        )
        self.content_frame.grid(row=0, column=1, sticky="nsew")

    def _update_sidebar_scrollbar(self):
        """Mostra a barra de rolagem fina apenas quando o conteúdo não couber na altura da tela."""
        try:
            if not hasattr(self, "sidebar_scroll") or not self.sidebar_scroll.winfo_exists():
                return
            canvas = self.sidebar_scroll._parent_canvas
            sb = self.sidebar_scroll._scrollbar
            req_h = self.sidebar_scroll.winfo_reqheight()
            vis_h = canvas.winfo_height()
            if vis_h > 10 and req_h <= vis_h + 2:
                sb.grid_remove()
            else:
                sb.grid()
        except Exception:
            pass

    def _toggle_sidebar(self):
        """Alterna o menu lateral entre modo completo (240px) e apenas ícones (76px)."""
        self.sidebar_collapsed = not self.sidebar_collapsed
        self._apply_sidebar_mode()

    def _apply_sidebar_mode(self):
        """Atualiza os widgets do menu lateral conforme o estado recolhido/expandido."""
        if not hasattr(self, "sidebar") or not self.sidebar.winfo_exists():
            return

        collapsed = self.sidebar_collapsed
        self.sidebar.configure(width=76 if collapsed else 240)
        if hasattr(self, "sidebar_scroll"):
            self.sidebar_scroll.configure(width=54 if collapsed else 218)

        # Cabeçalho
        self.btn_toggle_sidebar.pack_forget()
        if collapsed:
            self.lbl_logo.pack_forget()
            self.lbl_app.pack_forget()
            self.btn_toggle_sidebar.configure(text="▶", width=44)
            self.btn_toggle_sidebar.pack(anchor="center")
        else:
            self.lbl_logo.pack_forget()
            self.lbl_app.pack_forget()
            self.lbl_logo.pack(side="left", padx=(4, 8))
            self.lbl_app.pack(side="left", fill="x", expand=True)
            self.btn_toggle_sidebar.configure(text="◀", width=28)
            self.btn_toggle_sidebar.pack(side="right", padx=(2, 0))

        # Card do usuário
        if collapsed:
            self.lbl_user_name.pack_forget()
            self.lbl_role.pack_forget()
            self.user_actions.pack_forget()
            self.btn_switch_user.pack_forget()

            self.btn_pass.pack_forget()
            self.btn_logout.pack_forget()
            self.btn_pass.configure(text="🔑", width=44)
            self.btn_logout.configure(text="🚪", width=44)
            self.btn_pass.pack(pady=(4, 2))
            self.btn_logout.pack(pady=(0, 2))
            self.user_actions.pack(fill="x", padx=4, pady=(6, 4))

            self.btn_switch_user.configure(text="🔄", width=44)
            self.btn_switch_user.pack(padx=4, pady=(0, 6))
        else:
            self.lbl_user_name.pack_forget()
            self.lbl_role.pack_forget()
            self.user_actions.pack_forget()
            self.btn_switch_user.pack_forget()

            self.lbl_user_name.pack(fill="x", padx=12, pady=(10, 2))
            self.lbl_role.pack(fill="x", padx=12, pady=(0, 8))

            self.btn_pass.pack_forget()
            self.btn_logout.pack_forget()
            self.btn_pass.configure(text="🔑 Senha", width=80)
            self.btn_logout.configure(text="🚪 Sair", width=80)
            self.btn_pass.pack(side="left", fill="x", expand=True, padx=(0, 4))
            self.btn_logout.pack(side="right", fill="x", expand=True, padx=(4, 0))
            self.user_actions.pack(fill="x", padx=10, pady=(0, 6))

            self.btn_switch_user.configure(text="🔄 Trocar Usuário", width=180)
            self.btn_switch_user.pack(fill="x", padx=10, pady=(0, 10))

        # Botões do menu de navegação
        for key, btn in self.nav_buttons.items():
            icon, label = self._nav_items_meta.get(key, ("•", key))
            if collapsed:
                btn.configure(text=icon, width=44, anchor="center", font=ctk.CTkFont(size=16))
                btn.pack_configure(fill="none", anchor="center", pady=3)
            else:
                btn.configure(text=label, width=180, anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
                btn.pack_configure(fill="x", anchor="w", pady=3)

        # Rodapé
        is_light = not bool(self.switch_theme.get())
        if collapsed:
            self.switch_theme.configure(text="", width=44)
            self.switch_theme.pack_configure(anchor="center")
            self.lbl_ver.configure(text=f"v{config.APP_VERSION}")
            self.lbl_ver.pack_configure(anchor="center")
            self.btn_check_updates.configure(text="🔄", width=44, anchor="center")
            self.btn_check_updates.pack_configure(fill="none", anchor="center")
        else:
            self.switch_theme.configure(text="Modo Claro" if is_light else "Modo Escuro", width=140)
            self.switch_theme.pack_configure(anchor="w")
            self.lbl_ver.configure(text=f"v{config.APP_VERSION} • Windows")
            self.lbl_ver.pack_configure(anchor="w")
            self.btn_check_updates.configure(text="🔄 Verificar Atualização", width=180, anchor="w")
            self.btn_check_updates.pack_configure(fill="x", anchor="w")

        self.update_idletasks()
        self.after(20, self._update_sidebar_scrollbar)

    def _toggle_theme(self):
        if self.switch_theme.get():
            new_theme = "dark"
            ctk.set_appearance_mode("dark")
            if not self.sidebar_collapsed:
                self.switch_theme.configure(text="Modo Escuro")
        else:
            new_theme = "light"
            ctk.set_appearance_mode("light")
            if not self.sidebar_collapsed:
                self.switch_theme.configure(text="Modo Claro")

        if self.current_user:
            self.current_user.theme_preference = new_theme
            self.auth_service.update_theme_preference(self.current_user.id, new_theme)

        if self.active_view and hasattr(self.active_view, "txt_content"):
            try:
                configure_syntax_tags(self.active_view.txt_content._textbox)
            except Exception:
                pass

    def _open_change_password_dialog(self):
        SelfPasswordChangeDialog(self, self.current_user.id, self.auth_service)

    def _open_switch_user_dialog(self):
        """Permite trocar rapidamente para outro usuário ativo sem voltar à tela de login."""
        if not self.current_user:
            return
        if hasattr(self.active_view, "confirm_discard_if_unsaved"):
            if not self.active_view.confirm_discard_if_unsaved():
                return

        diag = SwitchUserDialog(self, self.current_user, self.auth_service)
        if diag.selected_user is not None:
            self._on_login_success(diag.selected_user)

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
        if self._reminder_timer_id is not None:
            try:
                self.after_cancel(self._reminder_timer_id)
            except Exception:
                pass
            self._reminder_timer_id = None
        if self._toast_poll_timer_id is not None:
            try:
                self.after_cancel(self._toast_poll_timer_id)
            except Exception:
                pass
            self._toast_poll_timer_id = None
        self.destroy()

    def _schedule_reminder_check(self, delay_ms: int = 25000):
        """Agenda verificação periódica de lembretes e agendamentos pendentes."""
        try:
            if not self.winfo_exists():
                return
            if self._reminder_timer_id is not None:
                try:
                    self.after_cancel(self._reminder_timer_id)
                except Exception:
                    pass
            self._reminder_timer_id = self.after(delay_ms, self._run_reminder_check)
        except Exception:
            pass

    def _run_reminder_check(self):
        """Verifica se há agendamentos que atingiram a data/horário e dispara notificações do Windows."""
        self._reminder_timer_id = None
        try:
            if not self.winfo_exists():
                return
            if self.current_user:
                notified = self.schedule_service.check_and_notify_due_schedules(user_id=self.current_user.id)
                if notified and hasattr(self.active_view, "refresh"):
                    self.active_view.refresh()
        except Exception:
            pass
        finally:
            self._schedule_reminder_check(delay_ms=25000)

    def _schedule_toast_action_poll(self, delay_ms: int = 800):
        """Verifica periodicamente se houve clique em botões de notificações do Windows."""
        try:
            if not self.winfo_exists():
                return
            if self._toast_poll_timer_id is not None:
                try:
                    self.after_cancel(self._toast_poll_timer_id)
                except Exception:
                    pass
            self._toast_poll_timer_id = self.after(delay_ms, self._poll_toast_actions)
        except Exception:
            pass

    def _poll_toast_actions(self):
        self._toast_poll_timer_id = None
        try:
            if not self.winfo_exists():
                return
            action_data = consume_pending_toast_action()
            if action_data:
                act = action_data.get("action")
                sched_id = action_data.get("schedule_id")
                if act == "open_schedule":
                    # Traz a janela para o primeiro plano
                    try:
                        self.deiconify()
                        self.lift()
                        self.attributes("-topmost", True)
                        self.after(200, lambda: self.attributes("-topmost", False) if self.winfo_exists() else None)
                        self.focus_force()
                    except Exception:
                        pass

                    if self.current_user:
                        self.navigate_to("schedules")
                        if hasattr(self.active_view, "open_schedule_by_id"):
                            self.active_view.open_schedule_by_id(sched_id)
                    else:
                        self._pending_toast_open = True
                        self._pending_schedule_open_id = sched_id
                elif act == "snooze_refresh":
                    if self.current_user and hasattr(self.active_view, "refresh"):
                        self.active_view.refresh()
        except Exception:
            pass
        finally:
            self._schedule_toast_action_poll(delay_ms=800)

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

    def _start_background_update_check(self):
        """Dispara verificação de versão em segundo plano sem bloquear a inicialização."""
        if self._update_checked:
            return
        import threading
        t = threading.Thread(target=self._run_background_update_check, daemon=True)
        t.start()

    def _run_background_update_check(self):
        try:
            res = self.update_service.check_for_updates(timeout_sec=5)
            self._update_checked = True
            if res.get("has_update"):
                self.after(0, lambda: self._prompt_update_dialog(res))
        except Exception:
            pass

    def _check_updates_manually(self):
        """Acionado manualmente pelo usuário no rodapé da barra lateral."""
        if hasattr(self, "btn_check_updates"):
            self.btn_check_updates.configure(text="🔄 Verificando...", state="disabled")
        import threading

        def _worker():
            res = self.update_service.check_for_updates(timeout_sec=8)

            def _on_finish():
                if hasattr(self, "btn_check_updates"):
                    self.btn_check_updates.configure(
                        text="🔄 Verificar Atualização", state="normal"
                    )
                if res.get("has_update"):
                    self._prompt_update_dialog(res)
                elif res.get("error"):
                    show_message(
                        self,
                        "Verificação de Atualizações",
                        f"Não foi possível verificar no momento:\n{res['error']}",
                        kind="info",
                    )
                else:
                    show_message(
                        self,
                        "DailyNotes Atualizado",
                        f"Você já está utilizando a versão mais recente ({config.APP_VERSION})!",
                        kind="success",
                    )

            self.after(0, _on_finish)

        threading.Thread(target=_worker, daemon=True).start()

    def _prompt_update_dialog(self, update_info: dict):
        """Abre o diálogo de nova versão se a janela ainda existir."""
        try:
            if not self.winfo_exists():
                return
            UpdateAvailableDialog(self, update_info, self.update_service)
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
                import_service=self.import_service,
                initial_folder_id=kwargs.get("folder_id"),
                initial_note_id=kwargs.get("note_id"),
                highlight_query=kwargs.get("highlight_query"),
            )
            self.active_view.pack(fill="both", expand=True)

        elif view_name == "schedules":
            self.active_view = SchedulesView(
                self.content_frame,
                current_user=self.current_user,
                schedule_service=self.schedule_service,
                on_open_diary_date=self._open_diary_from_search,
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
                on_open_folder_note=self._open_note_from_import,
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
                note_service=self.note_service,
                on_import_completed=self._on_import_finished,
                on_open_diary_date=self._open_diary_from_search,
                on_open_imported_note=self._open_note_from_import,
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

    def _open_note_from_import(
        self,
        folder_id: Optional[int] = None,
        note_id: Optional[int] = None,
        highlight_query: Optional[str] = None,
    ):
        self.navigate_to("notes", folder_id=folder_id, note_id=note_id, highlight_query=highlight_query)

    def _on_import_finished(self):
        # Callback opcional após importação
        pass
