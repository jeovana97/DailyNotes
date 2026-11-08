import os
import hashlib
import binascii
import logging
from typing import Optional, List, Tuple
from database.connection import get_db, get_connection
from models.user import User
from utils.date_utils import get_current_timestamp
from utils.validators import validate_username, validate_password

logger = logging.getLogger(__name__)

# Tenta carregar Argon2id; caso não esteja disponível, usa PBKDF2 com salt aleatório
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError
    _argon2_hasher = PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=1,
        hash_len=32
    )
    HAS_ARGON2 = True
except ImportError:
    HAS_ARGON2 = False
    logger.info("argon2-cffi não encontrado. Utilizando PBKDF2-HMAC-SHA256 como fallback.")


def hash_password(password: str) -> str:
    """
    Gera um hash seguro para a senha utilizando Argon2id (ou PBKDF2 se Argon2 indisponível).
    Nunca armazena senhas em texto puro.
    """
    if HAS_ARGON2:
        return _argon2_hasher.hash(password)
    else:
        # PBKDF2 com SHA256 e 100.000 iterações
        salt = os.urandom(16)
        iterations = 100000
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        salt_hex = binascii.hexlify(salt).decode("ascii")
        key_hex = binascii.hexlify(key).decode("ascii")
        return f"pbkdf2$sha256${iterations}${salt_hex}${key_hex}"


def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifica se a senha fornecida corresponde ao hash armazenado.
    Suporta tanto Argon2id quanto PBKDF2.
    """
    if not hashed_password or not password:
        return False

    if hashed_password.startswith("$argon2"):
        if HAS_ARGON2:
            try:
                return _argon2_hasher.verify(hashed_password, password)
            except (VerifyMismatchError, VerificationError):
                return False
        else:
            logger.error("Hash Argon2 detectado, mas a biblioteca argon2-cffi não está instalada.")
            return False

    elif hashed_password.startswith("pbkdf2$"):
        parts = hashed_password.split("$")
        if len(parts) == 5:
            _, algo, iterations, salt_hex, key_hex = parts
            salt = binascii.unhexlify(salt_hex)
            expected_key = binascii.unhexlify(key_hex)
            actual_key = hashlib.pbkdf2_hmac(
                algo, password.encode("utf-8"), salt, int(iterations)
            )
            return hashlib.compare_digest(actual_key, expected_key)

    return False


class AuthenticationService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def count_users(self) -> int:
        """Retorna o número total de usuários cadastrados no sistema."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def create_initial_admin(self, username: str, full_name: str, password: str) -> Tuple[Optional[User], str]:
        """
        Cria o primeiro usuário administrador do sistema durante o primeiro uso.
        Permitido somente quando não há usuários cadastrados.
        """
        if self.count_users() > 0:
            return None, "O administrador inicial já foi criado."

        valid_u, msg_u = validate_username(username)
        if not valid_u:
            return None, msg_u

        valid_p, msg_p = validate_password(password)
        if not valid_p:
            return None, msg_p

        if not full_name or not full_name.strip():
            return None, "O nome completo não pode estar em branco."

        now = get_current_timestamp()
        pwd_hash = hash_password(password)

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (username, full_name, password_hash, role, can_view_all_diaries, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 'admin', 1, 1, ?, ?)
                """,
                (username.strip(), full_name.strip(), pwd_hash, now, now),
            )
            user_id = cursor.lastrowid
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user_row = cursor.fetchone()
            return User.from_row(user_row), "Administrador inicial criado com sucesso!"

    def authenticate(self, username: str, password: str) -> Tuple[Optional[User], str]:
        """
        Autentica o usuário com base em seu login e senha.
        Retorna o objeto User autenticado ou mensagem de erro.
        """
        if not username or not password:
            return None, "Informe o usuário e a senha."

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),))
            row = cursor.fetchone()

            if not row:
                return None, "Usuário ou senha incorretos."

            user = User.from_row(row)

            if not user.is_active:
                return None, "Esta conta de usuário foi desativada pelo administrador."

            if not verify_password(password, user.password_hash):
                return None, "Usuário ou senha incorretos."

            return user, "Autenticação realizada com sucesso."
        finally:
            conn.close()

    def create_user(
        self,
        creator: User,
        username: str,
        full_name: str,
        password: str,
        role: str = "user",
        can_view_all_diaries: bool = False,
        is_active: bool = True,
    ) -> Tuple[Optional[User], str]:
        """
        Cria um novo usuário no sistema. Requer perfil de administrador.
        """
        if not creator.is_admin:
            return None, "Apenas administradores podem cadastrar novos usuários."

        valid_u, msg_u = validate_username(username)
        if not valid_u:
            return None, msg_u

        valid_p, msg_p = validate_password(password)
        if not valid_p:
            return None, msg_p

        if not full_name or not full_name.strip():
            return None, "O nome completo não pode estar em branco."

        role = "admin" if role == "admin" else "user"
        # Apenas admins podem ter permissão de ver outros diários
        can_view = 1 if (role == "admin" and can_view_all_diaries) else 0
        active_val = 1 if is_active else 0

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),))
            if cursor.fetchone():
                return None, f"O nome de usuário '{username.strip()}' já está em uso."

            now = get_current_timestamp()
            pwd_hash = hash_password(password)

            cursor.execute(
                """
                INSERT INTO users (username, full_name, password_hash, role, can_view_all_diaries, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (username.strip(), full_name.strip(), pwd_hash, role, can_view, active_val, now, now),
            )
            conn.commit()
            user_id = cursor.lastrowid
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            return User.from_row(cursor.fetchone()), "Usuário cadastrado com sucesso!"
        finally:
            conn.close()

    def register_user(
        self,
        username: str,
        full_name: str,
        password: str,
    ) -> Tuple[Optional[User], str]:
        """
        Cadastra um novo usuário no sistema (auto-cadastro pelo botão da tela de Login).
        Cria o usuário com perfil padrão ('user') e ativo.
        """
        valid_u, msg_u = validate_username(username)
        if not valid_u:
            return None, msg_u

        valid_p, msg_p = validate_password(password)
        if not valid_p:
            return None, msg_p

        if not full_name or not full_name.strip():
            return None, "O nome completo não pode estar em branco."

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),))
            if cursor.fetchone():
                return None, f"O nome de usuário '{username.strip()}' já está em uso."

            now = get_current_timestamp()
            pwd_hash = hash_password(password)

            cursor.execute(
                """
                INSERT INTO users (username, full_name, password_hash, role, can_view_all_diaries, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 'user', 0, 1, ?, ?)
                """,
                (username.strip(), full_name.strip(), pwd_hash, now, now),
            )
            conn.commit()
            user_id = cursor.lastrowid
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            return User.from_row(cursor.fetchone()), "Cadastro realizado com sucesso! Você já pode entrar."
        finally:
            conn.close()

    def update_password(self, user_id: int, current_password: str, new_password: str) -> Tuple[bool, str]:
        """Permite que o usuário conectado altere a sua própria senha."""
        valid_p, msg_p = validate_password(new_password)
        if not valid_p:
            return False, msg_p

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return False, "Usuário não encontrado."

            if not verify_password(current_password, row["password_hash"]):
                return False, "A senha atual informada está incorreta."

            now = get_current_timestamp()
            new_hash = hash_password(new_password)
            cursor.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (new_hash, now, user_id),
            )
            conn.commit()
            return True, "Senha alterada com sucesso!"
        finally:
            conn.close()

    def admin_reset_password(self, admin_user: User, target_user_id: int, new_password: str) -> Tuple[bool, str]:
        """Permite que um administrador redefina a senha de outro usuário."""
        if not admin_user.is_admin:
            return False, "Permissão negada. Apenas administradores podem redefinir senhas."

        valid_p, msg_p = validate_password(new_password)
        if not valid_p:
            return False, msg_p

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            now = get_current_timestamp()
            new_hash = hash_password(new_password)
            cursor.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (new_hash, now, target_user_id),
            )
            conn.commit()
            return True, "Senha redefinida com sucesso pelo administrador."
        finally:
            conn.close()

    def list_users(self, requester: User) -> List[User]:
        """Lista todos os usuários cadastrados. Apenas administradores."""
        if not requester.is_admin:
            return [requester]

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY full_name ASC")
            return [User.from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_user_permissions(
        self,
        requester: User,
        target_user_id: int,
        role: str,
        can_view_all_diaries: bool,
        is_active: bool,
    ) -> Tuple[bool, str]:
        """Atualiza permissões e status de ativação de um usuário."""
        if not requester.is_admin:
            return False, "Apenas administradores podem alterar permissões."

        # Se for o próprio administrador, não permite desativar a si mesmo ou remover o perfil de admin
        if requester.id == target_user_id:
            if role != "admin" or not is_active:
                return False, "Você não pode remover seu próprio perfil de administrador nem desativar sua conta."

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            now = get_current_timestamp()
            can_view = 1 if (role == "admin" and can_view_all_diaries) else 0
            cursor.execute(
                """
                UPDATE users
                SET role = ?, can_view_all_diaries = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (role, can_view, 1 if is_active else 0, now, target_user_id),
            )
            conn.commit()
            return True, "Permissões atualizadas com sucesso!"
        finally:
            conn.close()

    def delete_user(self, requester: User, target_user_id: int) -> Tuple[bool, str]:
        """Exclui um usuário e suas anotações associadas."""
        if not requester.is_admin:
            return False, "Apenas administradores podem excluir usuários."

        if requester.id == target_user_id:
            return False, "Você não pode excluir sua própria conta enquanto conectado."

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            # Verifica se é o último admin ativo
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?", (target_user_id,))
            remaining_admins = cursor.fetchone()[0]

            cursor.execute("SELECT role FROM users WHERE id = ?", (target_user_id,))
            user_to_delete = cursor.fetchone()
            if not user_to_delete:
                return False, "Usuário não encontrado."

            if user_to_delete["role"] == "admin" and remaining_admins == 0:
                return False, "Não é possível excluir o único administrador ativo do sistema."

            cursor.execute("DELETE FROM users WHERE id = ?", (target_user_id,))
            conn.commit()
            return True, "Usuário excluído com sucesso."
        finally:
            conn.close()

    def _ensure_theme_column(self, conn) -> None:
        """Garante que a coluna theme_preference exista na tabela users."""
        try:
            cursor = conn.execute("PRAGMA table_info(users)")
            cols = {row["name"] for row in cursor.fetchall()}
            if "theme_preference" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN theme_preference TEXT NOT NULL DEFAULT 'dark'")
        except Exception as e:
            logger.debug("Aviso ao verificar coluna theme_preference: %s", e)

    def update_theme_preference(self, user_id: int, theme: str) -> bool:
        """
        Salva a preferência de tema ('dark' ou 'light') do usuário no banco de dados
        para que seja mantida ao logar novamente.
        """
        normalized_theme = "light" if str(theme).lower() == "light" else "dark"
        now = get_current_timestamp()
        try:
            with get_db(self.db_path) as conn:
                self._ensure_theme_column(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET theme_preference = ?, updated_at = ? WHERE id = ?",
                    (normalized_theme, now, user_id),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.warning("Erro ao salvar preferência de tema do usuário: %s", e)
            return False

    def get_last_theme_preference(self) -> str:
        """
        Retorna o último tema escolhido no sistema (para inicializar a tela de login),
        ou 'dark' como padrão.
        """
        conn = get_connection(self.db_path)
        try:
            self._ensure_theme_column(conn)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT theme_preference FROM users ORDER BY updated_at DESC, id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row and row["theme_preference"]:
                return "light" if str(row["theme_preference"]).lower() == "light" else "dark"
            return "dark"
        except Exception:
            return "dark"
        finally:
            conn.close()
