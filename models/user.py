from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: int
    username: str
    full_name: str
    password_hash: str
    role: str = "user"  # 'admin' ou 'user'
    can_view_all_diaries: bool = False
    is_active: bool = True
    theme_preference: str = "dark"  # 'dark' ou 'light'
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_admin(self) -> bool:
        """Verifica se o usuário possui perfil de administrador."""
        return self.role == "admin"

    @property
    def can_view_other_diaries(self) -> bool:
        """
        Retorna True se o usuário pode consultar diários de outros usuários.
        Requisito: O administrador poderá gerenciar usuários e, caso autorizado,
        consultar os diários de outros usuários. Essa permissão deve ser controlada explicitamente.
        """
        return self.is_admin and self.can_view_all_diaries

    @classmethod
    def from_row(cls, row) -> "User":
        """Instancia um User a partir de uma linha do sqlite3.Row."""
        keys = row.keys()
        raw_theme = row["theme_preference"] if "theme_preference" in keys and row["theme_preference"] else "dark"
        theme = "light" if str(raw_theme).lower() == "light" else "dark"
        return cls(
            id=row["id"],
            username=row["username"],
            full_name=row["full_name"],
            password_hash=row["password_hash"],
            role=row["role"],
            can_view_all_diaries=bool(row["can_view_all_diaries"]),
            is_active=bool(row["is_active"]),
            theme_preference=theme,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
