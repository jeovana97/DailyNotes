import unittest
import tempfile
import os
from database.migrations import init_db
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService
from services.import_service import ImportService, ConflictResolution


class TestImportService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_import.db")
        init_db(self.db_path)
        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.diary_service = DiaryService(db_path=self.db_path)
        self.import_service = ImportService(diary_service=self.diary_service)

        self.user, _ = self.auth_service.create_initial_admin("user_import", "Usuário Importador", "senha1234")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_single_utf8_file(self):
        # Cria arquivo no formato padrão "01 10 2026.txt"
        file_path = os.path.join(self.temp_dir.name, "01 10 2026.txt")
        content = "Reunião de início de mês. Metas traçadas com acentuação e pontuação: ação, coração, café."
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        res = self.import_service.import_file(file_path, self.user.id)
        self.assertEqual(res["status"], "imported")
        self.assertEqual(res["date_iso"], "2026-10-01")

        entry = self.diary_service.get_entry_by_date(self.user.id, "2026-10-01")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.content, content)

    def test_import_windows_1252_encoding(self):
        # Cria arquivo em Windows-1252 (ANSI)
        file_path = os.path.join(self.temp_dir.name, "02 10 2026.txt")
        content = "Anotação gravada em ANSI: Atenção às configurações de produção!"
        with open(file_path, "w", encoding="cp1252") as f:
            f.write(content)

        res = self.import_service.import_file(file_path, self.user.id)
        self.assertEqual(res["status"], "imported")

        entry = self.diary_service.get_entry_by_date(self.user.id, "2026-10-02")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.content, content)

    def test_conflict_resolutions(self):
        date_iso = "2026-10-03"
        # Cria anotação prévia
        self.diary_service.save_entry(self.user.id, date_iso, "Conteúdo original pré-existente.")

        file_path = os.path.join(self.temp_dir.name, "03 10 2026.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("Novo conteúdo importado do arquivo.")

        # 1. Modo SKIP (ignorar)
        res_skip = self.import_service.import_file(
            file_path, self.user.id, conflict_resolution=ConflictResolution.SKIP
        )
        self.assertEqual(res_skip["status"], "skipped")
        entry = self.diary_service.get_entry_by_date(self.user.id, date_iso)
        self.assertEqual(entry.content, "Conteúdo original pré-existente.")

        # 2. Modo MERGE (mesclar)
        res_merge = self.import_service.import_file(
            file_path, self.user.id, conflict_resolution=ConflictResolution.MERGE
        )
        self.assertEqual(res_merge["status"], "imported")
        entry_merged = self.diary_service.get_entry_by_date(self.user.id, date_iso)
        self.assertIn("Conteúdo original pré-existente.", entry_merged.content)
        self.assertIn("Novo conteúdo importado do arquivo.", entry_merged.content)

        # 3. Modo REPLACE (substituir)
        res_replace = self.import_service.import_file(
            file_path, self.user.id, conflict_resolution=ConflictResolution.REPLACE
        )
        self.assertEqual(res_replace["status"], "imported")
        entry_replaced = self.diary_service.get_entry_by_date(self.user.id, date_iso)
        self.assertEqual(entry_replaced.content, "Novo conteúdo importado do arquivo.")

    def test_batch_folder_import(self):
        folder = os.path.join(self.temp_dir.name, "batch_notes")
        os.makedirs(folder, exist_ok=True)

        # Cria 3 arquivos válidos e 1 inválido
        with open(os.path.join(folder, "10 10 2026.txt"), "w", encoding="utf-8") as f:
            f.write("Nota dia 10")
        with open(os.path.join(folder, "11 10 2026.txt"), "w", encoding="utf-8") as f:
            f.write("Nota dia 11")
        with open(os.path.join(folder, "12 10 2026.txt"), "w", encoding="utf-8") as f:
            f.write("Nota dia 12")
        with open(os.path.join(folder, "arquivo_sem_data.txt"), "w", encoding="utf-8") as f:
            f.write("Ignorado")

        report = self.import_service.import_folder(folder, self.user.id)
        self.assertEqual(report["total"], 4)
        self.assertEqual(report["imported"], 3)
        self.assertEqual(report["errors"], 1)

        # Verifica registro do último TXT importado
        last_txt = self.import_service.get_last_imported_txt(self.user.id)
        self.assertIsNotNone(last_txt)
        self.assertEqual(last_txt["filename"], "12 10 2026.txt")
        self.assertEqual(last_txt["entry_date"], "2026-10-12")
        self.assertEqual(last_txt["date_br"], "12/10/2026")

    def test_import_notes_into_folders_without_date_format(self):
        # Cria uma pasta de destino
        folder_obj = self.import_service.note_service.create_folder(self.user.id, "Consultas SQL e XML")

        # Cria arquivos TXT com nomes livres (sem formato de data)
        sql_file = os.path.join(self.temp_dir.name, "consulta_clientes_ativos.txt")
        with open(sql_file, "w", encoding="utf-8") as f:
            f.write("select id, nome from clientes where ativo = 1;")

        xml_file = os.path.join(self.temp_dir.name, "ERRO XML NFE.txt")
        with open(xml_file, "w", encoding="utf-8") as f:
            f.write("<nfeProc><NFe><infNFe Id='NFe1'><ide><cUF>35</cUF></ide></infNFe></NFe></nfeProc>")

        res1 = self.import_service.import_note_file(
            file_path=sql_file,
            user_id=self.user.id,
            folder_id=folder_obj.id,
        )
        self.assertEqual(res1["status"], "imported")
        self.assertEqual(res1["folder_id"], folder_obj.id)
        self.assertIsNotNone(res1["note_id"])

        res2 = self.import_service.import_note_file(
            file_path=xml_file,
            user_id=self.user.id,
            folder_id=folder_obj.id,
        )
        self.assertEqual(res2["status"], "imported")

        # Verifica se as notas foram salvas dentro da pasta escolhida
        notes_in_folder = self.import_service.note_service.list_notes(
            self.user.id, folder_id=folder_obj.id, all_notes=False
        )
        self.assertEqual(len(notes_in_folder), 2)
        titles = {n.title for n in notes_in_folder}
        self.assertEqual(titles, {"consulta_clientes_ativos", "ERRO XML NFE"})

        # Verifica o último TXT importado apontando para a pasta
        last_info = self.import_service.get_last_imported_txt(self.user.id)
        self.assertIsNotNone(last_info)
        self.assertEqual(last_info["target_type"], "note")
        self.assertEqual(last_info["filename"], "ERRO XML NFE.txt")
        self.assertEqual(last_info["folder_id"], folder_obj.id)
        self.assertEqual(last_info["folder_name"], "Consultas SQL e XML")

    def test_import_folder_to_notes_batch(self):
        src_dir = os.path.join(self.temp_dir.name, "notas_avulsas")
        os.makedirs(src_dir, exist_ok=True)

        with open(os.path.join(src_dir, "SENHAS CIS.txt"), "w", encoding="utf-8") as f:
            f.write("admin / 1234")
        with open(os.path.join(src_dir, "SESSAO PRESA.txt"), "w", encoding="utf-8") as f:
            f.write("ALTER SYSTEM KILL SESSION;")

        dest_folder = self.import_service.note_service.create_folder(self.user.id, "Importadas")
        report = self.import_service.import_folder_to_notes(
            folder_path=src_dir,
            user_id=self.user.id,
            target_folder_id=dest_folder.id,
        )
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["imported"], 2)
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["target_folder_name"], "Importadas")


if __name__ == "__main__":
    unittest.main()
