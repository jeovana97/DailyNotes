import json
import os
import sqlite3
import tempfile
import unittest
import customtkinter as ctk

from database.migrations import init_db
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService
from services.note_service import NoteService
from services.search_service import SearchService
from utils.rich_text import (
    RichTextController,
    TAG_BOLD,
    TAG_UNDERLINE,
    TAG_OVERSTRIKE,
    TAG_FAMILY_PREFIX,
    TAG_SIZE_PREFIX,
    TAG_COMP_PREFIX,
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
)
from views.main_window import MainWindow


class TestRichTextPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "rich_text_test.db")
        init_db(self.db_path)

        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.diary_service = DiaryService(db_path=self.db_path)
        self.note_service = NoteService(db_path=self.db_path)
        self.search_service = SearchService(db_path=self.db_path)

        self.user, _ = self.auth_service.create_initial_admin(
            "admin_rt", "Admin RichText", "senha123"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_diary_entry_persists_formatting_and_keeps_search_clean(self):
        fmt = json.dumps({
            "font_family": "Georgia",
            "font_size": 18,
            "spans": [
                {"tag": "bold", "start": "1.0", "end": "1.10"},
                {"tag": "underline", "start": "1.0", "end": "1.10"},
                {"tag": "overstrike", "start": "1.11", "end": "1.18"},
            ],
        })
        saved = self.diary_service.save_entry(
            self.user.id,
            "2026-11-19",
            "Importante revisar contrato anual",
            formatting_json=fmt,
        )
        self.assertEqual(saved.formatting_json, fmt)

        reloaded = self.diary_service.get_entry_by_date(self.user.id, "2026-11-19")
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.formatting_json, fmt)
        self.assertEqual(reloaded.content, "Importante revisar contrato anual")

        # Garante que a pesquisa continua encontrando o conteúdo sem poluição do JSON
        results = self.search_service.search_all(
            requester=self.user, query="contrato", scope="diaries"
        )
        self.assertEqual(len(results), 1)
        # Termos do JSON (ex: "overstrike") não devem aparecer como falso positivo no texto
        false_pos = self.search_service.search_all(
            requester=self.user, query="overstrike", scope="diaries"
        )
        self.assertEqual(len(false_pos), 0)

    def test_note_persists_formatting_on_insert_and_update(self):
        fmt1 = json.dumps({
            "font_family": "Consolas",
            "font_size": 14,
            "spans": [{"tag": "bold", "start": "1.0", "end": "1.6"}],
        })
        created = self.note_service.save_note(
            self.user.id,
            title="Manual SQL",
            content="SELECT * FROM notas;",
            formatting_json=fmt1,
        )
        self.assertEqual(created.formatting_json, fmt1)

        fmt2 = json.dumps({
            "font_family": "Arial",
            "font_size": 16,
            "spans": [
                {"tag": "bold", "start": "1.0", "end": "1.6"},
                {"tag": "overstrike", "start": "1.7", "end": "1.12"},
            ],
        })
        updated = self.note_service.save_note(
            self.user.id,
            title="Manual SQL",
            content="SELECT * FROM notas;",
            note_id=created.id,
            formatting_json=fmt2,
        )
        self.assertEqual(updated.formatting_json, fmt2)

        fetched = self.note_service.get_note(self.user.id, created.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.formatting_json, fmt2)

        # Pesquisa nas pastas/arquivos continua intacta
        results = self.search_service.search_all(
            requester=self.user, query="notas", scope="notes"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source_type"], "note")

    def test_migration_adds_formatting_json_to_legacy_database(self):
        legacy_db = os.path.join(self.temp_dir.name, "legacy.db")
        conn = sqlite3.connect(legacy_db)
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE diaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                content_normalized TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, entry_date)
            );
            CREATE TABLE note_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                parent_id INTEGER,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER,
                title TEXT NOT NULL,
                title_normalized TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                content_normalized TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()

        # Roda migração incremental sobre banco antigo
        init_db(legacy_db)

        conn = sqlite3.connect(legacy_db)
        diary_cols = {r[1] for r in conn.execute("PRAGMA table_info(diaries)").fetchall()}
        note_cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)").fetchall()}
        conn.close()

        self.assertIn("formatting_json", diary_cols)
        self.assertIn("formatting_json", note_cols)


class TestRichTextController(unittest.TestCase):
    def setUp(self):
        self.root = ctk.CTk()
        self.root.withdraw()
        self.textbox = ctk.CTkTextbox(self.root)
        self.textbox.pack()
        self.change_count = 0
        self.ctrl = RichTextController(
            self.textbox,
            on_change_callback=self._on_change,
        )
        self.root.update()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def _on_change(self):
        self.change_count += 1

    def test_apply_combined_styles_on_selection_and_roundtrip(self):
        self.textbox.insert("1.0", "Texto normal e palavra destacada no fim.")
        tb = self.textbox._textbox

        # Seleciona "palavra destacada" (índices 1.15 a 1.32)
        tb.tag_add("sel", "1.15", "1.32")

        self.ctrl.apply_font_family("Consolas")
        self.ctrl.apply_font_size("20")
        self.ctrl.toggle_bold()
        self.ctrl.toggle_underline()
        self.ctrl.toggle_overstrike()

        tags_at_word = set(tb.tag_names("1.16"))
        self.assertIn(TAG_BOLD, tags_at_word)
        self.assertIn(TAG_UNDERLINE, tags_at_word)
        self.assertIn(TAG_OVERSTRIKE, tags_at_word)
        self.assertIn(f"{TAG_FAMILY_PREFIX}Consolas", tags_at_word)
        self.assertIn(f"{TAG_SIZE_PREFIX}20", tags_at_word)
        self.assertIn(f"{TAG_COMP_PREFIX}Consolas::20::1", tags_at_word)

        # Trecho fora da seleção permanece sem formatação extra
        tags_outside = set(tb.tag_names("1.1"))
        self.assertNotIn(TAG_BOLD, tags_outside)
        self.assertNotIn(TAG_UNDERLINE, tags_outside)
        self.assertNotIn(TAG_OVERSTRIKE, tags_outside)

        # Serializa, reseta e recarrega verificando restauração fiel
        serialized = self.ctrl.serialize()
        self.assertTrue(serialized)

        self.ctrl.reset()
        self.assertEqual(self.ctrl.base_family, DEFAULT_FONT_FAMILY)
        self.assertEqual(self.ctrl.base_size, DEFAULT_FONT_SIZE)
        self.assertNotIn(TAG_BOLD, tb.tag_names("1.16"))

        self.ctrl.load(serialized)
        restored_tags = set(tb.tag_names("1.16"))
        self.assertIn(TAG_BOLD, restored_tags)
        self.assertIn(TAG_UNDERLINE, restored_tags)
        self.assertIn(TAG_OVERSTRIKE, restored_tags)
        self.assertIn(f"{TAG_FAMILY_PREFIX}Consolas", restored_tags)
        self.assertIn(f"{TAG_SIZE_PREFIX}20", restored_tags)
        self.assertIn(f"{TAG_COMP_PREFIX}Consolas::20::1", restored_tags)

    def test_toggle_off_styles_and_global_font_size(self):
        self.textbox.insert("1.0", "Ola mundo")
        tb = self.textbox._textbox

        # Altera fonte e tamanho globalmente sem seleção
        self.ctrl.apply_font_family("Georgia")
        self.ctrl.apply_font_size("22")
        self.assertEqual(self.ctrl.base_family, "Georgia")
        self.assertEqual(self.ctrl.base_size, 22)

        # Liga e depois desliga negrito, sublinhado e riscado em "Ola"
        tb.tag_add("sel", "1.0", "1.3")
        self.ctrl.toggle_bold()
        self.ctrl.toggle_underline()
        self.ctrl.toggle_overstrike()
        self.assertIn(TAG_BOLD, tb.tag_names("1.1"))
        self.assertIn(TAG_UNDERLINE, tb.tag_names("1.1"))
        self.assertIn(TAG_OVERSTRIKE, tb.tag_names("1.1"))

        self.ctrl.toggle_bold()
        self.ctrl.toggle_underline()
        self.ctrl.toggle_overstrike()
        self.assertNotIn(TAG_BOLD, tb.tag_names("1.1"))
        self.assertNotIn(TAG_UNDERLINE, tb.tag_names("1.1"))
        self.assertNotIn(TAG_OVERSTRIKE, tb.tag_names("1.1"))

        # Serialização ainda registra fonte/tamanho base customizados
        data = json.loads(self.ctrl.serialize())
        self.assertEqual(data["font_family"], "Georgia")
        self.assertEqual(data["font_size"], 22)
        self.assertEqual(data["spans"], [])


class TestRichTextUIIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "rich_ui_test.db")
        init_db(self.db_path)
        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.admin, _ = self.auth_service.create_initial_admin(
            "admin_rt_ui", "Admin RT UI", "admin1234"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_diary_notes_reader_and_history_rich_text_flow(self):
        app = MainWindow(db_path=self.db_path)
        try:
            app.update()
            app._on_login_success(self.admin)
            app.update()

            # 1. Diário do Dia: formata seleção, salva e confirma persistência
            app.navigate_to("diary", date_iso="2026-11-19")
            app.update()
            diary_view = app.active_view
            diary_view.txt_content.insert("1.0", "Resumo diario importante")
            diary_view.txt_content._textbox.tag_add("sel", "1.14", "1.24")
            diary_view.rich_text.apply_font_family("Arial")
            diary_view.rich_text.apply_font_size("18")
            diary_view.rich_text.toggle_bold()
            diary_view.rich_text.toggle_underline()
            diary_view.rich_text.toggle_overstrike()
            self.assertTrue(diary_view.has_unsaved_changes)
            self.assertTrue(diary_view.save_current_entry(silent=True))
            self.assertFalse(diary_view.has_unsaved_changes)

            # Alterar apenas formatação (sem alterar texto) deve marcar has_unsaved_changes
            diary_view.txt_content._textbox.tag_remove("sel", "1.0", "end")
            diary_view.rich_text.apply_font_size("16")
            self.assertTrue(diary_view.has_unsaved_changes)
            self.assertTrue(diary_view.save_current_entry(silent=True))

            # 2. Notas & Pastas: cria nota formatada, salva e recarrega
            app.navigate_to("notes")
            app.update()
            notes_view = app.active_view
            notes_view.entry_title.insert(0, "Nota Estilizada")
            notes_view.txt_content.insert("1.0", "Texto com destaque especial")
            notes_view.txt_content._textbox.tag_add("sel", "1.10", "1.18")
            notes_view.rich_text.toggle_bold()
            notes_view.rich_text.toggle_overstrike()
            notes_view.rich_text.apply_font_family("Verdana")
            self.assertTrue(notes_view.save_current_note(silent=True))
            saved_note_id = notes_view.active_note.id

            # Recarrega a nota e valida tags preservadas
            notes_view._prepare_blank_note()
            self.assertTrue(notes_view.load_note(saved_note_id))
            note_tags = set(notes_view.txt_content._textbox.tag_names("1.12"))
            self.assertIn(TAG_BOLD, note_tags)
            self.assertIn(TAG_OVERSTRIKE, note_tags)
            self.assertIn(f"{TAG_FAMILY_PREFIX}Verdana", note_tags)

            # 3. Histórico & Calendário: preview e janela de leitura/edição
            app.navigate_to("history", initial_date="2026-11-19")
            app.update()
            history_view = app.active_view
            history_view._on_calendar_date_selected("2026-11-19")
            app.update()
            preview_tags = set(history_view.txt_day_preview._textbox.tag_names("1.16"))
            self.assertIn(TAG_BOLD, preview_tags)
            self.assertIn(TAG_UNDERLINE, preview_tags)
            self.assertIn(TAG_OVERSTRIKE, preview_tags)

            # Abre DiaryNoteReaderDialog e edita apenas formatação
            history_view._open_date("2026-11-19")
            app.update()
            reader = history_view._reader_dialog
            self.assertIsNotNone(reader)
            reader_tags = set(reader.txt_content._textbox.tag_names("1.16"))
            self.assertIn(TAG_BOLD, reader_tags)
            self.assertEqual(reader.combo_font_family.cget("state"), "disabled")

            reader._enable_edit_mode()
            self.assertEqual(reader.combo_font_family.cget("state"), "readonly")
            reader.txt_content._textbox.tag_add("sel", "1.0", "1.6")
            reader.rich_text.toggle_underline()
            self.assertTrue(reader.has_unsaved_changes)
            self.assertTrue(reader.save_changes())
            reader.destroy()
        finally:
            try:
                app.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
