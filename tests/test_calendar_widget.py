import unittest
import customtkinter as ctk
from views.components.calendar_widget import CalendarWidget


class TestCalendarWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Desativa renderização visual para testes rápidos
        ctk.set_appearance_mode("Dark")
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_parse_calendar_jump(self):
        widget = CalendarWidget(self.root, selected_date_iso="2025-01-15")

        # DD/MM/AAAA
        res = widget._parse_calendar_jump("25/12/2024")
        self.assertEqual(res, {"type": "date", "iso": "2024-12-25"})

        # DD-MM-AAAA
        res = widget._parse_calendar_jump("05-08-2023")
        self.assertEqual(res, {"type": "date", "iso": "2023-08-05"})

        # DD MM AAAA
        res = widget._parse_calendar_jump("10 03 2026")
        self.assertEqual(res, {"type": "date", "iso": "2026-03-10"})

        # AAAA-MM-DD
        res = widget._parse_calendar_jump("2027-11-20")
        self.assertEqual(res, {"type": "date", "iso": "2027-11-20"})

        # MM/AAAA
        res = widget._parse_calendar_jump("07/2026")
        self.assertEqual(res, {"type": "month", "year": 2026, "month": 7})

        # Apenas Ano (4 dígitos)
        res = widget._parse_calendar_jump("2030")
        self.assertEqual(res, {"type": "month", "year": 2030, "month": 1})

        # Mês por extenso + ano
        res = widget._parse_calendar_jump("março 2026")
        self.assertEqual(res, {"type": "month", "year": 2026, "month": 3})

        # 15 de janeiro de 2026
        res = widget._parse_calendar_jump("15 de janeiro de 2026")
        self.assertEqual(res, {"type": "date", "iso": "2026-01-15"})

        # Datas inválidas
        self.assertIsNone(widget._parse_calendar_jump(""))
        self.assertIsNone(widget._parse_calendar_jump("35/01/2025"))
        self.assertIsNone(widget._parse_calendar_jump("texto aleatório"))

        widget.destroy()

    def test_edit_mode_flow_and_navigation(self):
        selected_dates = []
        month_changes = []

        widget = CalendarWidget(
            self.root,
            on_date_selected=lambda d: selected_dates.append(d),
            on_month_changed=lambda y, m: month_changes.append((y, m)),
            selected_date_iso="2025-01-10",
        )

        # Inicia modo de edição
        widget._enter_edit_mode()
        self.assertEqual(widget.entry_date.get(), "10/01/2025")

        # Altera para nova data e confirma
        widget.entry_date.delete(0, "end")
        widget.entry_date.insert(0, "20/05/2025")
        widget._confirm_date_input()

        self.assertEqual(widget.selected_date, "2025-05-20")
        self.assertEqual(widget.current_year, 2025)
        self.assertEqual(widget.current_month, 5)
        self.assertIn("2025-05-20", selected_dates)
        self.assertIn((2025, 5), month_changes)

        # Testa entrada de apenas Mês/Ano
        widget._enter_edit_mode()
        widget.entry_date.delete(0, "end")
        widget.entry_date.insert(0, "11/2028")
        widget._confirm_date_input()

        self.assertEqual(widget.current_year, 2028)
        self.assertEqual(widget.current_month, 11)
        self.assertIn((2028, 11), month_changes)

        # Testa cancelamento
        widget._enter_edit_mode()
        widget._exit_edit_mode()

        widget.destroy()


if __name__ == "__main__":
    unittest.main()
