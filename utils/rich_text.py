"""
Motor de Formatação Rica (Rich Text) para editores CTkTextbox (Tkinter tk.Text).
Suporta:
- Seleção de Fonte (família) e Tamanho (por trecho selecionado ou documento inteiro)
- Negrito (bold), Itálico (italic), Sublinhado (underline) e Riscado (overstrike) — combináveis entre si
- Digitação contínua com estilos ativos quando não há seleção
- Escala de fonte em pixels negativos idêntica ao CustomTkinter (evita mudança de tamanho ao ativar Negrito/Itálico)
- Recálculo de fontes compostas por algoritmo sweep-line de intervalos (O(K log K) em vez de O(N) por caractere)
- Integração com EditorHistoryManager para Desfazer (Ctrl+Z) e Refazer (Ctrl+Y)
- Serialização e restauração em JSON (formatting_json), mantendo o texto puro intacto no SQLite
"""

import json
import tkinter as tk
import tkinter.font as tkfont
from typing import Optional, Callable, Dict, List, Tuple, Any
import customtkinter as ctk

import config
from utils.editor_history import (
    commit_history_before_action,
    record_history_after_action,
)


AVAILABLE_FONTS: List[str] = [
    "Segoe UI",
    "Arial",
    "Calibri",
    "Consolas",
    "Courier New",
    "Georgia",
    "Tahoma",
    "Times New Roman",
    "Verdana",
]

AVAILABLE_FONT_SIZES: List[str] = [
    "10", "11", "12", "13", "14", "15", "16", "18", "20", "22", "24", "28", "32",
]

DEFAULT_FONT_FAMILY = "Segoe UI"
DEFAULT_FONT_SIZE = 15

TAG_BOLD = "rt_bold"
TAG_ITALIC = "rt_italic"
TAG_UNDERLINE = "rt_underline"
TAG_OVERSTRIKE = "rt_overstrike"
TAG_FAMILY_PREFIX = "rt_family::"
TAG_SIZE_PREFIX = "rt_size::"
TAG_COMP_PREFIX = "rt_comp::"


def _idx_to_tuple(idx_str: str) -> Tuple[int, int]:
    """Converte índice Tkinter 'linha.coluna' para tupla comparável (linha, coluna) em Python puro."""
    dot = idx_str.find(".")
    if dot == -1:
        return (1, 0)
    return (int(idx_str[:dot]), int(idx_str[dot + 1:]))


def _tuple_to_idx(pos: Tuple[int, int]) -> str:
    return f"{pos[0]}.{pos[1]}"


class RichTextController:
    """
    Controlador de formatação rica acoplado a um CTkTextbox.
    Permite combinar Fonte + Tamanho + Negrito + Itálico + Sublinhado + Riscado no mesmo trecho
    sem conflitar com destaque de sintaxe XML/SQL ou destaque de busca F3.
    """

    def __init__(
        self,
        ctk_textbox: ctk.CTkTextbox,
        on_change_callback: Optional[Callable[[], None]] = None,
        default_family: str = DEFAULT_FONT_FAMILY,
        default_size: int = DEFAULT_FONT_SIZE,
    ):
        self.ctk_textbox = ctk_textbox
        self.tb = ctk_textbox._textbox
        self.on_change_callback = on_change_callback

        # Expõe o controlador no CTkTextbox para integração com o EditorHistoryManager
        self.ctk_textbox._rich_text = self

        self.default_family = default_family
        self.default_size = int(default_size)
        self.base_family = default_family
        self.base_size = int(default_size)
        # Guarda a última fonte base aplicada no widget para evitar reflows redundantes
        self._applied_base_font: Tuple[str, int] = (default_family, int(default_size))

        # Estados de digitação quando não há texto selecionado
        self.typing_bold = False
        self.typing_italic = False
        self.typing_underline = False
        self.typing_overstrike = False

        # Referências opcionais aos widgets da barra de ferramentas para sincronização visual
        self._combo_font: Optional[ctk.CTkComboBox] = None
        self._combo_size: Optional[ctk.CTkComboBox] = None
        self._btn_bold: Optional[ctk.CTkButton] = None
        self._btn_italic: Optional[ctk.CTkButton] = None
        self._btn_underline: Optional[ctk.CTkButton] = None
        self._btn_overstrike: Optional[ctk.CTkButton] = None

        self._font_cache: Dict[Tuple[str, int, bool, bool, float], tkfont.Font] = {}
        self._configured_comp_tags: Dict[str, Tuple[str, int, bool, bool, float]] = {}
        self._pre_key_index: Optional[str] = None
        self._suppress_sync = False
        self._last_btn_states: Dict[int, bool] = {}

        self._setup_static_tags()
        try:
            # Preserva a seleção visual ('sel') mesmo ao clicar em comboboxes/botões da barra
            self.tb.configure(exportselection=False)
        except Exception:
            pass
        self._bind_events()

    def attach_toolbar_widgets(
        self,
        combo_font: Optional[ctk.CTkComboBox] = None,
        combo_size: Optional[ctk.CTkComboBox] = None,
        btn_bold: Optional[ctk.CTkButton] = None,
        btn_italic: Optional[ctk.CTkButton] = None,
        btn_underline: Optional[ctk.CTkButton] = None,
        btn_overstrike: Optional[ctk.CTkButton] = None,
    ):
        """Vincula os controles visuais da barra de ferramentas para refletir o estado ativo."""
        self._combo_font = combo_font
        self._combo_size = combo_size
        self._btn_bold = btn_bold
        self._btn_italic = btn_italic
        self._btn_underline = btn_underline
        self._btn_overstrike = btn_overstrike
        self._last_btn_states.clear()
        self.sync_toolbar_state()

    def _setup_static_tags(self):
        try:
            self.tb.tag_configure(TAG_UNDERLINE, underline=True)
            self.tb.tag_configure(TAG_OVERSTRIKE, overstrike=True)
        except Exception:
            pass

    def _bind_events(self):
        self.tb.bind("<KeyPress>", self._on_key_press, add="+")
        self.tb.bind("<KeyRelease>", self._on_key_release, add="+")
        self.tb.bind("<ButtonRelease-1>", lambda _e: self.sync_toolbar_state(), add="+")

        self.tb.bind("<Control-b>", lambda _e: (self.toggle_bold(), "break")[1])
        self.tb.bind("<Control-B>", lambda _e: (self.toggle_bold(), "break")[1])
        self.tb.bind("<Control-i>", lambda _e: (self.toggle_italic(), "break")[1])
        self.tb.bind("<Control-I>", lambda _e: (self.toggle_italic(), "break")[1])
        self.tb.bind("<Control-u>", lambda _e: (self.toggle_underline(), "break")[1])
        self.tb.bind("<Control-U>", lambda _e: (self.toggle_underline(), "break")[1])

    def _get_widget_scaling(self) -> float:
        try:
            scaling = float(self.ctk_textbox._get_widget_scaling())
            return scaling if scaling > 0 else 1.0
        except Exception:
            return 1.0

    def _get_scaled_pixel_size(self, size: int) -> int:
        """
        Calcula o tamanho da fonte em pixels negativos exatamente como CTkFont.create_scaled_tuple(),
        garantindo que Negrito/Itálico/Fonte nunca alterem a altura visual da fonte.
        """
        scaling = self._get_widget_scaling()
        return -max(1, round(int(size) * scaling))

    def _get_tk_font(self, family: str, size: int, is_bold: bool, is_italic: bool = False) -> tkfont.Font:
        scaling = round(self._get_widget_scaling(), 3)
        key = (family, int(size), bool(is_bold), bool(is_italic), scaling)
        if key not in self._font_cache:
            self._font_cache[key] = tkfont.Font(
                root=self.tb,
                family=family,
                size=self._get_scaled_pixel_size(size),
                weight="bold" if is_bold else "normal",
                slant="italic" if is_italic else "roman",
            )
        return self._font_cache[key]

    def _apply_base_font(self, force: bool = False):
        target = (self.base_family, int(self.base_size))
        if not force and self._applied_base_font == target:
            return
        try:
            self.ctk_textbox.configure(
                font=ctk.CTkFont(family=self.base_family, size=int(self.base_size))
            )
            self._applied_base_font = target
        except Exception:
            pass

    def _is_editable(self) -> bool:
        try:
            return str(self.tb.cget("state")) != "disabled"
        except Exception:
            return True

    def _get_selection(self) -> Optional[Tuple[str, str]]:
        try:
            ranges = self.tb.tag_ranges("sel")
            if ranges and len(ranges) >= 2:
                return (str(ranges[0]), str(ranges[1]))
        except Exception:
            pass
        return None

    def _range_fully_has_tag(self, tag_name: str, start: str, end: str) -> bool:
        """
        Verifica em O(K) usando tag_ranges se TODOS os caracteres em [start, end)
        possuem `tag_name`, evitando percorrer caractere por caractere no Tcl/Tk.
        """
        s_pos = _idx_to_tuple(self.tb.index(start))
        e_pos = _idx_to_tuple(self.tb.index(end))
        if s_pos >= e_pos:
            return False

        ranges = self.tb.tag_ranges(tag_name)
        if not ranges:
            return False

        # Como o tk.Text mescla automaticamente intervalos adjacentes da mesma tag,
        # basta verificar se algum intervalo [rs, re) cobre completamente [s_pos, e_pos)
        for i in range(0, len(ranges), 2):
            rs = _idx_to_tuple(str(ranges[i]))
            re_ = _idx_to_tuple(str(ranges[i + 1]))
            if rs <= s_pos and re_ >= e_pos:
                return True
            if rs > s_pos:
                return False
        return False

    def _clear_prefix_tags_in_range(self, prefix: str, start: str, end: str):
        for tag in self.tb.tag_names():
            if tag.startswith(prefix):
                self.tb.tag_remove(tag, start, end)

    def _recompute_composite_fonts(self, start: str, end: str):
        """
        Recalcula as tags compostas de fonte (family + size + bold + italic) no intervalo [start, end)
        usando algoritmo sweep-line sobre os intervalos retornados por `tag_ranges`.
        Complexidade O(K log K) no número de trechos formatados — independente do tamanho do texto!
        """
        s_idx = self.tb.index(start)
        e_idx = self.tb.index(end)
        s_pos = _idx_to_tuple(s_idx)
        e_pos = _idx_to_tuple(e_idx)
        if s_pos >= e_pos:
            return

        # Remove tags compostas antigas neste intervalo
        all_tags = self.tb.tag_names()
        for tag in all_tags:
            if tag.startswith(TAG_COMP_PREFIX):
                self.tb.tag_remove(tag, s_idx, e_idx)

        # Identifica apenas tags de fonte/tamanho/negrito/itálico existentes no widget
        font_tags: List[Tuple[str, str, Any]] = []
        for t in all_tags:
            if t == TAG_BOLD:
                font_tags.append((t, "bold", True))
            elif t == TAG_ITALIC:
                font_tags.append((t, "italic", True))
            elif t.startswith(TAG_FAMILY_PREFIX):
                font_tags.append((t, "family", t[len(TAG_FAMILY_PREFIX):]))
            elif t.startswith(TAG_SIZE_PREFIX):
                try:
                    font_tags.append((t, "size", int(t[len(TAG_SIZE_PREFIX):])))
                except ValueError:
                    pass

        if not font_tags:
            return

        # Coleta apenas intervalos que interceptam [s_pos, e_pos)
        # Eventos: (pos, delta (+1 entra / -1 sai), kind, value)
        events: List[Tuple[Tuple[int, int], int, str, Any]] = []
        for tag_name, kind, val in font_tags:
            ranges = self.tb.tag_ranges(tag_name)
            for i in range(0, len(ranges), 2):
                rs = _idx_to_tuple(str(ranges[i]))
                re_ = _idx_to_tuple(str(ranges[i + 1]))
                if re_ <= s_pos:
                    continue
                if rs >= e_pos:
                    break
                clamped_s = rs if rs > s_pos else s_pos
                clamped_e = re_ if re_ < e_pos else e_pos
                if clamped_s < clamped_e:
                    events.append((clamped_s, 1, kind, val))
                    events.append((clamped_e, -1, kind, val))

        if not events:
            return

        events.sort(key=lambda ev: ev[0])

        bold_cnt = 0
        italic_cnt = 0
        family_stack: List[str] = []
        size_stack: List[int] = []

        # Agrupa todos os segmentos por tag composta para aplicar em lote (1 tag_add por estilo)
        comp_batches: Dict[Tuple[str, int, bool, bool], List[str]] = {}

        idx_ev = 0
        n_ev = len(events)
        prev_pos = events[0][0]

        while idx_ev < n_ev:
            cur_pos = events[idx_ev][0]
            if cur_pos > prev_pos:
                fam = family_stack[-1] if family_stack else self.base_family
                sz = size_stack[-1] if size_stack else self.base_size
                bld = bold_cnt > 0
                itl = italic_cnt > 0
                if not (fam == self.base_family and sz == self.base_size and not bld and not itl):
                    key = (fam, sz, bld, itl)
                    batch = comp_batches.get(key)
                    if batch is None:
                        batch = []
                        comp_batches[key] = batch
                    batch.append(_tuple_to_idx(prev_pos))
                    batch.append(_tuple_to_idx(cur_pos))

            # Processa todos os eventos que ocorrem exatamente em cur_pos
            while idx_ev < n_ev and events[idx_ev][0] == cur_pos:
                _, delta, kind, val = events[idx_ev]
                if kind == "bold":
                    bold_cnt += delta
                elif kind == "italic":
                    italic_cnt += delta
                elif kind == "family":
                    if delta > 0:
                        family_stack.append(val)
                    else:
                        try:
                            family_stack.remove(val)
                        except ValueError:
                            pass
                elif kind == "size":
                    if delta > 0:
                        size_stack.append(val)
                    else:
                        try:
                            size_stack.remove(val)
                        except ValueError:
                            pass
                idx_ev += 1

            prev_pos = cur_pos

        if not comp_batches:
            return

        scaling = round(self._get_widget_scaling(), 3)
        for (fam, sz, bld, itl), flat_indices in comp_batches.items():
            comp_tag = f"{TAG_COMP_PREFIX}{fam}::{sz}::{1 if bld else 0}::{1 if itl else 0}"
            font_sig = (fam, sz, bld, itl, scaling)
            if self._configured_comp_tags.get(comp_tag) != font_sig:
                self.tb.tag_configure(comp_tag, font=self._get_tk_font(fam, sz, bld, itl))
                self._configured_comp_tags[comp_tag] = font_sig
            self.tb.tag_add(comp_tag, *flat_indices)
            try:
                self.tb.tag_raise(comp_tag)
            except Exception:
                pass

        # Garante sublinhado e riscado acima de sintaxe, e busca/seleção sempre no topo
        for tag in (TAG_UNDERLINE, TAG_OVERSTRIKE, "search_highlight", "search_highlight_current", "sel"):
            try:
                self.tb.tag_raise(tag)
            except Exception:
                pass

    # =========================================================================
    # Ações da Barra de Formatação
    # =========================================================================

    def toggle_bold(self):
        self._toggle_flag(TAG_BOLD, "typing_bold", recompute_font=True)

    def toggle_italic(self):
        self._toggle_flag(TAG_ITALIC, "typing_italic", recompute_font=True)

    def toggle_underline(self):
        self._toggle_flag(TAG_UNDERLINE, "typing_underline", recompute_font=False)

    def toggle_overstrike(self):
        self._toggle_flag(TAG_OVERSTRIKE, "typing_overstrike", recompute_font=False)

    def _toggle_flag(self, tag_name: str, typing_attr: str, recompute_font: bool):
        if not self._is_editable():
            return

        sel = self._get_selection()
        if sel:
            commit_history_before_action(self.ctk_textbox)
            start, end = sel
            already_on = self._range_fully_has_tag(tag_name, start, end)
            if already_on:
                self.tb.tag_remove(tag_name, start, end)
            else:
                self.tb.tag_add(tag_name, start, end)
            if recompute_font:
                self._recompute_composite_fonts(start, end)
            setattr(self, typing_attr, not already_on)
            record_history_after_action(self.ctk_textbox)
            self._notify_changed()
        else:
            setattr(self, typing_attr, not getattr(self, typing_attr))

        self._update_button_highlights()
        try:
            self.ctk_textbox.focus_set()
        except Exception:
            pass

    def apply_font_family(self, family: str):
        if not self._is_editable() or not family:
            return
        commit_history_before_action(self.ctk_textbox)
        sel = self._get_selection()
        if sel:
            start, end = sel
            self._clear_prefix_tags_in_range(TAG_FAMILY_PREFIX, start, end)
            if family != self.base_family:
                self.tb.tag_add(f"{TAG_FAMILY_PREFIX}{family}", start, end)
            self._recompute_composite_fonts(start, end)
        else:
            self.base_family = family
            self._apply_base_font()
            self._recompute_composite_fonts("1.0", "end-1c")

        record_history_after_action(self.ctk_textbox)
        self._notify_changed()
        self.sync_toolbar_state()
        self._refocus_textbox()

    def apply_font_size(self, size_val: Any):
        if not self._is_editable():
            return
        try:
            size = max(8, min(72, int(str(size_val).strip())))
        except Exception:
            return

        commit_history_before_action(self.ctk_textbox)
        sel = self._get_selection()
        if sel:
            start, end = sel
            self._clear_prefix_tags_in_range(TAG_SIZE_PREFIX, start, end)
            if size != self.base_size:
                self.tb.tag_add(f"{TAG_SIZE_PREFIX}{size}", start, end)
            self._recompute_composite_fonts(start, end)
        else:
            self.base_size = size
            self._apply_base_font()
            self._recompute_composite_fonts("1.0", "end-1c")

        record_history_after_action(self.ctk_textbox)
        self._notify_changed()
        self.sync_toolbar_state()
        self._refocus_textbox()

    def _refocus_textbox(self):
        """Devolve foco ao editor imediatamente e após o fechamento de dropdowns (CTkComboBox)."""
        try:
            self.tb.focus_set()
            if self.tb.winfo_exists():
                self.tb.after(15, lambda: self.tb.focus_set() if self.tb.winfo_exists() else None)
        except Exception:
            pass

    # =========================================================================
    # Digitação Contínua & Sincronização Visual
    # =========================================================================

    def _on_key_press(self, event):
        if not self._is_editable():
            return
        if event.state & 0x4:
            self._pre_key_index = None
            return
        if event.char and (event.char.isprintable() or event.char in ("\r", "\n", "\t")):
            try:
                self._pre_key_index = self.tb.index("insert")
            except Exception:
                self._pre_key_index = None
        else:
            self._pre_key_index = None

    def _on_key_release(self, event):
        if not self._is_editable():
            return
        if self._pre_key_index is not None:
            pre = self._pre_key_index
            self._pre_key_index = None
            try:
                post = self.tb.index("insert")
                if _idx_to_tuple(pre) < _idx_to_tuple(post):
                    any_active = (
                        self.typing_bold
                        or self.typing_italic
                        or self.typing_underline
                        or self.typing_overstrike
                    )
                    if self.typing_bold:
                        self.tb.tag_add(TAG_BOLD, pre, post)
                    else:
                        self.tb.tag_remove(TAG_BOLD, pre, post)

                    if self.typing_italic:
                        self.tb.tag_add(TAG_ITALIC, pre, post)
                    else:
                        self.tb.tag_remove(TAG_ITALIC, pre, post)

                    if self.typing_underline:
                        self.tb.tag_add(TAG_UNDERLINE, pre, post)
                    else:
                        self.tb.tag_remove(TAG_UNDERLINE, pre, post)

                    if self.typing_overstrike:
                        self.tb.tag_add(TAG_OVERSTRIKE, pre, post)
                    else:
                        self.tb.tag_remove(TAG_OVERSTRIKE, pre, post)

                    # Só recalcula se houver estilo ativo ou tag composta herdada no caractere digitado
                    if any_active or any(
                        t.startswith((TAG_COMP_PREFIX, TAG_FAMILY_PREFIX, TAG_SIZE_PREFIX))
                        for t in self.tb.tag_names(pre)
                    ):
                        self._recompute_composite_fonts(pre, post)
            except Exception:
                pass
        elif event.keysym in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"):
            self.sync_toolbar_state()

    def sync_toolbar_state(self):
        """Atualiza os seletores de fonte/tamanho e o destaque de B/I/U/S conforme a posição atual."""
        if self._suppress_sync:
            return
        try:
            sel = self._get_selection()
            probe_idx = sel[0] if sel else self.tb.index("insert - 1c")
            tags = self.tb.tag_names(probe_idx) if self.tb.compare("1.0", "<", "end-1c") else ()

            fam = self.base_family
            sz = self.base_size
            is_bold = TAG_BOLD in tags
            is_italic = TAG_ITALIC in tags
            is_under = TAG_UNDERLINE in tags
            is_strike = TAG_OVERSTRIKE in tags

            for t in tags:
                if t.startswith(TAG_FAMILY_PREFIX):
                    fam = t[len(TAG_FAMILY_PREFIX):]
                elif t.startswith(TAG_SIZE_PREFIX):
                    try:
                        sz = int(t[len(TAG_SIZE_PREFIX):])
                    except ValueError:
                        pass

            self.typing_bold = is_bold
            self.typing_italic = is_italic
            self.typing_underline = is_under
            self.typing_overstrike = is_strike

            if self._combo_font is not None and self._combo_font.winfo_exists():
                if self._combo_font.get() != fam:
                    self._combo_font.set(fam)
            if self._combo_size is not None and self._combo_size.winfo_exists():
                if self._combo_size.get() != str(sz):
                    self._combo_size.set(str(sz))

            self._update_button_highlights()
        except Exception:
            pass

    def _update_button_highlights(self):
        mapping = [
            (self._btn_bold, self.typing_bold),
            (self._btn_italic, self.typing_italic),
            (self._btn_underline, self.typing_underline),
            (self._btn_overstrike, self.typing_overstrike),
        ]
        for btn, active in mapping:
            if btn is None:
                continue
            bid = id(btn)
            if self._last_btn_states.get(bid) == active:
                continue
            try:
                if not btn.winfo_exists():
                    continue
                if active:
                    btn.configure(
                        fg_color=config.COLORS["primary"],
                        text_color="#FFFFFF",
                    )
                else:
                    btn.configure(
                        fg_color=config.COLORS["card_dark"],
                        text_color=config.COLORS["button_text"],
                    )
                self._last_btn_states[bid] = active
            except Exception:
                pass

    def _notify_changed(self):
        if self.on_change_callback:
            try:
                self.on_change_callback()
            except Exception:
                pass

    # =========================================================================
    # Serialização / Carregamento / Reset
    # =========================================================================

    def reset(self):
        """Limpa todas as tags de formatação rica e restaura fonte/tamanho padrão."""
        self.base_family = self.default_family
        self.base_size = self.default_size
        self.typing_bold = False
        self.typing_italic = False
        self.typing_underline = False
        self.typing_overstrike = False

        try:
            for tag in self.tb.tag_names():
                if tag in (TAG_BOLD, TAG_ITALIC, TAG_UNDERLINE, TAG_OVERSTRIKE) or tag.startswith(
                    (TAG_FAMILY_PREFIX, TAG_SIZE_PREFIX, TAG_COMP_PREFIX)
                ):
                    self.tb.tag_remove(tag, "1.0", "end")
        except Exception:
            pass

        self._apply_base_font()
        self.sync_toolbar_state()

    def serialize(self) -> str:
        """
        Exporta a formatação atual (fonte base, tamanho base e intervalos formatados)
        como string JSON compacta. Retorna '' se não houver formatação customizada.
        """
        spans: List[Dict[str, str]] = []
        try:
            for tag in self.tb.tag_names():
                logical_name: Optional[str] = None
                if tag == TAG_BOLD:
                    logical_name = "bold"
                elif tag == TAG_ITALIC:
                    logical_name = "italic"
                elif tag == TAG_UNDERLINE:
                    logical_name = "underline"
                elif tag == TAG_OVERSTRIKE:
                    logical_name = "overstrike"
                elif tag.startswith(TAG_FAMILY_PREFIX):
                    logical_name = f"family:{tag[len(TAG_FAMILY_PREFIX):]}"
                elif tag.startswith(TAG_SIZE_PREFIX):
                    logical_name = f"size:{tag[len(TAG_SIZE_PREFIX):]}"

                if not logical_name:
                    continue

                ranges = self.tb.tag_ranges(tag)
                for i in range(0, len(ranges), 2):
                    s = str(ranges[i])
                    e = str(ranges[i + 1])
                    if _idx_to_tuple(s) < _idx_to_tuple(e):
                        spans.append({"tag": logical_name, "start": s, "end": e})
        except Exception:
            pass

        if (
            self.base_family == self.default_family
            and self.base_size == self.default_size
            and not spans
        ):
            return ""

        payload = {
            "font_family": self.base_family,
            "font_size": int(self.base_size),
            "spans": spans,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def load(self, formatting_json: Optional[str]):
        """Restaura a formatação rica salva em JSON sobre o texto já carregado no editor."""
        self._suppress_sync = True
        try:
            self.base_family = self.default_family
            self.base_size = self.default_size
            self.typing_bold = False
            self.typing_italic = False
            self.typing_underline = False
            self.typing_overstrike = False

            # Limpa apenas tags de formatação existentes
            for tag in self.tb.tag_names():
                if tag in (TAG_BOLD, TAG_ITALIC, TAG_UNDERLINE, TAG_OVERSTRIKE) or tag.startswith(
                    (TAG_FAMILY_PREFIX, TAG_SIZE_PREFIX, TAG_COMP_PREFIX)
                ):
                    self.tb.tag_remove(tag, "1.0", "end")

            if not formatting_json or not str(formatting_json).strip():
                self._apply_base_font()
                return

            data = json.loads(formatting_json)
            if not isinstance(data, dict):
                self._apply_base_font()
                return

            fam = data.get("font_family")
            if isinstance(fam, str) and fam.strip():
                self.base_family = fam.strip()

            sz = data.get("font_size")
            if sz is not None:
                try:
                    self.base_size = max(8, min(72, int(sz)))
                except Exception:
                    pass

            self._apply_base_font()

            # Agrupa spans por tag para aplicar em lote (muito mais rápido em documentos grandes)
            batches: Dict[str, List[str]] = {}
            for sp in data.get("spans", []):
                if not isinstance(sp, dict):
                    continue
                t_logical = sp.get("tag", "")
                s = sp.get("start")
                e = sp.get("end")
                if not t_logical or not s or not e:
                    continue
                tk_tag: Optional[str] = None
                if t_logical == "bold":
                    tk_tag = TAG_BOLD
                elif t_logical == "italic":
                    tk_tag = TAG_ITALIC
                elif t_logical == "underline":
                    tk_tag = TAG_UNDERLINE
                elif t_logical == "overstrike":
                    tk_tag = TAG_OVERSTRIKE
                elif t_logical.startswith("family:"):
                    f_name = t_logical.split(":", 1)[1].strip()
                    if f_name:
                        tk_tag = f"{TAG_FAMILY_PREFIX}{f_name}"
                elif t_logical.startswith("size:"):
                    sz_str = t_logical.split(":", 1)[1].strip()
                    if sz_str.isdigit():
                        tk_tag = f"{TAG_SIZE_PREFIX}{sz_str}"

                if tk_tag:
                    batches.setdefault(tk_tag, []).extend((str(s), str(e)))

            for tk_tag, flat_indices in batches.items():
                if flat_indices:
                    self.tb.tag_add(tk_tag, *flat_indices)

            if batches:
                self._recompute_composite_fonts("1.0", "end-1c")
        except Exception:
            pass
        finally:
            self._suppress_sync = False
            self.sync_toolbar_state()


def apply_formatting_to_textbox(ctk_textbox: ctk.CTkTextbox, formatting_json: Optional[str]) -> RichTextController:
    """Utilitário rápido para aplicar formatação rica salva em um CTkTextbox de leitura/preview."""
    ctrl = RichTextController(ctk_textbox)
    ctrl.load(formatting_json)
    return ctrl
