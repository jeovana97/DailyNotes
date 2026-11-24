import json
import os
import sqlite3
import tempfile
import tkinter.font as tkfont
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
    TAG_ITALIC,
    TAG_UNDERLINE,
    TAG_OVERSTRIKE,
    TAG_FAMILY_PREFIX,
    TAG_SIZE_PREFIX,
    TAG_COMP_PREFIX,
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
)
from utils.syntax_highlighter import (
    enable_undo_redo,
    perform_undo,
    perform_redo,
    reset_undo_stack,
    convert_selection_case,
    format_and_highlight_xml,
    format_and_highlight_sql,
    clear_syntax_tags,
    ALL_SYNTAX_TAGS,
)
from utils.editor_history import (
    commit_history_before_action,
    record_history_after_action,
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
                {"tag": "italic", "start": "1.0", "end": "1.10"},
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
                {"tag": "italic", "start": "1.0", "end": "1.6"},
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

        init_db(legacy_db)

        conn = sqlite3.connect(legacy_db)
        diary_cols = {r[1] for r in conn.execute("PRAGMA table_info(diaries)").fetchall()}
        note_cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)").fetchall()}
        conn.close()

        self.assertIn("formatting_json", diary_cols)
        self.assertIn("formatting_json", note_cols)


class TestRichTextControllerAndUndoRedo(unittest.TestCase):
    def setUp(self):
        self.root = ctk.CTk()
        self.root.withdraw()
        self.textbox = ctk.CTkTextbox(
            self.root,
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=DEFAULT_FONT_SIZE),
        )
        self.textbox.pack()
        self.change_count = 0
        enable_undo_redo(self.textbox, on_change_callback=self._on_change)
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

    def _has_any_syntax_tag(self) -> bool:
        tb = self.textbox._textbox
        return any(bool(tb.tag_ranges(t)) for t in ALL_SYNTAX_TAGS)

    def test_bold_and_italic_keep_exact_base_font_size(self):
        """Aplicar Negrito (B) ou Itálico (I) NÃO pode alterar o tamanho visual da fonte."""
        self.textbox.insert("1.0", "Texto normal e palavra negrito")
        tb = self.textbox._textbox

        base_font_obj = tkfont.Font(root=tb, font=tb.cget("font"))
        base_actual_size = base_font_obj.actual("size")

        tb.tag_add("sel", "1.23", "1.30")
        self.ctrl.toggle_bold()

        bold_tag = f"{TAG_COMP_PREFIX}{DEFAULT_FONT_FAMILY}::{DEFAULT_FONT_SIZE}::1::0"
        self.assertIn(bold_tag, tb.tag_names("1.24"))
        bold_font_name = tb.tag_cget(bold_tag, "font")
        bold_font_obj = tkfont.Font(root=tb, font=bold_font_name)

        self.assertEqual(bold_font_obj.actual("weight"), "bold")
        self.assertEqual(
            bold_font_obj.actual("size"),
            base_actual_size,
            "Ativar Negrito (B) alterou o tamanho da fonte!",
        )
        self.assertLess(int(bold_font_obj.cget("size")), 0)

        # Também combina com Itálico preservando exatamente o mesmo tamanho
        self.ctrl.toggle_italic()
        bi_tag = f"{TAG_COMP_PREFIX}{DEFAULT_FONT_FAMILY}::{DEFAULT_FONT_SIZE}::1::1"
        self.assertIn(bi_tag, tb.tag_names("1.24"))
        bi_font_obj = tkfont.Font(root=tb, font=tb.tag_cget(bi_tag, "font"))
        self.assertEqual(bi_font_obj.actual("weight"), "bold")
        self.assertEqual(bi_font_obj.actual("slant"), "italic")
        self.assertEqual(bi_font_obj.actual("size"), base_actual_size)

    def test_apply_combined_styles_on_selection_and_roundtrip(self):
        self.textbox.insert("1.0", "Texto normal e palavra destacada no fim.")
        tb = self.textbox._textbox

        tb.tag_add("sel", "1.15", "1.32")

        self.ctrl.apply_font_family("Consolas")
        self.ctrl.apply_font_size("20")
        self.ctrl.toggle_bold()
        self.ctrl.toggle_italic()
        self.ctrl.toggle_underline()
        self.ctrl.toggle_overstrike()

        tags_at_word = set(tb.tag_names("1.16"))
        self.assertIn(TAG_BOLD, tags_at_word)
        self.assertIn(TAG_ITALIC, tags_at_word)
        self.assertIn(TAG_UNDERLINE, tags_at_word)
        self.assertIn(TAG_OVERSTRIKE, tags_at_word)
        self.assertIn(f"{TAG_FAMILY_PREFIX}Consolas", tags_at_word)
        self.assertIn(f"{TAG_SIZE_PREFIX}20", tags_at_word)
        self.assertIn(f"{TAG_COMP_PREFIX}Consolas::20::1::1", tags_at_word)

        tags_outside = set(tb.tag_names("1.1"))
        self.assertNotIn(TAG_BOLD, tags_outside)
        self.assertNotIn(TAG_ITALIC, tags_outside)
        self.assertNotIn(TAG_UNDERLINE, tags_outside)
        self.assertNotIn(TAG_OVERSTRIKE, tags_outside)

        serialized = self.ctrl.serialize()
        self.assertTrue(serialized)

        self.ctrl.reset()
        self.assertEqual(self.ctrl.base_family, DEFAULT_FONT_FAMILY)
        self.assertEqual(self.ctrl.base_size, DEFAULT_FONT_SIZE)
        self.assertNotIn(TAG_BOLD, tb.tag_names("1.16"))

        self.ctrl.load(serialized)
        restored_tags = set(tb.tag_names("1.16"))
        self.assertIn(TAG_BOLD, restored_tags)
        self.assertIn(TAG_ITALIC, restored_tags)
        self.assertIn(TAG_UNDERLINE, restored_tags)
        self.assertIn(TAG_OVERSTRIKE, restored_tags)
        self.assertIn(f"{TAG_FAMILY_PREFIX}Consolas", restored_tags)
        self.assertIn(f"{TAG_SIZE_PREFIX}20", restored_tags)
        self.assertIn(f"{TAG_COMP_PREFIX}Consolas::20::1::1", restored_tags)

    def test_toggle_off_styles_and_global_font_size(self):
        self.textbox.insert("1.0", "Ola mundo")
        tb = self.textbox._textbox

        self.ctrl.apply_font_family("Georgia")
        self.ctrl.apply_font_size("22")
        self.assertEqual(self.ctrl.base_family, "Georgia")
        self.assertEqual(self.ctrl.base_size, 22)

        tb.tag_add("sel", "1.0", "1.3")
        self.ctrl.toggle_bold()
        self.ctrl.toggle_italic()
        self.ctrl.toggle_underline()
        self.ctrl.toggle_overstrike()
        self.assertIn(TAG_BOLD, tb.tag_names("1.1"))
        self.assertIn(TAG_ITALIC, tb.tag_names("1.1"))
        self.assertIn(TAG_UNDERLINE, tb.tag_names("1.1"))
        self.assertIn(TAG_OVERSTRIKE, tb.tag_names("1.1"))

        self.ctrl.toggle_bold()
        self.ctrl.toggle_italic()
        self.ctrl.toggle_underline()
        self.ctrl.toggle_overstrike()
        self.assertNotIn(TAG_BOLD, tb.tag_names("1.1"))
        self.assertNotIn(TAG_ITALIC, tb.tag_names("1.1"))
        self.assertNotIn(TAG_UNDERLINE, tb.tag_names("1.1"))
        self.assertNotIn(TAG_OVERSTRIKE, tb.tag_names("1.1"))

        data = json.loads(self.ctrl.serialize())
        self.assertEqual(data["font_family"], "Georgia")
        self.assertEqual(data["font_size"], 22)
        self.assertEqual(data["spans"], [])

    def test_undo_and_redo_for_all_formatting_actions(self):
        """Ctrl+Z e Ctrl+Y devem desfazer/refazer fonte, tamanho, negrito, itálico, sublinhado, riscado e caixa."""
        tb = self.textbox._textbox
        self.textbox.insert("1.0", "nota de teste")
        reset_undo_stack(self.textbox)

        # 1. Troca fonte global
        self.ctrl.apply_font_family("Georgia")
        self.assertEqual(self.ctrl.base_family, "Georgia")

        # 2. Troca tamanho global
        self.ctrl.apply_font_size("20")
        self.assertEqual(self.ctrl.base_size, 20)

        # Seleciona "teste" (1.8 a 1.13)
        tb.tag_add("sel", "1.8", "1.13")

        # 3. Negrito
        self.ctrl.toggle_bold()
        self.assertIn(TAG_BOLD, tb.tag_names("1.9"))

        # 4. Itálico
        self.ctrl.toggle_italic()
        self.assertIn(TAG_ITALIC, tb.tag_names("1.9"))

        # 5. Sublinhado
        self.ctrl.toggle_underline()
        self.assertIn(TAG_UNDERLINE, tb.tag_names("1.9"))

        # 6. Riscado
        self.ctrl.toggle_overstrike()
        self.assertIn(TAG_OVERSTRIKE, tb.tag_names("1.9"))

        # 7. Converter para MAIÚSCULO
        ok, _ = convert_selection_case(self.textbox, uppercase=True)
        self.assertTrue(ok)
        self.assertEqual(tb.get("1.0", "end-1c"), "nota de TESTE")

        # --- Desfaz cada ação na ordem inversa ---
        # Desfaz MAIÚSCULO
        self.assertTrue(perform_undo(self.textbox))
        self.assertEqual(tb.get("1.0", "end-1c"), "nota de teste")
        self.assertIn(TAG_OVERSTRIKE, tb.tag_names("1.9"))

        # Desfaz Riscado
        self.assertTrue(perform_undo(self.textbox))
        self.assertNotIn(TAG_OVERSTRIKE, tb.tag_names("1.9"))
        self.assertIn(TAG_UNDERLINE, tb.tag_names("1.9"))

        # Desfaz Sublinhado
        self.assertTrue(perform_undo(self.textbox))
        self.assertNotIn(TAG_UNDERLINE, tb.tag_names("1.9"))
        self.assertIn(TAG_ITALIC, tb.tag_names("1.9"))

        # Desfaz Itálico
        self.assertTrue(perform_undo(self.textbox))
        self.assertNotIn(TAG_ITALIC, tb.tag_names("1.9"))
        self.assertIn(TAG_BOLD, tb.tag_names("1.9"))

        # Desfaz Negrito
        self.assertTrue(perform_undo(self.textbox))
        self.assertNotIn(TAG_BOLD, tb.tag_names("1.9"))
        self.assertEqual(self.ctrl.base_size, 20)

        # Desfaz Tamanho 20 -> volta para padrão 15
        self.assertTrue(perform_undo(self.textbox))
        self.assertEqual(self.ctrl.base_size, DEFAULT_FONT_SIZE)
        self.assertEqual(self.ctrl.base_family, "Georgia")

        # Desfaz Fonte Georgia -> volta para padrão Segoe UI
        self.assertTrue(perform_undo(self.textbox))
        self.assertEqual(self.ctrl.base_family, DEFAULT_FONT_FAMILY)

        # Sem mais passos na pilha
        self.assertFalse(perform_undo(self.textbox))

        # --- Refaz (Ctrl+Y) os passos ---
        self.assertTrue(perform_redo(self.textbox))
        self.assertEqual(self.ctrl.base_family, "Georgia")
        self.assertTrue(perform_redo(self.textbox))
        self.assertEqual(self.ctrl.base_size, 20)
        self.assertTrue(perform_redo(self.textbox))
        self.assertIn(TAG_BOLD, tb.tag_names("1.9"))

    def test_undo_and_redo_for_xml_sql_clear_colors_and_typing(self):
        """Ctrl+Z deve desfazer formatação/coloração XML, SQL, limpar cores e edições de texto."""
        tb = self.textbox._textbox

        # 1. SQL: formata + colore, depois desfaz (remove texto formatado E cores)
        self.textbox.insert("1.0", "select id from clientes;")
        reset_undo_stack(self.textbox)

        self.assertTrue(format_and_highlight_sql(self.textbox, format_keywords=True))
        self.assertEqual(tb.get("1.0", "end-1c"), "SELECT id FROM clientes;")
        self.assertTrue(self._has_any_syntax_tag())

        # Limpar cores -> depois Ctrl+Z deve restaurar as cores
        commit_history_before_action(self.textbox)
        clear_syntax_tags(tb, "1.0", "end")
        record_history_after_action(self.textbox)
        self.assertFalse(self._has_any_syntax_tag())

        self.assertTrue(perform_undo(self.textbox))
        self.assertTrue(self._has_any_syntax_tag())

        # Novo Ctrl+Z deve desfazer o botão SQL (voltar para minúsculo E sem cores)
        self.assertTrue(perform_undo(self.textbox))
        self.assertEqual(tb.get("1.0", "end-1c"), "select id from clientes;")
        self.assertFalse(self._has_any_syntax_tag())

        # Ctrl+Y refaz SQL
        self.assertTrue(perform_redo(self.textbox))
        self.assertEqual(tb.get("1.0", "end-1c"), "SELECT id FROM clientes;")
        self.assertTrue(self._has_any_syntax_tag())

        # 2. XML: indenta + colore, e também apenas colorir XML já indentado
        tb.delete("1.0", "end")
        clear_syntax_tags(tb, "1.0", "end")
        tb.insert("1.0", "<nfe><id>1</id></nfe>")
        reset_undo_stack(self.textbox)

        self.assertTrue(format_and_highlight_xml(self.textbox, indent_xml=True))
        self.assertIn("\n", tb.get("1.0", "end-1c"))
        self.assertTrue(self._has_any_syntax_tag())

        # Ctrl+Z desfaz indentação + cores XML
        self.assertTrue(perform_undo(self.textbox))
        self.assertEqual(tb.get("1.0", "end-1c"), "<nfe><id>1</id></nfe>")
        self.assertFalse(self._has_any_syntax_tag())

        # 3. Edição de texto seguida de botão de ação: Ctrl+Z desfaz primeiro o botão, depois o texto
        tb.insert("end", " extra")
        tb.tag_add("sel", "1.0", "1.5")
        self.ctrl.toggle_bold()
        self.assertIn(TAG_BOLD, tb.tag_names("1.1"))
        self.assertTrue(tb.get("1.0", "end-1c").endswith(" extra"))

        self.assertTrue(perform_undo(self.textbox))
        self.assertNotIn(TAG_BOLD, tb.tag_names("1.1"))
        self.assertTrue(tb.get("1.0", "end-1c").endswith(" extra"))

        self.assertTrue(perform_undo(self.textbox))
        self.assertEqual(tb.get("1.0", "end-1c"), "<nfe><id>1</id></nfe>")


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

            # 1. Diário do Dia: formata seleção, testa desfazer/refazer, salva e confirma persistência
            app.navigate_to("diary", date_iso="2026-11-19")
            app.update()
            diary_view = app.active_view
            diary_view.txt_content.insert("1.0", "Resumo diario importante")
            diary_view.txt_content._textbox.tag_add("sel", "1.14", "1.24")
            diary_view.rich_text.apply_font_family("Arial")
            diary_view.rich_text.apply_font_size("18")
            diary_view.rich_text.toggle_bold()
            diary_view.rich_text.toggle_italic()
            diary_view.rich_text.toggle_underline()
            diary_view.rich_text.toggle_overstrike()

            # Testa desfazer e refazer o Riscado pelo botão da barra
            diary_view._on_undo_clicked()
            self.assertNotIn(TAG_OVERSTRIKE, diary_view.txt_content._textbox.tag_names("1.16"))
            diary_view._on_redo_clicked()
            self.assertIn(TAG_OVERSTRIKE, diary_view.txt_content._textbox.tag_names("1.16"))

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
            notes_view.rich_text.toggle_italic()
            notes_view.rich_text.toggle_overstrike()
            notes_view.rich_text.apply_font_family("Verdana")
            self.assertTrue(notes_view.save_current_note(silent=True))
            saved_note_id = notes_view.active_note.id

            # Recarrega a nota e valida tags preservadas
            notes_view._prepare_blank_note()
            self.assertTrue(notes_view.load_note(saved_note_id))
            note_tags = set(notes_view.txt_content._textbox.tag_names("1.12"))
            self.assertIn(TAG_BOLD, note_tags)
            self.assertIn(TAG_ITALIC, note_tags)
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
            self.assertIn(TAG_ITALIC, preview_tags)
            self.assertIn(TAG_UNDERLINE, preview_tags)
            self.assertIn(TAG_OVERSTRIKE, preview_tags)

            # Abre DiaryNoteReaderDialog, edita e testa Undo/Redo na janela
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
            self.assertIn(TAG_UNDERLINE, reader.txt_content._textbox.tag_names("1.1"))
            self.assertTrue(reader.has_unsaved_changes)

            # Desfazer na janela de leitura remove o sublinhado
            reader._on_undo()
            self.assertNotIn(TAG_UNDERLINE, reader.txt_content._textbox.tag_names("1.1"))
            # Refazer restaura o sublinhado
            reader._on_redo()
            self.assertIn(TAG_UNDERLINE, reader.txt_content._textbox.tag_names("1.1"))

            self.assertTrue(reader.save_changes())
            reader.destroy()
        finally:
            try:
                app.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
