import unittest
import tempfile
import os
from database.migrations import init_db
from services.authentication_service import AuthenticationService, hash_password, verify_password


class TestAuthenticationService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_auth.db")
        init_db(self.db_path)
        self.auth_service = AuthenticationService(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_admin_creation(self):
        # 1. Banco começa sem usuários
        self.assertEqual(self.auth_service.count_users(), 0)

        # 2. Cria primeiro administrador
        admin, msg = self.auth_service.create_initial_admin("admin", "Administrador do Sistema", "senha1234")
        self.assertIsNotNone(admin)
        self.assertEqual(admin.username, "admin")
        self.assertTrue(admin.is_admin)
        self.assertTrue(admin.can_view_other_diaries)
        self.assertEqual(self.auth_service.count_users(), 1)

        # 3. Segunda tentativa deve falhar
        admin2, msg2 = self.auth_service.create_initial_admin("admin2", "Outro Admin", "senha1234")
        self.assertIsNone(admin2)

    def test_password_hash_security(self):
        raw_pass = "minhaSenhaForte2026"
        hashed = hash_password(raw_pass)

        # A senha nunca deve estar em texto puro
        self.assertNotIn(raw_pass, hashed)
        # O hash deve ser válido
        self.assertTrue(verify_password(raw_pass, hashed))
        # Senha incorreta deve falhar
        self.assertFalse(verify_password("senhaErrada", hashed))

    def test_user_authentication(self):
        admin, _ = self.auth_service.create_initial_admin("admin", "Admin", "senhaForte")

        # Login com sucesso
        user, msg = self.auth_service.authenticate("admin", "senhaForte")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "admin")

        # Login com senha incorreta
        user_err, msg_err = self.auth_service.authenticate("admin", "senhaIncorreta")
        self.assertIsNone(user_err)

        # Login com usuário inexistente
        user_none, _ = self.auth_service.authenticate("usuarioInexistente", "senhaForte")
        self.assertIsNone(user_none)

    def test_create_and_manage_users(self):
        admin, _ = self.auth_service.create_initial_admin("admin", "Admin", "adminPass")

        # Cria usuário comum
        colab, msg = self.auth_service.create_user(
            creator=admin,
            username="colaborador",
            full_name="Carlos Silva",
            password="userPass123",
            role="user",
            can_view_all_diaries=False,
        )
        self.assertIsNotNone(colab)
        self.assertEqual(colab.role, "user")
        self.assertFalse(colab.is_admin)
        self.assertFalse(colab.can_view_other_diaries)

        # Usuário comum tenta criar outro usuário (deve falhar)
        tentativa, msg_err = self.auth_service.create_user(
            creator=colab,
            username="outro",
            full_name="Outro Usuário",
            password="outraSenha123",
        )
        self.assertIsNone(tentativa)

    def test_update_password(self):
        admin, _ = self.auth_service.create_initial_admin("admin", "Admin", "senhaAntiga123")

        # Troca com senha atual errada
        ok, msg = self.auth_service.update_password(admin.id, "senhaErrada", "novaSenha123")
        self.assertFalse(ok)

        # Troca com senha atual correta
        ok, msg = self.auth_service.update_password(admin.id, "senhaAntiga123", "novaSenha123")
        self.assertTrue(ok)

        # Verifica se o login funciona com a nova senha
        user, _ = self.auth_service.authenticate("admin", "novaSenha123")
        self.assertIsNotNone(user)

    def test_theme_preference_persistence_on_relogin(self):
        admin, _ = self.auth_service.create_initial_admin("admin", "Admin", "senha1234")
        self.assertEqual(admin.theme_preference, "dark")

        # Usuário escolhe o Modo Claro
        self.assertTrue(self.auth_service.update_theme_preference(admin.id, "light"))
        self.assertEqual(self.auth_service.get_last_theme_preference(), "light")

        # Ao logar novamente, deve retornar 'light'
        relogged_user, _ = self.auth_service.authenticate("admin", "senha1234")
        self.assertIsNotNone(relogged_user)
        self.assertEqual(relogged_user.theme_preference, "light")

        # Usuário volta para o Modo Escuro
        self.assertTrue(self.auth_service.update_theme_preference(admin.id, "dark"))
        relogged_dark, _ = self.auth_service.authenticate("admin", "senha1234")
        self.assertEqual(relogged_dark.theme_preference, "dark")


if __name__ == "__main__":
    unittest.main()
