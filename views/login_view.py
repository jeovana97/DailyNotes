import os
import customtkinter as ctk
from PIL import Image
from typing import Callable, Optional
import config
from services.authentication_service import AuthenticationService
from models.user import User


class LoginView(ctk.CTkFrame):
    """
    Tela de autenticação e configuração inicial do sistema.
    Detecta automaticamente o primeiro uso para guiar o cadastro do administrador.
    """

    def __init__(self, master, auth_service: AuthenticationService, on_login_success: Callable[[User], None]):
        super().__init__(master, fg_color="transparent")
        self.auth_service = auth_service
        self.on_login_success = on_login_success

        self.is_first_run = (self.auth_service.count_users() == 0)

        self._build_ui()

    def _build_ui(self):
        # Container centralizado
        self.center_card = ctk.CTkFrame(
            self,
            width=460,
            corner_radius=16,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.center_card.place(relx=0.5, rely=0.5, anchor="center")

        if self.is_first_run:
            self._build_initial_admin_ui()
        else:
            self._build_login_ui()

    def _build_login_ui(self):
        # Limpa widgets do card
        for widget in self.center_card.winfo_children():
            widget.destroy()

        # Ícone e Cabeçalho
        self._login_ctk_image = None
        if os.path.isfile(config.ICON_PNG_PATH):
            try:
                pil_icon = Image.open(config.ICON_PNG_PATH)
                self._login_ctk_image = ctk.CTkImage(
                    light_image=pil_icon,
                    dark_image=pil_icon,
                    size=(58, 58),
                )
            except Exception:
                self._login_ctk_image = None

        if self._login_ctk_image is not None:
            self.lbl_icon = ctk.CTkLabel(
                self.center_card,
                text="",
                image=self._login_ctk_image,
            )
        else:
            self.lbl_icon = ctk.CTkLabel(
                self.center_card,
                text="📓",
                font=ctk.CTkFont(size=48),
            )
        self.lbl_icon.pack(pady=(25, 5))

        self.lbl_app_name = ctk.CTkLabel(
            self.center_card,
            text=config.APP_NAME,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=config.COLORS["text_dark"],
            justify="center",
        )
        self.lbl_app_name.pack(fill="x", padx=45, pady=(4, 4))

        self.lbl_subtitle = ctk.CTkLabel(
            self.center_card,
            text="Entre com suas credenciais para acessar o diário",
            font=ctk.CTkFont(size=13),
            text_color=config.COLORS["text_muted"],
            justify="center",
        )
        self.lbl_subtitle.pack(fill="x", padx=45, pady=(0, 22))

        # Campo Usuário
        self.lbl_user = ctk.CTkLabel(
            self.center_card,
            text="Usuário:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        self.lbl_user.pack(fill="x", padx=40, pady=(0, 4))

        self.entry_username = ctk.CTkEntry(
            self.center_card,
            width=380,
            height=42,
            placeholder_text="Digite seu usuário...",
            font=ctk.CTkFont(size=14),
            corner_radius=8,
        )
        self.entry_username.pack(fill="x", padx=40, pady=(0, 14))
        self.entry_username.bind("<Return>", lambda e: self.entry_password.focus_set())

        # Campo Senha
        self.lbl_pass = ctk.CTkLabel(
            self.center_card,
            text="Senha:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLORS["text_dark"],
            anchor="w",
        )
        self.lbl_pass.pack(fill="x", padx=40, pady=(0, 4))

        self.pass_container = ctk.CTkFrame(self.center_card, fg_color="transparent")
        self.pass_container.pack(fill="x", padx=40, pady=(0, 5))

        self.entry_password = ctk.CTkEntry(
            self.pass_container,
            height=42,
            placeholder_text="Digite sua senha...",
            show="•",
            font=ctk.CTkFont(size=14),
            corner_radius=8,
        )
        self.entry_password.pack(side="left", fill="x", expand=True)
        self.entry_password.bind("<Return>", lambda e: self._handle_login())

        self.show_pass_var = False
        self.btn_toggle_pass = ctk.CTkButton(
            self.pass_container,
            text="Ver",
            width=64,
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLORS["card_dark_alt"],
            hover_color=config.COLORS["primary"],
            text_color=config.COLORS["button_text"],
            command=self._toggle_show_password,
        )
        self.btn_toggle_pass.pack(side="right", padx=(8, 0))

        # Mensagem de Erro
        self.lbl_error = ctk.CTkLabel(
            self.center_card,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["danger"],
            wraplength=380,
        )
        self.lbl_error.pack(padx=40, pady=4)

        # Botão de Login
        self.btn_login = ctk.CTkButton(
            self.center_card,
            text="Entrar no Sistema",
            width=380,
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            corner_radius=8,
            command=self._handle_login,
        )
        self.btn_login.pack(fill="x", padx=40, pady=(10, 28))

        self.entry_username.focus_set()

    def _build_initial_admin_ui(self):
        for widget in self.center_card.winfo_children():
            widget.destroy()

        self.lbl_icon = ctk.CTkLabel(self.center_card, text="🛡️", font=ctk.CTkFont(size=44))
        self.lbl_icon.pack(pady=(20, 5))

        self.lbl_title = ctk.CTkLabel(
            self.center_card,
            text="Configuração Inicial",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(fill="x", padx=45, pady=(0, 2))

        self.lbl_desc = ctk.CTkLabel(
            self.center_card,
            text="Bem-vindo! Crie o primeiro usuário Administrador para começar.",
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_muted"],
            wraplength=380,
        )
        self.lbl_desc.pack(fill="x", padx=45, pady=(0, 15))

        # Nome Completo
        self.entry_admin_fullname = ctk.CTkEntry(
            self.center_card, width=380, height=40, placeholder_text="Nome Completo (ex: João Silva)", corner_radius=8
        )
        self.entry_admin_fullname.pack(fill="x", padx=40, pady=(0, 10))

        # Usuário
        self.entry_admin_user = ctk.CTkEntry(
            self.center_card, width=380, height=40, placeholder_text="Nome de Usuário (ex: admin)", corner_radius=8
        )
        self.entry_admin_user.pack(fill="x", padx=40, pady=(0, 10))

        # Senha
        self.entry_admin_pass = ctk.CTkEntry(
            self.center_card, width=380, height=40, placeholder_text="Senha (mínimo 4 caracteres)", show="•", corner_radius=8
        )
        self.entry_admin_pass.pack(fill="x", padx=40, pady=(0, 10))

        # Confirmação de Senha
        self.entry_admin_pass_confirm = ctk.CTkEntry(
            self.center_card, width=380, height=40, placeholder_text="Confirme a Senha", show="•", corner_radius=8
        )
        self.entry_admin_pass_confirm.pack(fill="x", padx=40, pady=(0, 5))
        self.entry_admin_pass_confirm.bind("<Return>", lambda e: self._handle_create_admin())

        self.lbl_error = ctk.CTkLabel(
            self.center_card, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color=config.COLORS["danger"], wraplength=380
        )
        self.lbl_error.pack(padx=40, pady=4)

        self.btn_create_admin = ctk.CTkButton(
            self.center_card,
            text="Criar Administrador e Iniciar",
            width=380,
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=config.COLORS["secondary"],
            hover_color=config.COLORS["secondary_hover"],
            text_color="#FFFFFF",
            corner_radius=8,
            command=self._handle_create_admin,
        )
        self.btn_create_admin.pack(fill="x", padx=40, pady=(10, 28))

        self.entry_admin_fullname.focus_set()

    def _toggle_show_password(self):
        self.show_pass_var = not self.show_pass_var
        if self.show_pass_var:
            self.entry_password.configure(show="")
            self.btn_toggle_pass.configure(text="Ocultar")
        else:
            self.entry_password.configure(show="•")
            self.btn_toggle_pass.configure(text="Ver")

    def _handle_login(self):
        username = self.entry_username.get().strip()
        password = self.entry_password.get()

        user, msg = self.auth_service.authenticate(username, password)
        if not user:
            self.lbl_error.configure(text=msg)
            return

        self.lbl_error.configure(text="")
        self.on_login_success(user)

    def _handle_create_admin(self):
        full_name = self.entry_admin_fullname.get().strip()
        username = self.entry_admin_user.get().strip()
        pwd = self.entry_admin_pass.get()
        pwd_confirm = self.entry_admin_pass_confirm.get()

        if pwd != pwd_confirm:
            self.lbl_error.configure(text="As senhas digitadas não coincidem.")
            return

        user, msg = self.auth_service.create_initial_admin(username, full_name, pwd)
        if not user:
            self.lbl_error.configure(text=msg)
            return

        self.lbl_error.configure(text="")
        self.on_login_success(user)
