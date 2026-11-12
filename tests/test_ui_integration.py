import unittest
import tempfile
import os
from database.migrations import init_db
from services.authentication_service import AuthenticationService
from views.main_window import MainWindow


class TestUIIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "ui_test.db")
        init_db(self.db_path)
        self.auth_service = AuthenticationService(db_path=self.db_path)
        # Cria admin inicial
        self.admin, _ = self.auth_service.create_initial_admin("admin_test", "Admin UI Test", "admin1234")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_main_window_views_navigation(self):
        app = MainWindow(db_path=self.db_path)
        app.update()

        # Simula login
        app._on_login_success(self.admin)
        app.update()

        # Navega por todas as telas para verificar renderização sem erros
        views_to_test = ["diary", "notes", "search", "history", "import", "backup", "users"]
        for view_name in views_to_test:
            app.navigate_to(view_name)
            app.update()
            self.assertIsNotNone(app.active_view)

        # Cria uma anotação de teste e verifica se abrir a partir da Pesquisa Avançada
        # e do Histórico & Calendário abre a janela de leitura sem sair da tela atual
        app.diary_service.save_entry(self.admin.id, "2026-11-05", "Nota de teste para leitura e edicao")

        app.navigate_to("search")
        app.update()
        search_view = app.active_view
        search_view.execute_search()
        app.update()
        search_view._open_result("2026-11-05", self.admin.id)
        app.update()

        # Permanece na tela de pesquisa e abre o diálogo em modo somente leitura
        self.assertIs(app.active_view, search_view)
        self.assertIsNotNone(search_view._reader_dialog)
        self.assertFalse(search_view._reader_dialog.is_editing)
        self.assertEqual(search_view._reader_dialog.txt_content.cget("state"), "disabled")

        # Habilita edição na janela de leitura e salva
        search_view._reader_dialog._enable_edit_mode()
        self.assertTrue(search_view._reader_dialog.is_editing)
        self.assertEqual(search_view._reader_dialog.txt_content.cget("state"), "normal")
        search_view._reader_dialog.txt_content.insert("end", " - editado")
        search_view._reader_dialog.save_changes()
        self.assertFalse(search_view._reader_dialog.is_editing)
        search_view._reader_dialog.destroy()

        # Verifica abertura também no Histórico & Calendário
        app.navigate_to("history", initial_date="2026-11-05")
        app.update()
        history_view = app.active_view
        history_view._open_date("2026-11-05")
        app.update()
        self.assertIs(app.active_view, history_view)
        self.assertIsNotNone(history_view._reader_dialog)
        self.assertFalse(history_view._reader_dialog.is_editing)
        history_view._reader_dialog.destroy()

        # Verifica colagem de texto no Diário do Dia posicionando o cursor no fim do texto
        app.navigate_to("diary")
        app.update()
        diary_view = app.active_view
        diary_view.txt_content.delete("1.0", "end")
        diary_view.txt_content.insert("1.0", "Linha inicial\n")
        diary_view.txt_content._textbox.mark_set("insert", "1.0")
        app.clipboard_clear()
        app.clipboard_append("Texto colado 1\nTexto colado final")
        diary_view._on_paste()
        app.update()
        tb = diary_view.txt_content._textbox
        self.assertEqual(tb.index("insert"), tb.index("end-1c"))
        self.assertIn("Texto colado final", diary_view.txt_content.get("1.0", "end-1c"))

        # Verifica configuração e execução do Backup Automático
        auto_backup_dir = os.path.join(self.temp_dir.name, "auto_backups")
        ok, msg = app.backup_service.save_auto_backup_settings(
            enabled=True,
            target_dir=auto_backup_dir,
            schedule_date_iso="2026-11-05",
            schedule_time="08:30",
            repeat_daily=True,
        )
        self.assertTrue(ok, msg)

        import datetime
        # Antes do horário agendado não deve executar
        ran_early, _ = app.backup_service.check_and_run_due_auto_backup(
            now=datetime.datetime(2026, 11, 5, 8, 15, 0)
        )
        self.assertFalse(ran_early)

        # No horário agendado deve gerar o arquivo .db automaticamente
        ran_due, generated_path = app.backup_service.check_and_run_due_auto_backup(
            now=datetime.datetime(2026, 11, 5, 8, 35, 0)
        )
        self.assertTrue(ran_due)
        self.assertIsNotNone(generated_path)
        self.assertTrue(os.path.isfile(generated_path))

        # Não deve duplicar no mesmo dia após já ter executado
        ran_again, _ = app.backup_service.check_and_run_due_auto_backup(
            now=datetime.datetime(2026, 11, 5, 9, 0, 0)
        )
        self.assertFalse(ran_again)

        # Destrói app
        app.destroy()

    def test_notes_view_folders_minimized_by_default_and_expand_on_click(self):
        # Cria estrutura de pastas e notas
        f_admin = self.auth_service.db_path  # Apenas para ter o path
        from services.note_service import NoteService
        note_service = NoteService(db_path=self.db_path)
        folder_admin = note_service.create_folder(self.admin.id, "Administrativo")
        folder_scripts = note_service.create_folder(self.admin.id, "Scripts", parent_id=folder_admin.id)
        note_service.save_note(
            self.admin.id,
            title="Nota de Teste Admin",
            content="Conteudo",
            folder_id=folder_admin.id,
        )

        app = MainWindow(db_path=self.db_path)
        app.update()
        app._on_login_success(self.admin)
        app.update()

        # Navega para a tela de notas
        app.navigate_to("notes")
        app.update()

        notes_view = app.active_view
        # As pastas devem vir minimizadas (recolhidas) por padrão
        self.assertEqual(notes_view.expanded_folders, set())

        # Ao clicar na pasta, ela deve expandir e exibir o conteúdo
        notes_view._on_folder_row_clicked(folder_admin.id)
        app.update()
        self.assertIn(folder_admin.id, notes_view.expanded_folders)

        # Ao clicar novamente, a pasta deve recolher (minimizar)
        notes_view._on_folder_row_clicked(folder_admin.id)
        app.update()
        self.assertNotIn(folder_admin.id, notes_view.expanded_folders)

        app.destroy()


if __name__ == "__main__":
    unittest.main()
