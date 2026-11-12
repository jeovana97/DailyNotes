import unittest
import os
from utils.window_utils import (
    get_display_monitors,
    get_primary_monitor_work_area,
    center_window_on_primary_screen,
    center_modal_on_parent,
)


class TestWindowUtils(unittest.TestCase):
    def test_get_display_monitors(self):
        monitors = get_display_monitors()
        self.assertIsInstance(monitors, list)
        if os.name == "nt":
            self.assertGreaterEqual(len(monitors), 1)
            # Ao menos um monitor deve ser marcado como primário
            has_primary = any(m.get("is_primary") for m in monitors)
            self.assertTrue(has_primary, "Deve haver ao menos um monitor principal detectado.")
            for m in monitors:
                self.assertIn("device", m)
                self.assertIn("is_primary", m)
                self.assertIn("monitor_rect", m)
                self.assertIn("work_rect", m)

    def test_get_primary_monitor_work_area(self):
        left, top, w, h = get_primary_monitor_work_area()
        self.assertIsInstance(left, int)
        self.assertIsInstance(top, int)
        self.assertGreater(w, 200)
        self.assertGreater(h, 200)

    def test_center_window_calculation(self):
        class DummyWindow:
            def __init__(self):
                self.geo = ""

            def geometry(self, g):
                self.geo = g

        dummy = DummyWindow()
        w, h, x, y = center_window_on_primary_screen(
            dummy,
            desired_width=1240,
            desired_height=780,
            min_width=1050,
            min_height=680,
        )
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertEqual(dummy.geo, f"{w}x{h}+{x}+{y}")

    def test_center_modal_on_parent(self):
        class DummyParent:
            def winfo_width(self):
                return 1240

            def winfo_height(self):
                return 780

            def winfo_x(self):
                return 100

            def winfo_y(self):
                return 50

        class DummyDialog:
            def __init__(self):
                self.geo = ""

            def update_idletasks(self):
                pass

            def geometry(self, g):
                self.geo = g

        dlg = DummyDialog()
        parent = DummyParent()
        geo = center_modal_on_parent(dlg, parent, 400, 300)
        self.assertIn("400x300", geo)
        self.assertIn("+", geo)


if __name__ == "__main__":
    unittest.main()

