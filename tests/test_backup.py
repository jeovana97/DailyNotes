import unittest
import tempfile
import os
import csv
from database.migrations import init_db
from database.connection import get_connection
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService
from services.backup_service import BackupService


class TestBackupService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_backup.db")
        init_db(self.db_path)
        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.diary_service = DiaryService(db_path=self.db_path)
        self.backup_service = BackupService(db_path=self.db_path)

        self.user, _ = self.auth_service.create_initial_admin("admin_backup", "Admin Backup", "senha1234")
        self.diary_service.save_entry(self.user.id, "2026-10-27", "Anotação antes do backup.")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_backup_and_restore(self):
        backup_file = os.path.join(self.temp_dir.name, "backup_snapshot.db")

        # 1. Cria backup
        ok, msg = self.backup_service.create_database_backup(backup_file)
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(backup_file))

        # 2. Modifica a anotação no banco original
        self.diary_service.save_entry(self.user.id, "2026-10-27", "Conteúdo modificado pós backup!")
        entry_mod = self.diary_service.get_entry_by_date(self.user.id, "2026-10-27")
        self.assertEqual(entry_mod.content, "Conteúdo modificado pós backup!")

        # 3. Restaura o backup
        ok_rest, msg_rest = self.backup_service.restore_database_backup(backup_file)
        self.assertTrue(ok_rest)

        # 4. Verifica se o conteúdo antigo foi restaurado
        entry_rest = self.diary_service.get_entry_by_date(self.user.id, "2026-10-27")
        self.assertEqual(entry_rest.content, "Anotação antes do backup.")

    def test_export_txt(self):
        entry = self.diary_service.get_entry_by_date(self.user.id, "2026-10-27")
        export_file = os.path.join(self.temp_dir.name, "exportado.txt")

        ok, msg = self.backup_service.export_entry_to_txt(entry, export_file)
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(export_file))

        with open(export_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Anotação antes do backup.", content)

    def test_export_csv(self):
        results = [{
            "entry_date": "2026-10-27",
            "username": "admin_backup",
            "full_name": "Admin Backup",
            "snippet": "... Anotação antes do backup ...",
            "updated_at": "2026-10-27 10:00:00",
            "content": "Anotação antes do backup."
        }]
        csv_file = os.path.join(self.temp_dir.name, "resultados.csv")
        ok, msg = self.backup_service.export_search_results_to_csv(results, csv_file)
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(csv_file))

        # Verifica se o CSV foi escrito corretamente
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Data"], "27/10/2026")
            self.assertEqual(rows[0]["Usuário"], "admin_backup")


if __name__ == "__main__":
    unittest.main()
