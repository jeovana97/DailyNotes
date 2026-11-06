import unittest
import sys
import os
import tempfile
from database.migrations import init_db
from services.spellcheck_service import WindowsSpellCheckService, SpellingError


class TestWindowsSpellCheckService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "spell_test.db")
        init_db(self.db_path)
        self.service = WindowsSpellCheckService(
            preferred_languages=["pt-BR", "pt-PT", "en-US"],
            db_path=self.db_path,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_service_initialization(self):
        if sys.platform == "win32":
            self.assertTrue(self.service.is_available)
            self.assertIn(self.service.active_language, ["pt-BR", "pt-PT", "en-US"])
        else:
            self.assertFalse(self.service.is_available)

    def test_check_text_errors(self):
        if not self.service.is_available:
            self.skipTest("Windows Spell Checking API não disponível neste ambiente.")

        texto_com_erros = "Hoje fui ao mercadu e comprei pao e cafeh."
        errors = self.service.check_text(texto_com_erros)

        self.assertGreaterEqual(len(errors), 2)
        palavras_erradas = [err.word for err in errors]
        self.assertIn("mercadu", palavras_erradas)
        self.assertIn("pao", palavras_erradas)

        # Texto sem erros
        texto_correto = "Hoje fui ao mercado e comprei pão e café."
        errors_correto = self.service.check_text(texto_correto)
        self.assertEqual(len(errors_correto), 0)

    def test_suggestions(self):
        if not self.service.is_available:
            self.skipTest("Windows Spell Checking API não disponível neste ambiente.")

        sugestoes = self.service.get_suggestions("mercadu")
        self.assertIsInstance(sugestoes, list)
        self.assertIn("mercado", sugestoes)

    def test_ignore_word(self):
        if not self.service.is_available:
            self.skipTest("Windows Spell Checking API não disponível neste ambiente.")

        texto = "Esta palavra inventadaxpto nao existe."
        errors_antes = self.service.check_text(texto)
        self.assertTrue(any(e.word == "inventadaxpto" for e in errors_antes))

        self.service.ignore_word("inventadaxpto")
        errors_depois = self.service.check_text(texto)
        self.assertFalse(any(e.word == "inventadaxpto" for e in errors_depois))

    def test_custom_dictionary_add_list_and_remove(self):
        palavra_custom = "plsqlcustomxpto"

        # Adiciona palavra ao dicionário personalizado
        self.assertTrue(self.service.add_to_dictionary(palavra_custom))
        palavras = self.service.list_custom_words()
        self.assertIn(palavra_custom, palavras)

        if self.service.is_available:
            erros_com_palavra_no_dic = self.service.check_text(f"Teste de {palavra_custom} no texto.")
            self.assertFalse(any(e.word == palavra_custom for e in erros_com_palavra_no_dic))

        # Remove palavra do dicionário personalizado
        self.assertTrue(self.service.remove_from_dictionary(palavra_custom))
        palavras_apos_remocao = self.service.list_custom_words()
        self.assertNotIn(palavra_custom, palavras_apos_remocao)

        if self.service.is_available:
            erros_apos_remocao = self.service.check_text(f"Teste de {palavra_custom} no texto.")
            self.assertTrue(any(e.word == palavra_custom for e in erros_apos_remocao))


if __name__ == "__main__":
    unittest.main()
