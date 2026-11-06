import unittest
import tempfile
import os
from database.migrations import init_db
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService
from services.search_service import SearchService


class TestSearchService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_search.db")
        init_db(self.db_path)
        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.diary_service = DiaryService(db_path=self.db_path)
        self.search_service = SearchService(db_path=self.db_path)

        # Admin com permissão para ver todos
        self.admin, _ = self.auth_service.create_initial_admin("admin", "Admin Geral", "admin123")

        # Usuário regular (sem permissão de ver outros)
        self.user1, _ = self.auth_service.create_user(
            creator=self.admin,
            username="joao",
            full_name="João Silva",
            password="senhaJoao123",
            role="user",
            can_view_all_diaries=False,
        )

        # Usuário 2
        self.user2, _ = self.auth_service.create_user(
            creator=self.admin,
            username="maria",
            full_name="Maria Santos",
            password="senhaMaria123",
            role="user",
            can_view_all_diaries=False,
        )

        # Popula diários
        self.diary_service.save_entry(
            self.user1.id,
            "2026-09-10",
            "Foi identificado um erro na emissão da nota fiscal para o cliente Acme Corp."
        )
        self.diary_service.save_entry(
            self.user1.id,
            "2026-10-15",
            "Atendimento ao chamado #8492. Executado comando SQL de otimização de índices."
        )
        self.diary_service.save_entry(
            self.user2.id,
            "2026-10-20",
            "Anotação confidencial da Maria sobre planejamento orçamentário do cliente Beta."
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_search_word_case_insensitive(self):
        # Pesquisa por "cliente" em maiúsculas
        results = self.search_service.search_diaries(requester=self.user1, query="CLIENTE")
        self.assertEqual(len(results), 1)
        self.assertIn("Acme Corp", results[0]["content"])

    def test_search_compound_phrase(self):
        # Pesquisa por expressão exata "erro na emissão"
        results = self.search_service.search_diaries(requester=self.user1, query="erro na emissão")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["entry_date"], "2026-09-10")

    def test_search_accent_insensitive(self):
        # Usuário pesquisa "emissao" (sem acento) e deve encontrar "emissão"
        results = self.search_service.search_diaries(requester=self.user1, query="emissao")
        self.assertEqual(len(results), 1)
        self.assertIn("emissão", results[0]["content"])

        # Pesquisa "otimizacao" (sem acento e cedilha) para encontrar "otimização"
        results_opt = self.search_service.search_diaries(requester=self.user1, query="otimizacao")
        self.assertEqual(len(results_opt), 1)
        self.assertIn("otimização", results_opt[0]["content"])

    def test_search_date_range(self):
        # Pesquisa entre 01/10/2026 e 31/10/2026
        results = self.search_service.search_diaries(
            requester=self.user1,
            start_date="2026-10-01",
            end_date="2026-10-31"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["entry_date"], "2026-10-15")

    def test_search_exact_date(self):
        results = self.search_service.search_diaries(requester=self.user1, exact_date="2026-09-10")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["entry_date"], "2026-09-10")

    def test_permission_isolation(self):
        # João pesquisa por "cliente" e só deve ver a sua própria anotação (não a de Maria)
        results_joao = self.search_service.search_diaries(requester=self.user1, query="cliente")
        self.assertEqual(len(results_joao), 1)
        self.assertEqual(results_joao[0]["username"], "joao")

        # Administrador pesquisa por "cliente" e pode ver ambas
        results_admin = self.search_service.search_diaries(requester=self.admin, query="cliente")
        self.assertEqual(len(results_admin), 2)


if __name__ == "__main__":
    unittest.main()
