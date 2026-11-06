import tkinter as tk
from typing import Optional, Callable, List
import customtkinter as ctk

import config
from models.user import User
from services.authentication_service import AuthenticationService
from views.components.dialogs import show_message, ask_confirmation


class UserModalDialog(ctk.CTkToplevel):
    """Modal para cadastro ou edição de usuário."""
    def __init__(self, parent, title: str, user: Optional[User] = None):
        super().__init__(parent)
        self.title(title)
        self.geometry("450x480")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.user = user
        self.result = None

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() // 2) - 225
        py = parent.winfo_y() + (parent.winfo_height() // 2) - 240
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
            text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(pady=(12, 12))

        # Nome Completo
        self.lbl_name = ctk.CTkLabel(
            self.container,
            text="Nome Completo:",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_name.pack(fill="x", padx=25, pady=(0, 2))
        self.entry_name = ctk.CTkEntry(self.container, height=36, corner_radius=6)
        self.entry_name.pack(fill="x", padx=25, pady=(0, 10))
        if user:
            self.entry_name.insert(0, user.full_name)

        # Nome de Usuário
        self.lbl_user = ctk.CTkLabel(
            self.container,
            text="Nome de Usuário (login):",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_user.pack(fill="x", padx=25, pady=(0, 2))
        self.entry_username = ctk.CTkEntry(self.container, height=36, corner_radius=6)
        self.entry_username.pack(fill="x", padx=25, pady=(0, 10))
        if user:
            self.entry_username.insert(0, user.username)
            self.entry_username.configure(state="disabled")

        # Senha (apenas no cadastro)
        if not user:
            self.lbl_pass = ctk.CTkLabel(
                self.container,
                text="Senha Inicial:",
                anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=config.COLORS["text_dark"],
            )
            self.lbl_pass.pack(fill="x", padx=25, pady=(0, 2))
            self.entry_password = ctk.CTkEntry(self.container, height=36, show="•", corner_radius=6)
            self.entry_password.pack(fill="x", padx=25, pady=(0, 10))

        # Perfil (Admin vs Usuário comum)
        self.lbl_role = ctk.CTkLabel(
            self.container,
            text="Perfil de Acesso:",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_role.pack(fill="x", padx=25, pady=(0, 2))
        self.combo_role = ctk.CTkComboBox(
            self.container,
            values=["user (Usuário Padrão)", "admin (Administrador)"],
            height=36,
            corner_radius=6,
            command=self._on_role_changed,
        )
        if user and user.is_admin:
            self.combo_role.set("admin (Administrador)")
        else:
            self.combo_role.set("user (Usuário Padrão)")
        self.combo_role.pack(fill="x", padx=25, pady=(0, 10))

        # Checkboxes de permissão
        self.var_can_view_all = tk.BooleanVar(value=user.can_view_all_diaries if user else False)
        self.chk_can_view_all = ctk.CTkCheckBox(
            self.container,
            text="Permitir consultar os diários de outros usuários",
            variable=self.var_can_view_all,
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_dark"],
        )
        self.chk_can_view_all.pack(anchor="w", padx=25, pady=(5, 5))

        self.var_is_active = tk.BooleanVar(value=user.is_active if user else True)
        self.chk_is_active = ctk.CTkCheckBox(
            self.container,
            text="Usuário ativo (pode fazer login)",
            variable=self.var_is_active,
            font=ctk.CTkFont(size=12),
            text_color=config.COLORS["text_dark"],
        )
        self.chk_is_active.pack(anchor="w", padx=25, pady=(5, 15))

        self._on_role_changed(self.combo_role.get())

        # Botões
        self.btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.btn_frame.pack(side="bottom", fill="x", padx=25, pady=(0, 15))

        self.btn_save = ctk.CTkButton(
            self.btn_frame,
            text="Salvar",
            width=120,
            height=36,
            corner_radius=8,
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_save,
        )
        self.btn_save.pack(side="left")

        self.btn_cancel = ctk.CTkButton(
            self.btn_frame,
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

        self.wait_window(self)

    def _on_role_changed(self, choice: str):
        is_admin = "admin" in choice.lower()
        if not is_admin:
            self.var_can_view_all.set(False)
            self.chk_can_view_all.configure(state="disabled")
        else:
            self.chk_can_view_all.configure(state="normal")

    def _on_save(self):
        name = self.entry_name.get().strip()
        username = self.entry_username.get().strip()
        role = "admin" if "admin" in self.combo_role.get().lower() else "user"
        can_view_all = self.var_can_view_all.get()
        is_active = self.var_is_active.get()

        if not name:
            show_message(self, "Aviso", "O nome completo não pode estar em branco.", kind="warning")
            return

        if not self.user:
            password = self.entry_password.get()
            if len(password) < 4:
                show_message(self, "Aviso", "A senha deve conter no mínimo 4 caracteres.", kind="warning")
                return
            self.result = {
                "name": name,
                "username": username,
                "password": password,
                "role": role,
                "can_view_all": can_view_all,
                "is_active": is_active,
            }
        else:
            self.result = {
                "name": name,
                "role": role,
                "can_view_all": can_view_all,
                "is_active": is_active,
            }
        self.destroy()


class ResetPasswordDialog(ctk.CTkToplevel):
    """Modal para redefinir senha de usuário."""
    def __init__(self, parent, target_user: User):
        super().__init__(parent)
        self.title("Redefinir Senha")
        self.geometry("380x240")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.new_password = None

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() // 2) - 190
        py = parent.winfo_y() + (parent.winfo_height() // 2) - 120
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
            text=f"Redefinir Senha de {target_user.username}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(pady=(12, 10))

        self.entry_pass = ctk.CTkEntry(
            self.container,
            height=36,
            placeholder_text="Nova Senha (mínimo 4 caracteres)",
            show="•",
            corner_radius=6,
        )
        self.entry_pass.pack(fill="x", padx=20, pady=(0, 15))

        self.btn_save = ctk.CTkButton(
            self.container,
            text="Redefinir Senha",
            height=36,
            corner_radius=8,
            fg_color=config.COLORS["warning"],
            hover_color=config.COLORS["warning_hover"],
            text_color="#FFFFFF",
            command=self._on_save,
        )
        self.btn_save.pack(fill="x", padx=20, pady=(0, 8))

        self.wait_window(self)

    def _on_save(self):
        pwd = self.entry_pass.get()
        if len(pwd) < 4:
            show_message(self, "Aviso", "A nova senha deve ter no mínimo 4 caracteres.", kind="warning")
            return
        self.new_password = pwd
        self.destroy()


class UsersView(ctk.CTkFrame):
    """
    Tela de gerenciamento de usuários para administradores.
    - Listagem de usuários
    - Cadastro de novos usuários
    - Edição de permissões (perfil admin e permissão de consultar outros diários)
    - Redefinição de senha
    - Exclusão com proteção
    """

    def __init__(self, master, current_user: User, auth_service: AuthenticationService):
        super().__init__(master, fg_color="transparent")
        self.current_user = current_user
        self.auth_service = auth_service

        self._build_ui()
        self._load_users()

    def _build_ui(self):
        # Cabeçalho da tela
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
            text="👥 Gerenciamento de Usuários e Permissões",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=config.COLORS["text_dark"],
        )
        self.lbl_title.pack(side="left", padx=15, pady=12)

        self.btn_new_user = ctk.CTkButton(
            self.header_card,
            text="➕ Cadastrar Novo Usuário",
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLORS["primary"],
            hover_color=config.COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._handle_create_user,
        )
        self.btn_new_user.pack(side="right", padx=15, pady=12)

        # Tabela / Lista de Usuários
        self.users_scroll = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color=config.COLORS["card_dark"],
            border_width=1,
            border_color=config.COLORS["border_dark"],
        )
        self.users_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

    def _load_users(self):
        for widget in self.users_scroll.winfo_children():
            widget.destroy()

        users = self.auth_service.list_users(self.current_user)

        for u in users:
            card = ctk.CTkFrame(
                self.users_scroll,
                corner_radius=10,
                fg_color=config.COLORS["card_dark_alt"],
                border_width=1,
                border_color=config.COLORS["border_dark"],
            )
            card.pack(fill="x", padx=10, pady=5)

            # Informações do Usuário
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=15, pady=10)

            lbl_name = ctk.CTkLabel(
                info_frame,
                text=f"{u.full_name} (@{u.username})",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=config.COLORS["text_dark"],
                anchor="w",
            )
            lbl_name.pack(fill="x")

            role_badge = "🛡️ Administrador" if u.is_admin else "👤 Usuário Padrão"
            view_perm = "• Pode consultar outros diários" if u.can_view_all_diaries else "• Acesso restrito às suas anotações"
            status_text = "🟢 Ativo" if u.is_active else "🔴 Desativado"

            lbl_sub = ctk.CTkLabel(
                info_frame,
                text=f"Perfil: {role_badge}  |  Permissão: {view_perm}  |  Status: {status_text}",
                font=ctk.CTkFont(size=12),
                text_color=config.COLORS["text_muted"],
                anchor="w",
            )
            lbl_sub.pack(fill="x", pady=(2, 0))

            # Ações à direita
            actions_frame = ctk.CTkFrame(card, fg_color="transparent")
            actions_frame.pack(side="right", padx=15, pady=10)

            btn_edit = ctk.CTkButton(
                actions_frame,
                text="✏️ Permissões",
                width=100,
                height=30,
                corner_radius=6,
                fg_color=config.COLORS["secondary"],
                hover_color=config.COLORS["secondary_hover"],
                text_color="#FFFFFF",
                command=lambda target=u: self._handle_edit_permissions(target),
            )
            btn_edit.pack(side="left", padx=4)

            btn_reset = ctk.CTkButton(
                actions_frame,
                text="🔑 Senha",
                width=80,
                height=30,
                corner_radius=6,
                fg_color=config.COLORS["card_dark_alt"],
                hover_color=config.COLORS["warning"],
                text_color=config.COLORS["button_text"],
                command=lambda target=u: self._handle_reset_password(target),
            )
            btn_reset.pack(side="left", padx=4)

            if u.id != self.current_user.id:
                btn_delete = ctk.CTkButton(
                    actions_frame,
                    text="🗑️",
                    width=36,
                    height=30,
                    corner_radius=6,
                    fg_color=config.COLORS["card_dark_alt"],
                    hover_color=config.COLORS["danger"],
                    text_color=config.COLORS["button_text"],
                    command=lambda target=u: self._handle_delete_user(target),
                )
                btn_delete.pack(side="left", padx=4)

    def _handle_create_user(self):
        diag = UserModalDialog(self, "Cadastrar Novo Usuário")
        if diag.result:
            res = diag.result
            new_u, msg = self.auth_service.create_user(
                creator=self.current_user,
                username=res["username"],
                full_name=res["name"],
                password=res["password"],
                role=res["role"],
                can_view_all_diaries=res["can_view_all"],
            )
            if new_u:
                show_message(self, "Sucesso", msg, kind="success")
                self._load_users()
            else:
                show_message(self, "Erro", msg, kind="danger")

    def _handle_edit_permissions(self, target_user: User):
        diag = UserModalDialog(self, f"Editar {target_user.username}", user=target_user)
        if diag.result:
            res = diag.result
            ok, msg = self.auth_service.update_user_permissions(
                requester=self.current_user,
                target_user_id=target_user.id,
                role=res["role"],
                can_view_all_diaries=res["can_view_all"],
                is_active=res["is_active"],
            )
            if ok:
                show_message(self, "Atualizado", msg, kind="success")
                self._load_users()
            else:
                show_message(self, "Erro", msg, kind="danger")

    def _handle_reset_password(self, target_user: User):
        diag = ResetPasswordDialog(self, target_user)
        if diag.new_password:
            ok, msg = self.auth_service.admin_reset_password(
                self.current_user, target_user.id, diag.new_password
            )
            if ok:
                show_message(self, "Senha Redefinida", msg, kind="success")
            else:
                show_message(self, "Erro", msg, kind="danger")

    def _handle_delete_user(self, target_user: User):
        confirmed = ask_confirmation(
            self,
            "Confirmação de Exclusão",
            f"Deseja realmente excluir o usuário '{target_user.full_name}' (@{target_user.username})?\n\n"
            "⚠️ Todas as anotações deste usuário serão excluídas definitivamente.",
            kind="danger",
        )
        if confirmed:
            ok, msg = self.auth_service.delete_user(self.current_user, target_user.id)
            if ok:
                show_message(self, "Excluído", msg, kind="success")
                self._load_users()
            else:
                show_message(self, "Erro", msg, kind="danger")
