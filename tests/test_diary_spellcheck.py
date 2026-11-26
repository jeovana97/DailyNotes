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

    def test_f5_inserts_current_datetime_and_supports_undo(self):
        import re
        from utils.syntax_highlighter import perform_undo, reset_undo_stack

        self.view.txt_content.delete("1.0", "end")
        self.view.txt_content.insert("1.0", "Registro: ")
        self.view.txt_content._textbox.mark_set("insert", "end-1c")
        reset_undo_stack(self.view.txt_content)

        # Aciona F5
        self.view.editor_assist._on_f5()
        text_after = self.view.txt_content.get("1.0", "end-1c")
        self.assertRegex(text_after, r"^Registro: \d{2}/\d{2}/\d{4} \d{2}:\d{2}$")

        # Ctrl+Z desfaz a inserção de data/hora
        self.assertTrue(perform_undo(self.view.txt_content))
        self.assertEqual(self.view.txt_content.get("1.0", "end-1c"), "Registro: ")

    def test_ctrl_space_corrects_end_of_text_and_completes_suggestions(self):
        if not self.spell_service.is_available:
            self.skipTest("Windows Spell Checking API não disponível.")

        from utils.syntax_highlighter import perform_undo, reset_undo_stack
        from utils.rich_text import TAG_BOLD

        tb = self.view.txt_content._textbox

        # 1. Erro ortográfico colado no cursor no fim do texto (preservando negrito)
        self.view.txt_content.delete("1.0", "end")
        self.view.txt_content.insert("1.0", "Hoje fui ao mercadu")
        tb.tag_add("sel", "1.12", "1.19")
        self.view.rich_text.toggle_bold()
        tb.tag_remove("sel", "1.0", "end")
        tb.mark_set("insert", "end-1c")
        reset_undo_stack(self.view.txt_content)

        res1 = self.view.editor_assist.trigger_smart_complete_or_correct()
        self.assertIsNotNone(res1)
        self.assertEqual(self.view.txt_content.get("1.0", "end-1c"), "Hoje fui ao mercado")
        self.assertIn(TAG_BOLD, tb.tag_names("1.13"))

        # Ctrl+Z desfaz a correção do Ctrl+Space
        self.assertTrue(perform_undo(self.view.txt_content))
        self.assertEqual(self.view.txt_content.get("1.0", "end-1c"), "Hoje fui ao mercadu")

        # 2. Erro ortográfico no fim do texto seguido de ponto final e espaço
        self.view.txt_content.delete("1.0", "end")
        self.view.txt_content.insert("1.0", "Favor revisar o relatorio. ")
        tb.mark_set("insert", "end-1c")
        reset_undo_stack(self.view.txt_content)

        res2 = self.view.editor_assist.trigger_smart_complete_or_correct()
        self.assertIsNotNone(res2)
        self.assertEqual(self.view.txt_content.get("1.0", "end-1c"), "Favor revisar o relatório. ")

        # 3. Completar palavra sugerida pelo corretor e ciclar sugestões com segundo Ctrl+Space
        self.view.txt_content.delete("1.0", "end")
        self.view.txt_content.insert("1.0", "Muito obrigad")
        tb.mark_set("insert", "end-1c")
        reset_undo_stack(self.view.txt_content)

        res3 = self.view.editor_assist.trigger_smart_complete_or_correct()
        self.assertIsNotNone(res3)
        first_applied = self.view.txt_content.get("1.0", "end-1c")
        self.assertIn(first_applied, ("Muito obrigado", "Muito obrigada"))

        # Segundo Ctrl+Space consecutivo alterna para a próxima sugestão
        res3_next = self.view.editor_assist.trigger_smart_complete_or_correct()
        self.assertIsNotNone(res3_next)
        second_applied = self.view.txt_content.get("1.0", "end-1c")
        self.assertNotEqual(second_applied, first_applied)

        # 4. Completar frase já escrita anteriormente na nota
        self.view.txt_content.delete("1.0", "end")
        self.view.txt_content.insert(
            "1.0",
            "Relatório de Emissão de Nota Fiscal\nRelatório de Em",
        )
        tb.mark_set("insert", "end-1c")
        reset_undo_stack(self.view.txt_content)

        res4 = self.view.editor_assist.trigger_smart_complete_or_correct()
        self.assertIsNotNone(res4)
        self.assertEqual(
            self.view.txt_content.get("1.0", "end-1c"),
            "Relatório de Emissão de Nota Fiscal\nRelatório de Emissão de Nota Fiscal",
        )


if __name__ == "__main__":
    unittest.main()
