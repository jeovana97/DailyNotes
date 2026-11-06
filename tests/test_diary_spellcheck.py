import unittest
import tempfile
import os
import customtkinter as ctk
from database.migrations import init_db
from models.user import User
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService
from services.backup_service import BackupService
from services.spellcheck_service import WindowsSpellCheckService
from views.diary_view import DiaryView


class TestDiarySpellCheckIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctk.set_appearance_mode("Dark")
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_spell_diary.db")
        init_db(self.db_path)

        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.diary_service = DiaryService(db_path=self.db_path)
        self.backup_service = BackupService(db_path=self.db_path)
        self.spell_service = WindowsSpellCheckService()

        self.user, _ = self.auth_service.create_initial_admin("spell_tester", "Spell Tester", "pass1234")

        self.view = DiaryView(
            self.root,
            current_user=self.user,
            diary_service=self.diary_service,
            auth_service=self.auth_service,
            backup_service=self.backup_service,
            spell_service=self.spell_service,
        )
        self.view.pack()

    def tearDown(self):
        self.view.destroy()
        self.temp_dir.cleanup()

    def test_spellcheck_highlights_and_status(self):
        if not self.spell_service.is_available:
            self.skipTest("Windows Spell Checking API não disponível.")

        # Insere texto com erro
        self.view.txt_content.delete("1.0", "end")
        self.view.txt_content.insert("1.0", "Hoje fui ao mercadu comprar pao.")
        self.view._run_spellcheck()

        # Verifica se as tags foram aplicadas
        ranges = self.view.txt_content._textbox.tag_ranges("spelling_error")
        self.assertGreater(len(ranges), 0)

        # Status deve indicar erros encontrados
        status_text = self.view.btn_spell_status.cget("text")
        self.assertIn("erro", status_text)

    def test_word_replacement(self):
        if not self.spell_service.is_available:
            self.skipTest("Windows Spell Checking API não disponível.")

        self.view.txt_content.delete("1.0", "end")
        self.view.txt_content.insert("1.0", "Eu comprei mercadu fresco.")
        self.view._run_spellcheck()

        # Localiza o range do erro 'mercadu'
        ranges = self.view.txt_content._textbox.tag_ranges("spelling_error")
        self.assertGreaterEqual(len(ranges), 2)
        start_idx, end_idx = ranges[0], ranges[1]
        err_word = self.view.txt_content._textbox.get(start_idx, end_idx)
        self.assertEqual(err_word, "mercadu")

        # Substitui pela sugestão
        self.view._replace_spelling_error(start_idx, end_idx, "mercado")

        conteudo_atual = self.view.txt_content.get("1.0", "end-1c")
        self.assertIn("mercado fresco", conteudo_atual)
        self.assertNotIn("mercadu", conteudo_atual)

    def test_toggle_spellcheck(self):
        if not self.spell_service.is_available:
            self.skipTest("Windows Spell Checking API não disponível.")

        self.view.txt_content.delete("1.0", "end")
        self.view.txt_content.insert("1.0", "Texto com mercadu e cafeh.")
        self.view._run_spellcheck()

        self.assertTrue(self.view.spellcheck_enabled.get())
        self.assertGreater(len(self.view.txt_content._textbox.tag_ranges("spelling_error")), 0)

        # Desativa o corretor
        self.view._toggle_spellcheck()
        self.assertFalse(self.view.spellcheck_enabled.get())
        self.assertEqual(len(self.view.txt_content._textbox.tag_ranges("spelling_error")), 0)
        self.assertIn("Desativado", self.view.btn_spell_status.cget("text"))

        # Reativa o corretor
        self.view._toggle_spellcheck()
        self.assertTrue(self.view.spellcheck_enabled.get())
        self.assertGreater(len(self.view.txt_content._textbox.tag_ranges("spelling_error")), 0)


if __name__ == "__main__":
    unittest.main()
