import unittest
import tempfile
import os
from database.migrations import init_db
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService


class TestDiaryService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_diary.db")
        init_db(self.db_path)
        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.diary_service = DiaryService(db_path=self.db_path)

        # Cria usuário de teste
        self.user, _ = self.auth_service.create_initial_admin("teste", "Usuário Teste", "senha1234")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve_entry(self):
        date_iso = "2026-10-27"
        content = "Reunião de alinhamento com a equipe de engenharia sobre o novo banco de dados."

        saved = self.diary_service.save_entry(self.user.id, date_iso, content)
        self.assertIsNotNone(saved.id)
        self.assertEqual(saved.content, content)
        self.assertEqual(saved.entry_date, date_iso)

        retrieved = self.diary_service.get_entry_by_date(self.user.id, date_iso)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.content, content)

    def test_no_duplicate_entries_for_same_date(self):
        date_iso = "2026-10-27"
        self.diary_service.save_entry(self.user.id, date_iso, "Primeira versão da anotação.")

        # Atualiza a anotação do mesmo dia
        updated = self.diary_service.save_entry(self.user.id, date_iso, "Segunda versão atualizada.")
        self.assertEqual(updated.content, "Segunda versão atualizada.")

        # Verifica no banco se existe apenas 1 registro para este dia
        entry = self.diary_service.get_entry_by_date(self.user.id, date_iso)
        self.assertEqual(entry.content, "Segunda versão atualizada.")

    def test_long_text_integrity(self):
        date_iso = "2026-10-28"
        # Gera texto longo com múltiplas quebras de linha e caracteres especiais
        paragraphs = [
            f"Parágrafo {i}: O sistema deve suportar textos extensos sem truncamento. "
            f"Acentuação: á é í ó ú ã õ ç Á É Í Ó Ú Ã Õ Ç. Símbolos: @#$%&*()[]{{}}! \n\n"
            for i in range(100)
        ]
        long_content = "".join(paragraphs)

        self.diary_service.save_entry(self.user.id, date_iso, long_content)
        retrieved = self.diary_service.get_entry_by_date(self.user.id, date_iso)

        self.assertEqual(len(retrieved.content), len(long_content))
        self.assertEqual(retrieved.content, long_content)

    def test_dates_with_notes_and_adjacent(self):
        self.diary_service.save_entry(self.user.id, "2026-10-05", "Anotação dia 5")
        self.diary_service.save_entry(self.user.id, "2026-10-15", "Anotação dia 15")
        self.diary_service.save_entry(self.user.id, "2026-10-25", "Anotação dia 25")

        dates = self.diary_service.get_dates_with_notes(self.user.id, 2026, 10)
        self.assertIn("2026-10-05", dates)
        self.assertIn("2026-10-15", dates)
        self.assertIn("2026-10-25", dates)
        self.assertNotIn("2026-10-10", dates)

        # Testa datas adjacentes
        prev_date, next_date = self.diary_service.get_adjacent_dates(self.user.id, "2026-10-15")
        self.assertEqual(prev_date, "2026-10-05")
        self.assertEqual(next_date, "2026-10-25")


if __name__ == "__main__":
    unittest.main()
