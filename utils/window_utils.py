"""
Utilitários de detecção de múltiplos monitores e posicionamento de janelas no Windows.
Garante que a aplicação sempre abra perfeitamente centralizada na TELA PRINCIPAL (Primary Monitor),
mesmo em setups com 2 ou mais telas com diferentes resoluções e posições relativas.
"""

import os
import sys
import logging
from typing import Tuple, Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def get_display_monitors() -> List[Dict[str, Any]]:
    """
    Enumera todos os monitores conectados no Windows.
    Retorna uma lista de dicionários contendo:
    - 'device': nome do dispositivo (ex: '\\\\.\\DISPLAY1')
    - 'is_primary': bool indicando se é a tela principal
    - 'monitor_rect': (left, top, right, bottom) limites totais do monitor
    - 'work_rect': (left, top, right, bottom) área de trabalho útil (descontando taskbar)
    """
    monitors: List[Dict[str, Any]] = []

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            class MONITORINFOEX(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32),
                ]

            def _enum_callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
                mi = MONITORINFOEX()
                mi.cbSize = ctypes.sizeof(MONITORINFOEX)
                if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
                    is_primary = bool(mi.dwFlags & 1)  # MONITORINFOF_PRIMARY = 1
                    monitors.append({
                        "device": str(mi.szDevice),
                        "is_primary": is_primary,
                        "monitor_rect": (mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom),
                        "work_rect": (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom),
                    })
                return 1

            MONITORENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL,
                wintypes.HMONITOR,
                wintypes.HDC,
                ctypes.POINTER(RECT),
                wintypes.LPARAM,
            )

            ctypes.windll.user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_enum_callback), 0)
        except Exception as e:
            logger.warning("Falha ao enumerar monitores via EnumDisplayMonitors: %s", e)

    return monitors


def get_primary_monitor_work_area() -> Tuple[int, int, int, int]:
    """
    Retorna (left, top, width, height) da área útil da TELA PRINCIPAL (Primary Monitor).
    Garante que coordenadas de monitores secundários (positivas ou negativas) não interfiram.
    """
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD),
                ]

            # Ponto (0, 0) com MONITOR_DEFAULTTOPRIMARY (1) garante a tela principal
            hmonitor = ctypes.windll.user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
                left = int(mi.rcWork.left)
                top = int(mi.rcWork.top)
                w = int(mi.rcWork.right - mi.rcWork.left)
                h = int(mi.rcWork.bottom - mi.rcWork.top)
                if w > 200 and h > 200:
                    return (left, top, w, h)
        except Exception as ex:
            logger.warning("Falha ao obter área de trabalho do monitor principal: %s", ex)

    # Fallback genérico caso não seja Windows ou ocorra erro
    return (0, 0, 1280, 720)


def center_window_on_primary_screen(
    window,
    desired_width: int = 1240,
    desired_height: int = 780,
    min_width: int = 1050,
    min_height: int = 680,
) -> Tuple[int, int, int, int]:
    """
    Calcula e aplica a geometria perfeitamente centralizada na TELA PRINCIPAL.
    Considera configurações de múltiplos monitores e ajusta proporções de forma segura.
    Retorna (final_w, final_h, pos_x, pos_y).
    """
    left, top, screen_w, screen_h = get_primary_monitor_work_area()

    # Ajusta o tamanho da janela se a tela principal for menor que o desejado
    # Deixa uma margem de segurança de pelo menos 20px nas bordas
    max_avail_w = max(min_width, screen_w - 40)
    max_avail_h = max(min_height, screen_h - 40)

    final_w = min(desired_width, max_avail_w)
    final_h = min(desired_height, max_avail_h)

    # Centraliza exatamente no espaço útil da tela principal
    pos_x = left + max(0, (screen_w - final_w) // 2)
    pos_y = top + max(0, (screen_h - final_h) // 2)

    geo_string = f"{final_w}x{final_h}+{pos_x}+{pos_y}"
    try:
        window.geometry(geo_string)
    except Exception as e:
        logger.warning("Erro ao aplicar geometry centralizada: %s", e)

    return (final_w, final_h, pos_x, pos_y)


def center_modal_on_parent(dialog, parent, win_w: int, win_h: int) -> str:
    """
    Posiciona uma janela modal perfeitamente centralizada sobre o parent,
    garantindo que não saia dos limites visíveis da tela útil do monitor.
    """
    try:
        dialog.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()

        left, top, screen_w, screen_h = get_primary_monitor_work_area()

        if pw > 100 and ph > 100:
            target_x = px + (pw // 2) - (win_w // 2)
            target_y = py + (ph // 2) - (win_h // 2)
        else:
            target_x = left + (screen_w - win_w) // 2
            target_y = top + (screen_h - win_h) // 2

        # Garante que o diálogo não ultrapasse as bordas da tela
        target_x = max(left + 10, min(target_x, left + screen_w - win_w - 10))
        target_y = max(top + 10, min(target_y, top + screen_h - win_h - 10))

        geo = f"{win_w}x{win_h}+{target_x}+{target_y}"
        dialog.geometry(geo)
        return geo
    except Exception as e:
        logger.warning("Erro ao posicionar modal: %s", e)
        geo = f"{win_w}x{win_h}"
        dialog.geometry(geo)
        return geo
