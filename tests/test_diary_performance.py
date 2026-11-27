"""
Testes de desempenho e regressão do Diário do Dia:
- Abertura, reabertura em cache e troca de dias (Anterior / Hoje / Próximo)
- Colagem de textos em notas extensas com formatação rica (negrito/itálico/fonte) e SQL+XML
- Preservação de Ctrl+Z (Desfazer), posicionamento do cursor ao final da colagem e corretor ortográfico.
"""

import json
import os
import tempfile
import time
import unittest

from database.migrations import init_db
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService
from views.main_window import MainWindow


class TestDiaryPerformanceAndPaste(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "diary_perf.db")
        init_db(self.db_path)

        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.user, _ = self.auth_service.create_initial_admin(
            "perf_admin", "Admin Perf", "senha123"
        )
        self.diary_service = DiaryService(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fast_day_switch_paste_and_reopen_on_large_notes(self):
        # Dia 1: 25KB com formatação rica (antes travava em _recompute_composite_fonts char-a-char)
        para = "Relatório diário de atendimento ao cliente e validação de emissão fiscal. " * 3
        day1_text = "\n".join(f"Linha {i:03d}: {para}" for i in range(100))
        day1_fmt = json.dumps(
            {
                "font_family": "Segoe UI",
                "font_size": 15,
                "spans": [
                    {"tag": "bold", "start": "1.0", "end": "1.25"},
                    {"tag": "italic", "start": "10.0", "end": "10.30"},
                ],
            }
        )

        # Dia 2: SQL + XML misturados (antes chamava highlight_xml_range centenas de vezes)
        day2_lines = []
        for i in range(40):
            day2_lines.append(
                f"-- Consulta {i}\nSELECT id, nome FROM pedidos WHERE cliente_id = {i} AND valor >= 100.50;"
            )
            day2_lines.append(
                f'<NFe id="{i}"><infNFe versao="4.00"><ide><cNF>{i:08d}</cNF></ide></infNFe></NFe>'
            )
        day2_text = "\n".join(day2_lines)

        self.diary_service.save_entry(self.user.id, "2026-11-26", day1_text, formatting_json=day1_fmt)
        self.diary_service.save_entry(self.user.id, "2026-11-27", day2_text)

        app = MainWindow(db_path=self.db_path)
        try:
            app.update()
            app._on_login_success(self.user)
            app.update()
            diary_view = app.active_view

            # 1. Troca para Dia 1 (25KB + negrito/itálico) deve ser rápida e manter as tags compostas
            t0 = time.perf_counter()
            diary_view.set_date("2026-11-26")
            elapsed_day1 = time.perf_counter() - t0
            self.assertLess(elapsed_day1, 1.0, f"Troca para Dia 1 demorou demais: {elapsed_day1:.3f}s")
            tb = diary_view.txt_content._textbox
            self.assertIn("rt_bold", tb.tag_names("1.5"))
            self.assertIn("rt_italic", tb.tag_names("10.5"))

            # 2. Troca para Dia 2 (SQL + XML) deve ser rápida e aplicar cores SQL e XML
            t0 = time.perf_counter()
            diary_view.set_date("2026-11-27")
            elapsed_day2 = time.perf_counter() - t0
            self.assertLess(elapsed_day2, 1.0, f"Troca para Dia 2 (SQL+XML) demorou demais: {elapsed_day2:.3f}s")
            self.assertTrue(bool(tb.tag_ranges("syntax_sql_keyword")))
            self.assertTrue(bool(tb.tag_ranges("syntax_xml_tag")))

            # 3. Colagem em nota longa SQL+XML deve ser rápida, manter cursor no fim da cópia e permitir Undo
            tb.mark_set("insert", "1.0")
            pasted = "Linha colada 1\r\nSELECT id FROM clientes WHERE ativo = 1;\r\n"
            app.clipboard_clear()
            app.clipboard_append(pasted)

            t0 = time.perf_counter()
            diary_view._on_paste()
            elapsed_paste = time.perf_counter() - t0
            self.assertLess(elapsed_paste, 1.0, f"Colagem no Dia 2 demorou demais: {elapsed_paste:.3f}s")

            # Cursor posicionado exatamente no fim do texto colado (normalizado para \n)
            self.assertEqual(tb.index("insert"), "3.0")
            self.assertIn("Linha colada 1", tb.get("1.0", "2.0"))
            self.assertTrue(diary_view.has_unsaved_changes)

            # Ctrl+Z desfaz a colagem intactamente
            diary_view._on_undo_clicked()
            self.assertNotIn("Linha colada 1", tb.get("1.0", "2.0"))

            # 4. Navegar para outro menu e voltar ao Diário reutiliza a view em cache com rapidez
            diary_view.has_unsaved_changes = False
            app.navigate_to("schedules")
            app.update()
            t0 = time.perf_counter()
            app.navigate_to("diary")
            elapsed_reopen = time.perf_counter() - t0
            self.assertLess(elapsed_reopen, 1.0, f"Reabertura do Diário demorou demais: {elapsed_reopen:.3f}s")
            self.assertIs(app.active_view, diary_view)
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
