"""
Atalhos inteligentes para os editores de texto do DailyNotes (Diário, Notas & Pastas e Leitor/Editor):
- F5: Insere a data e hora atual formatada (DD/MM/AAAA HH:MM) na posição do cursor.
- Ctrl+Space:
    1. Completa palavra/frase sugerida pelo corretor ortográfico do Windows, pelo dicionário
       personalizado ou por frases já digitadas na nota (apertar novamente cicla entre sugestões).
    2. Corrige automaticamente erro ortográfico sob o cursor ou no fim do texto (inclusive após
       espaço, pontuação ou quebra de linha).
Todas as operações são registradas no EditorHistoryManager (suportando Ctrl+Z / Ctrl+Y)
e preservam a formatação rica (Fonte, Tamanho, Negrito, Itálico, Sublinhado e Riscado).
"""

import datetime
import re
from typing import Callable, List, Optional, Tuple
import customtkinter as ctk

from utils.editor_history import (
    commit_history_before_action,
    record_history_after_action,
)
from utils.text_utils import normalize_text

# Regex para palavras Unicode (inclui acentos, cedilha e hífen interno)
_RE_WORD_CHARS = re.compile(r"[^\W\d_]", re.UNICODE)
_RE_ALL_WORDS = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)


def format_current_datetime_br(now: Optional[datetime.datetime] = None) -> str:
    """Retorna data e hora atuais no formato brasileiro 'DD/MM/AAAA HH:MM'."""
    dt = now or datetime.datetime.now()
    return dt.strftime("%d/%m/%Y %H:%M")


def _preserve_case(original: str, suggestion: str) -> str:
    """Adapta a capitalização da sugestão à caixa da palavra original (se aplicável)."""
    if not original or not suggestion:
        return suggestion
    if original.isupper() and len(original) > 1:
        return suggestion.upper()
    if original[0].isupper() and suggestion[0].islower():
        return suggestion[0].upper() + suggestion[1:]
    return suggestion


def insert_current_datetime(
    ctk_textbox: ctk.CTkTextbox,
    on_change_callback: Optional[Callable[[], None]] = None,
    now: Optional[datetime.datetime] = None,
) -> Optional[str]:
    """
    Insere a data e hora atual ('DD/MM/AAAA HH:MM') na posição do cursor (ou substituindo a seleção),
    registrando um passo atômico no histórico de Desfazer/Refazer (Ctrl+Z / Ctrl+Y).
    """
    tb = ctk_textbox._textbox
    try:
        if str(tb.cget("state")) == "disabled":
            return None
    except Exception:
        return None

    stamp = format_current_datetime_br(now)
    commit_history_before_action(ctk_textbox)

    try:
        tb.edit_separator()
    except Exception:
        pass

    if tb.tag_ranges("sel"):
        tb.delete("sel.first", "sel.last")

    start_pos = tb.index("insert")
    tb.insert(start_pos, stamp)
    end_pos = tb.index(f"{start_pos} + {len(stamp)} chars")
    tb.mark_set("insert", end_pos)

    # Aplica estilos de digitação ativos do RichTextController (se houver)
    rich_text = getattr(ctk_textbox, "_rich_text", None)
    if rich_text is not None:
        try:
            from utils.rich_text import TAG_BOLD, TAG_ITALIC, TAG_UNDERLINE, TAG_OVERSTRIKE
            if rich_text.typing_bold:
                tb.tag_add(TAG_BOLD, start_pos, end_pos)
            if rich_text.typing_italic:
                tb.tag_add(TAG_ITALIC, start_pos, end_pos)
            if rich_text.typing_underline:
                tb.tag_add(TAG_UNDERLINE, start_pos, end_pos)
            if rich_text.typing_overstrike:
                tb.tag_add(TAG_OVERSTRIKE, start_pos, end_pos)
            rich_text._recompute_composite_fonts(start_pos, end_pos)
        except Exception:
            pass

    try:
        tb.edit_separator()
    except Exception:
        pass

    record_history_after_action(ctk_textbox)
    try:
        tb.see(end_pos)
        tb.focus_set()
    except Exception:
        pass

    if on_change_callback:
        try:
            on_change_callback()
        except Exception:
            pass

    return stamp


class EditorAssistController:
    """
    Controlador acoplado a um CTkTextbox para:
    - F5: Inserir data e hora atual
    - Ctrl+Space: Completar palavra/frase sugerida e corrigir erro ortográfico (no cursor ou no fim do texto)
    """

    def __init__(
        self,
        ctk_textbox: ctk.CTkTextbox,
        spell_service_getter: Callable[[], object],
        on_change_callback: Optional[Callable[[], None]] = None,
        on_after_spell_change: Optional[Callable[[], None]] = None,
        on_status_feedback: Optional[Callable[[str], None]] = None,
    ):
        self.ctk_textbox = ctk_textbox
        self.tb = ctk_textbox._textbox
        self._get_spell_service = spell_service_getter
        self.on_change_callback = on_change_callback
        self.on_after_spell_change = on_after_spell_change
        self.on_status_feedback = on_status_feedback

        # Estado para alternar (ciclar) entre múltiplas sugestões em pressionamentos consecutivos de Ctrl+Space
        self._cycle_state: Optional[dict] = None

        self._bind_events()

    def _bind_events(self):
        self.tb.bind("<F5>", self._on_f5, add="+")
        self.tb.bind("<Control-space>", self._on_ctrl_space)
        self.tb.bind("<Control-Shift-space>", self._on_ctrl_space)
        self.tb.bind("<KeyPress>", self._on_any_key_press, add="+")
        self.tb.bind("<ButtonRelease-1>", lambda _e: self._clear_cycle(), add="+")

    def _clear_cycle(self):
        self._cycle_state = None

    def _on_any_key_press(self, event):
        keysym = getattr(event, "keysym", "")
        if keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R"):
            return
        if (event.state & 0x4) and keysym == "space":
            return
        self._cycle_state = None

    def _is_editable(self) -> bool:
        try:
            return str(self.tb.cget("state")) != "disabled"
        except Exception:
            return False

    def _on_f5(self, _event=None):
        self._clear_cycle()
        stamp = insert_current_datetime(
            self.ctk_textbox,
            on_change_callback=self.on_change_callback,
        )
        if stamp and self.on_status_feedback:
            try:
                self.on_status_feedback(f"🕒 Data/hora inserida: {stamp}")
            except Exception:
                pass
        return "break"

    def _on_ctrl_space(self, _event=None):
        self.trigger_smart_complete_or_correct()
        return "break"

    def _replace_span_preserving_tags(
        self,
        start_offset: int,
        end_offset: int,
        replacement: str,
        move_cursor_to_end: bool = True,
    ) -> Tuple[int, int]:
        """Substitui o intervalo [start_offset, end_offset) preservando formatação rica e registrando Undo."""
        start_idx = self.tb.index(f"1.0 + {start_offset} chars")
        end_idx = self.tb.index(f"1.0 + {end_offset} chars")

        # Captura tags de formatação rica da palavra substituída (ignora sel e spelling_error)
        preserved_tags = [
            t for t in self.tb.tag_names(start_idx)
            if t not in ("sel", "spelling_error", "search_highlight", "search_highlight_current")
        ]

        orig_cursor_offset = len(self.tb.get("1.0", "insert"))

        commit_history_before_action(self.ctk_textbox)
        try:
            self.tb.edit_separator()
        except Exception:
            pass

        self.tb.delete(start_idx, end_idx)
        self.tb.insert(start_idx, replacement)
        new_end_offset = start_offset + len(replacement)
        new_end_idx = self.tb.index(f"1.0 + {new_end_offset} chars")

        for t in preserved_tags:
            try:
                self.tb.tag_add(t, start_idx, new_end_idx)
            except Exception:
                pass
        self.tb.tag_remove("spelling_error", start_idx, new_end_idx)

        if move_cursor_to_end:
            self.tb.mark_set("insert", new_end_idx)
        else:
            delta = len(replacement) - (end_offset - start_offset)
            adjusted = max(0, orig_cursor_offset + delta)
            self.tb.mark_set("insert", self.tb.index(f"1.0 + {adjusted} chars"))

        try:
            self.tb.edit_separator()
        except Exception:
            pass

        record_history_after_action(self.ctk_textbox)

        try:
            self.tb.see("insert")
            self.tb.focus_set()
        except Exception:
            pass

        if self.on_change_callback:
            try:
                self.on_change_callback()
            except Exception:
                pass
        if self.on_after_spell_change:
            try:
                self.on_after_spell_change()
            except Exception:
                pass

        return start_offset, new_end_offset

    @staticmethod
    def _find_word_bounds_at(text: str, cursor_offset: int) -> Optional[Tuple[int, int]]:
        """Retorna (start, end) da palavra sob ou imediatamente à esquerda do cursor."""
        n = len(text)
        if n == 0:
            return None

        pos = min(max(0, cursor_offset), n)
        # Verifica se há letra na posição do cursor ou imediatamente antes
        probe = None
        if pos > 0 and _RE_WORD_CHARS.match(text[pos - 1]):
            probe = pos - 1
        elif pos < n and _RE_WORD_CHARS.match(text[pos]):
            probe = pos

        if probe is None:
            return None

        start = probe
        while start > 0 and (_RE_WORD_CHARS.match(text[start - 1]) or (text[start - 1] == "-" and start > 1 and _RE_WORD_CHARS.match(text[start - 2]))):
            start -= 1

        end = probe + 1
        while end < n and (_RE_WORD_CHARS.match(text[end]) or (text[end] == "-" and end + 1 < n and _RE_WORD_CHARS.match(text[end + 1]))):
            end += 1

        return (start, end)

    @staticmethod
    def _find_phrase_completion(full_text: str, cursor_offset: int) -> Optional[Tuple[int, int, List[str]]]:
        """
        Procura no texto anterior da própria nota uma frase que comece exatamente pelo
        fragmento atual da linha antes do cursor (mínimo 2 palavras ou >= 4 chars),
        retornando (replace_start, replace_end, [frases_completas]).
        """
        line_start = full_text.rfind("\n", 0, cursor_offset) + 1
        fragment = full_text[line_start:cursor_offset]
        stripped_frag = fragment.lstrip()
        if len(stripped_frag) < 4:
            return None

        # Só completa frase quando há pelo menos 2 palavras (ou espaço no meio) para evitar falsos positivos
        if " " not in stripped_frag:
            return None

        frag_start = cursor_offset - len(stripped_frag)
        norm_frag = normalize_text(stripped_frag)
        if not norm_frag or len(norm_frag) < 4:
            return None

        # Busca em linhas anteriores (ou antes do fragmento atual)
        search_area = full_text[:frag_start]
        if not search_area.strip():
            return None

        candidates: List[str] = []
        seen = set()
        for line in search_area.splitlines():
            clean_line = line.strip()
            if len(clean_line) <= len(stripped_frag):
                continue
            norm_line = normalize_text(clean_line)
            idx = norm_line.find(norm_frag)
            if idx != -1:
                # Garante fronteira de palavra no início do match
                if idx > 0 and _RE_WORD_CHARS.match(norm_line[idx - 1]):
                    continue
                # Mapeia posição aproximada para o texto original da linha
                completion = clean_line[idx:].strip()
                if len(completion) > len(stripped_frag) and completion.lower() not in seen:
                    seen.add(completion.lower())
                    candidates.append(completion)
                    if len(candidates) >= 5:
                        break

        if candidates:
            return (frag_start, cursor_offset, candidates)
        return None

    @staticmethod
    def _collect_prefix_matches_from_vocab(
        prefix: str,
        full_text: str,
        exclude_span: Tuple[int, int],
        custom_words: Optional[List[str]] = None,
    ) -> List[str]:
        """Retorna palavras do dicionário personalizado e do próprio texto que completam `prefix`."""
        norm_prefix = normalize_text(prefix)
        if len(norm_prefix) < 2:
            return []

        results: List[str] = []
        seen = {norm_prefix}

        # 1. Dicionário personalizado
        for w in (custom_words or []):
            nw = normalize_text(w)
            if len(nw) > len(norm_prefix) and nw.startswith(norm_prefix) and nw not in seen:
                seen.add(nw)
                results.append(w)

        # 2. Palavras já usadas no texto atual (fora do trecho que está sendo digitado)
        ex_s, ex_e = exclude_span
        for m in _RE_ALL_WORDS.finditer(full_text):
            if m.start() == ex_s and m.end() == ex_e:
                continue
            w = m.group(0)
            nw = normalize_text(w)
            if len(nw) > len(norm_prefix) and nw.startswith(norm_prefix) and nw not in seen:
                seen.add(nw)
                results.append(w)
                if len(results) >= 6:
                    break

        return results

    def _is_in_syntax_block(self, char_offset: int) -> bool:
        try:
            idx = self.tb.index(f"1.0 + {char_offset} chars")
            return any(t.startswith("syntax_") for t in self.tb.tag_names(idx))
        except Exception:
            return False

    def trigger_smart_complete_or_correct(self) -> Optional[Tuple[str, str]]:
        """
        Executa a ação inteligente de Ctrl+Space:
        - Se pressionado em sequência no mesmo ponto, alterna entre as sugestões disponíveis.
        - Se a palavra no cursor tiver erro ortográfico, corrige imediatamente com a melhor sugestão.
        - Se houver completamento de frase/palavra (corretor, dicionário ou texto), completa o trecho.
        - Se não houver palavra editável no cursor (ex.: após espaço/ponto/Enter no fim do texto)
          ou se a palavra atual já estiver correta sem completamento, localiza e corrige o erro
          ortográfico mais próximo antes do cursor (ou no fim do texto).
        Retorna (texto_original, texto_aplicado) ou None se não houver sugestão aplicável.
        """
        if not self._is_editable():
            return None

        full_text = self.tb.get("1.0", "end-1c")
        if not full_text.strip():
            return None

        cursor_offset = len(self.tb.get("1.0", "insert"))

        # 1. Ciclo de sugestões em pressionamentos consecutivos de Ctrl+Space no mesmo ponto
        if self._cycle_state is not None:
            st = self._cycle_state
            if (
                cursor_offset == st["end_offset"]
                and full_text[st["start_offset"] : st["end_offset"]] == st["current_text"]
                and len(st["candidates"]) > 1
            ):
                next_idx = (st["index"] + 1) % len(st["candidates"])
                prev_text = st["current_text"]
                next_text = st["candidates"][next_idx]
                s_off, new_e_off = self._replace_span_preserving_tags(
                    st["start_offset"],
                    st["end_offset"],
                    next_text,
                    move_cursor_to_end=True,
                )
                st["start_offset"] = s_off
                st["end_offset"] = new_e_off
                st["current_text"] = next_text
                st["index"] = next_idx
                if self.on_status_feedback:
                    try:
                        self.on_status_feedback(
                            f"✨ Sugestão {next_idx + 1}/{len(st['candidates'])}: {next_text}"
                        )
                    except Exception:
                        pass
                return (prev_text, next_text)
            self._cycle_state = None

        spell_service = self._get_spell_service() if self._get_spell_service else None
        spell_ok = bool(spell_service and getattr(spell_service, "is_available", False))
        custom_words = list(getattr(spell_service, "_custom_words", ())) if spell_service else []

        # 2. Verifica completamento de frase no contexto da linha atual (ex.: "Relatório de em|" -> frase anterior)
        phrase_match = self._find_phrase_completion(full_text, cursor_offset)

        # 3. Analisa a palavra sob ou imediatamente antes do cursor
        word_bounds = self._find_word_bounds_at(full_text, cursor_offset)
        if word_bounds is not None:
            w_start, w_end = word_bounds
            word = full_text[w_start:w_end]
            norm_word = normalize_text(word)

            is_word_error = False
            if spell_ok:
                word_errs = spell_service.check_text(word)
                is_word_error = bool(word_errs)

            candidates: List[str] = []
            seen_lower = {word.lower()}

            def _add_candidate(cand: str):
                if not cand or cand.lower() in seen_lower:
                    return
                seen_lower.add(cand.lower())
                candidates.append(_preserve_case(word, cand))

            if is_word_error:
                # Se a frase anterior da nota completa exatamente o prefixo de 2+ palavras, prioriza a frase
                if phrase_match is not None:
                    p_start, p_end, p_cands = phrase_match
                    applied = p_cands[0]
                    orig = full_text[p_start:p_end]
                    s_off, e_off = self._replace_span_preserving_tags(
                        p_start, p_end, applied, move_cursor_to_end=True
                    )
                    if len(p_cands) > 1:
                        self._cycle_state = {
                            "start_offset": s_off,
                            "end_offset": e_off,
                            "current_text": applied,
                            "candidates": p_cands,
                            "index": 0,
                        }
                    if self.on_status_feedback:
                        try:
                            self.on_status_feedback(f"✨ Frase completada: {applied}")
                        except Exception:
                            pass
                    return (orig, applied)

                # Sugestões do corretor nativo do Windows para a palavra com erro/incompleta
                win_sugs = spell_service.get_suggestions(word, limit=8) if spell_ok else []
                vocab_sugs = self._collect_prefix_matches_from_vocab(
                    word, full_text, (w_start, w_end), custom_words
                )
                for s in win_sugs:
                    _add_candidate(s)
                for s in vocab_sugs:
                    _add_candidate(s)
            else:
                # Palavra válida no cursor: primeiro tenta completar frase anterior
                if phrase_match is not None:
                    p_start, p_end, p_cands = phrase_match
                    applied = p_cands[0]
                    orig = full_text[p_start:p_end]
                    s_off, e_off = self._replace_span_preserving_tags(
                        p_start, p_end, applied, move_cursor_to_end=True
                    )
                    if len(p_cands) > 1:
                        self._cycle_state = {
                            "start_offset": s_off,
                            "end_offset": e_off,
                            "current_text": applied,
                            "candidates": p_cands,
                            "index": 0,
                        }
                    if self.on_status_feedback:
                        try:
                            self.on_status_feedback(f"✨ Frase completada: {applied}")
                        except Exception:
                            pass
                    return (orig, applied)

                # Tenta completar palavra maior a partir do dicionário personalizado / documento
                vocab_sugs = self._collect_prefix_matches_from_vocab(
                    word, full_text, (w_start, w_end), custom_words
                )
                for s in vocab_sugs:
                    _add_candidate(s)

                # Tenta sugestões do corretor que realmente estendem a palavra como prefixo (ex: "configura" -> "configurar")
                if spell_ok and len(norm_word) >= 3:
                    win_sugs = spell_service.get_suggestions(word, limit=8)
                    for s in win_sugs:
                        ns = normalize_text(s)
                        if len(ns) > len(norm_word) and ns.startswith(norm_word):
                            _add_candidate(s)

            if candidates:
                best = candidates[0]
                s_off, e_off = self._replace_span_preserving_tags(
                    w_start, w_end, best, move_cursor_to_end=True
                )
                if len(candidates) > 1:
                    self._cycle_state = {
                        "start_offset": s_off,
                        "end_offset": e_off,
                        "current_text": best,
                        "candidates": candidates,
                        "index": 0,
                    }
                if self.on_status_feedback:
                    try:
                        hint = f" (Ctrl+Espaço para mais {len(candidates) - 1})" if len(candidates) > 1 else ""
                        action_lbl = "Corrigido" if is_word_error else "Completado"
                        self.on_status_feedback(f"✨ {action_lbl}: {word} → {best}{hint}")
                    except Exception:
                        pass
                return (word, best)

        # 4. Fallback inteligente (fim do texto após ponto/espaço/Enter ou erro ortográfico pendente):
        #    Localiza e corrige o erro ortográfico mais próximo antes do cursor (ou no fim do texto).
        if spell_ok:
            all_errors = [
                err for err in spell_service.check_text(full_text)
                if not self._is_in_syntax_block(err.start)
            ]
            if all_errors:
                # Prioriza o último erro cujo final está antes ou igual ao cursor (fim do texto / frase)
                before_cursor = [e for e in all_errors if (e.start + e.length) <= cursor_offset]
                target_err = before_cursor[-1] if before_cursor else all_errors[-1]
                sugs = spell_service.get_suggestions(target_err.word, limit=6)
                if sugs:
                    best = _preserve_case(target_err.word, sugs[0])
                    is_touching = (target_err.start + target_err.length == cursor_offset)
                    s_off, e_off = self._replace_span_preserving_tags(
                        target_err.start,
                        target_err.start + target_err.length,
                        best,
                        move_cursor_to_end=is_touching,
                    )
                    if is_touching and len(sugs) > 1:
                        all_cands = [_preserve_case(target_err.word, s) for s in sugs]
                        self._cycle_state = {
                            "start_offset": s_off,
                            "end_offset": e_off,
                            "current_text": best,
                            "candidates": all_cands,
                            "index": 0,
                        }
                    if self.on_status_feedback:
                        try:
                            self.on_status_feedback(f"✨ Corrigido: {target_err.word} → {best}")
                        except Exception:
                            pass
                    return (target_err.word, best)

        # 5. Caso o cursor esteja após espaço e haja frase anterior completável (sem erros pendentes)
        if phrase_match is not None:
            p_start, p_end, p_cands = phrase_match
            applied = p_cands[0]
            orig = full_text[p_start:p_end]
            self._replace_span_preserving_tags(p_start, p_end, applied, move_cursor_to_end=True)
            if self.on_status_feedback:
                try:
                    self.on_status_feedback(f"✨ Frase completada: {applied}")
                except Exception:
                    pass
            return (orig, applied)

        return None
