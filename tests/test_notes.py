import os
import tempfile
import unittest

from database.migrations import init_db
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService
from services.note_service import NoteService
from services.search_service import SearchService


class TestNotesAndFolders(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "notes_test.db")
        init_db(self.db_path)

        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.note_service = NoteService(db_path=self.db_path)
        self.diary_service = DiaryService(db_path=self.db_path)
        self.search_service = SearchService(db_path=self.db_path)

        self.user, _ = self.auth_service.create_initial_admin(
            "admin_notes", "Admin Notas", "senha123"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_folders_and_subfolders_hierarchy(self):
        # Cria pasta raiz e subpastas em múltiplos níveis
        root_folder = self.note_service.create_folder(self.user.id, "Banco de Dados")
        sub_folder = self.note_service.create_folder(
            self.user.id, "Oracle PL/SQL", parent_id=root_folder.id
        )
        deep_folder = self.note_service.create_folder(
            self.user.id, "Scripts de Produção", parent_id=sub_folder.id
        )

        path_map = self.note_service.get_folder_path_map(self.user.id)
        self.assertEqual(path_map[root_folder.id], "Banco de Dados")
        self.assertEqual(path_map[sub_folder.id], "Banco de Dados / Oracle PL/SQL")
        self.assertEqual(
            path_map[deep_folder.id],
            "Banco de Dados / Oracle PL/SQL / Scripts de Produção",
        )

        # Impede ciclo ao tentar mover pasta pai para dentro de subpasta descendente
        with self.assertRaises(ValueError):
            self.note_service.move_folder(
                self.user.id, root_folder.id, new_parent_id=deep_folder.id
            )

    def test_save_notes_and_search_by_title_only(self):
        f_fiscal = self.note_service.create_folder(self.user.id, "Fiscal")
        f_nfe = self.note_service.create_folder(
            self.user.id, "NFe", parent_id=f_fiscal.id
        )

        n1 = self.note_service.save_note(
            self.user.id,
            title="erro VALOR DA NF DEFERE DO RECEBIMENTO",
            content="Verificar divergência nos centavos dos itens.",
            folder_id=f_nfe.id,
        )
        n2 = self.note_service.save_note(
            self.user.id,
            title="SENHAS CIS",
            content="Acesso restrito ao ambiente homologação.",
            folder_id=None,
        )
        n3 = self.note_service.save_note(
            self.user.id,
            title="SESSÇÃO PRESA NO BANCO",
            content="ALTER SYSTEM KILL SESSION 'sid,serial#';",
            folder_id=f_fiscal.id,
        )

        # Pesquisa pelo nome da nota (insensível a maiúsculas e acentos)
        res_nf = self.note_service.search_notes_by_title(self.user.id, "valor da nf")
        self.assertEqual(len(res_nf), 1)
        self.assertEqual(res_nf[0].id, n1.id)

        res_sessao = self.note_service.search_notes_by_title(self.user.id, "sesscao presa")
        self.assertEqual(len(res_sessao), 1)
        self.assertEqual(res_sessao[0].id, n3.id)

        # Palavra que existe apenas no conteúdo (e não no nome da nota) não deve retornar na busca por nome
        res_content_only = self.note_service.search_notes_by_title(self.user.id, "homologacao")
        self.assertEqual(len(res_content_only), 0)

    def test_notes_excluded_from_advanced_diary_search(self):
        # Salva nota no novo menu de notas
        self.note_service.save_note(
            self.user.id,
            title="leiaute plsql exclusivo",
            content="Bloco PLSQL de teste isolado da pesquisa avançada.",
        )

        # Salva anotação comum no diário
        self.diary_service.save_entry(
            self.user.id,
            "2026-11-04",
            "Anotação normal do diário sobre atendimento.",
        )

        # A Pesquisa Avançada NÃO deve retornar notas do menu Notas & Pastas
        adv_results_title = self.search_service.search_diaries(
            requester=self.user, query="leiaute plsql"
        )
        self.assertEqual(len(adv_results_title), 0)

        adv_results_body = self.search_service.search_diaries(
            requester=self.user, query="isolado da pesquisa"
        )
        self.assertEqual(len(adv_results_body), 0)

        # Mas continua encontrando normalmente o diário por data
        adv_diary = self.search_service.search_diaries(
            requester=self.user, query="atendimento"
        )
        self.assertEqual(len(adv_diary), 1)

    def test_delete_folder_cascades_subfolders_and_notes(self):
        parent = self.note_service.create_folder(self.user.id, "Projetos")
        sub = self.note_service.create_folder(self.user.id, "Subprojeto", parent_id=parent.id)
        note = self.note_service.save_note(
            self.user.id, title="KEYGEN", content="Chave de teste", folder_id=sub.id
        )

        self.assertTrue(self.note_service.delete_folder(self.user.id, parent.id))
        self.assertIsNone(self.note_service.get_folder(self.user.id, sub.id))
        self.assertIsNone(self.note_service.get_note(self.user.id, note.id))

    def test_move_note_between_folders_and_root(self):
        f_admin = self.note_service.create_folder(self.user.id, "Administrativo")
        f_scripts = self.note_service.create_folder(self.user.id, "Scripts")

        # Cria nota na Raiz (sem pasta)
        note = self.note_service.save_note(
            self.user.id,
            title="ANALYZE",
            content="EXEC DBMS_STATS.GATHER_SCHEMA_STATS;",
            folder_id=None,
        )
        self.assertIsNone(note.folder_id)

        # Move para a pasta Scripts
        moved_to_scripts = self.note_service.move_note(
            self.user.id, note.id, target_folder_id=f_scripts.id
        )
        self.assertEqual(moved_to_scripts.folder_id, f_scripts.id)
        self.assertEqual(moved_to_scripts.folder_name, "Scripts")

        # Move para a pasta Administrativo
        moved_to_admin = self.note_service.move_note(
            self.user.id, note.id, target_folder_id=f_admin.id
        )
        self.assertEqual(moved_to_admin.folder_id, f_admin.id)
        self.assertEqual(moved_to_admin.folder_name, "Administrativo")

        # Move de volta para a Raiz (Sem pasta)
        moved_to_root = self.note_service.move_note(
            self.user.id, note.id, target_folder_id=None
        )
        self.assertIsNone(moved_to_root.folder_id)

    def test_xml_and_sql_formatting(self):
        from utils.syntax_highlighter import format_xml_string, format_sql_string

        raw_xml = '<nfeProc versao="4.00"><NFe><infNFe Id="NFe123"><ide><cUF>35</cUF></ide></infNFe></NFe></nfeProc>'
        formatted_xml = format_xml_string(raw_xml)
        self.assertIn("  <NFe>", formatted_xml)
        self.assertIn("    <infNFe Id=\"NFe123\">", formatted_xml)
        self.assertIn("        <cUF>35</cUF>", formatted_xml)

        raw_sql = "select id, nome, count(*) from clientes where status = 'ativo' and valor >= 100 group by id, nome order by nome asc;"
        formatted_sql = format_sql_string(raw_sql)
        self.assertIn("SELECT id, nome, COUNT(*)", formatted_sql)
        self.assertIn("FROM clientes", formatted_sql)
        self.assertIn("WHERE status = 'ativo' AND valor >= 100", formatted_sql)
        self.assertIn("GROUP BY id, nome", formatted_sql)
        self.assertIn("ORDER BY nome ASC;", formatted_sql)


if __name__ == "__main__":
    unittest.main()

