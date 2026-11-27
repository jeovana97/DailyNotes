import bisect
import re
import unicodedata
import tkinter as tk
from typing import Optional, Tuple, List, Callable, Dict
import customtkinter as ctk

from utils.editor_history import (
    attach_editor_history,
    get_editor_history,
    commit_history_before_action,
    record_history_after_action,
    reset_editor_history,
)


# Paleta de cores para Syntax Highlighting (Modo Claro, Modo Escuro)
SYNTAX_COLORS = {
    # XML
    "syntax_xml_bracket": ("#0369A1", "#38BDF8"),     # Azul ciano para < > </ />
    "syntax_xml_tag": ("#1D4ED8", "#60A5FA"),         # Azul forte para nome da tag
    "syntax_xml_attr_name": ("#7C3AED", "#C084FC"),   # Roxo/Lilás para nome do atributo
    "syntax_xml_attr_val": ("#15803D", "#4ADE80"),    # Verde para valor do atributo "..."
    "syntax_xml_comment": ("#64748B", "#94A3B8"),     # Cinza para <!-- comentários -->
    "syntax_xml_cdata": ("#B45309", "#FBBF24"),       # Âmbar para CDATA
    # SQL
    "syntax_sql_keyword": ("#BE185D", "#F472B6"),     # Rosa/Magenta vibrante para palavras-chave SQL
    "syntax_sql_function": ("#0284C7", "#38BDF8"),    # Azul Ciano para funções SQL
    "syntax_sql_string": ("#15803D", "#4ADE80"),      # Verde para strings '...'
    "syntax_sql_number": ("#C2410C", "#FB923C"),      # Laranja para números
    "syntax_sql_operator": ("#6D28D9", "#A78BFA"),    # Violeta para operadores
    "syntax_sql_comment": ("#64748B", "#94A3B8"),     # Cinza para comentários -- e /* */
}

ALL_SYNTAX_TAGS = tuple(SYNTAX_COLORS.keys())

SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "EXISTS", "BETWEEN",
    "LIKE", "ILIKE", "IS", "NULL", "TRUE", "FALSE", "AS", "ON", "USING",
    "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS", "NATURAL",
    "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE", "MERGE", "MATCHED",
    "CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME", "REPLACE",
    "TABLE", "VIEW", "MATERIALIZED", "INDEX", "UNIQUE", "SEQUENCE", "SYNONYM",
    "PROCEDURE", "FUNCTION", "PACKAGE", "BODY", "TRIGGER", "TYPE", "DATABASE", "SCHEMA",
    "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "CONSTRAINT", "CHECK", "DEFAULT",
    "GROUP", "ORDER", "BY", "HAVING", "ASC", "DESC", "NULLS", "FIRST", "LAST",
    "UNION", "ALL", "INTERSECT", "MINUS", "EXCEPT", "DISTINCT",
    "LIMIT", "OFFSET", "FETCH", "NEXT", "ROWS", "ONLY", "TOP", "ROWNUM", "ROWID",
    "CASE", "WHEN", "THEN", "ELSE", "END", "IF", "ELSIF", "LOOP", "WHILE", "FOR",
    "BEGIN", "DECLARE", "EXCEPTION", "RAISE", "RETURN", "EXIT", "CONTINUE", "GOTO",
    "CURSOR", "OPEN", "CLOSE", "BULK", "COLLECT", "FORALL", "record", "ROWTYPE", "TYPE",
    "COMMIT", "ROLLBACK", "SAVEPOINT", "TRANSACTION", "WORK", "GRANT", "REVOKE",
    "NUMBER", "VARCHAR2", "NVARCHAR2", "VARCHAR", "CHAR", "NCHAR", "CLOB", "NCLOB",
    "BLOB", "DATE", "TIMESTAMP", "INTERVAL", "INTEGER", "INT", "SMALLINT", "BIGINT",
    "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL", "BOOLEAN", "RAW", "LONG", "XMLTYPE",
    "DUAL", "SYSDATE", "SYSTIMESTAMP", "CURRENT_DATE", "CURRENT_TIMESTAMP", "USER",
    "PRAGMA", "AUTONOMOUS_TRANSACTION", "EXCEPTION_INIT", "NOCOPY", "DETERMINISTIC",
    "WITH", "RECURSIVE", "OVER", "PARTITION", "WINDOW", "ROWS", "RANGE", "UNBOUNDED",
    "PRECEDING", "FOLLOWING", "CURRENT", "ROW", "RETURNING", "NOCYCLE", "START", "CONNECT", "PRIOR",
}

SQL_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "STDDEV", "VARIANCE",
    "NVL", "NVL2", "COALESCE", "DECODE", "NULLIF", "GREATEST", "LEAST",
    "TO_CHAR", "TO_DATE", "TO_NUMBER", "TO_TIMESTAMP", "TO_CLOB", "CAST", "CONVERT",
    "SUBSTR", "SUBSTRING", "INSTR", "LENGTH", "CHAR_LENGTH", "REPLACE", "TRANSLATE",
    "TRIM", "LTRIM", "RTRIM", "LPAD", "RPAD", "UPPER", "LOWER", "INITCAP", "CONCAT",
    "ROUND", "TRUNC", "MOD", "ABS", "CEIL", "CEILING", "FLOOR", "SIGN", "POWER", "SQRT",
    "ADD_MONTHS", "MONTHS_BETWEEN", "LAST_DAY", "NEXT_DAY", "EXTRACT", "SYSDATE",
    "LISTAGG", "WM_CONCAT", "STRING_AGG", "GROUP_CONCAT",
    "ROW_NUMBER", "RANK", "DENSE_RANK", "NTILE", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE",
    "REGEXP_LIKE", "REGEXP_REPLACE", "REGEXP_SUBSTR", "REGEXP_INSTR", "REGEXP_COUNT",
    "XMLELEMENT", "XMLAGG", "XMLFOREST", "XMLATTRIBUTES", "EXTRACTVALUE", "XMLTABLE",
    "DBMS_OUTPUT", "PUT_LINE", "RAISE_APPLICATION_ERROR", "SQLCODE", "SQLERRM",
}

# Expressões compiladas para performance (limites explícitos evitam backtracking em textos longos)
_RE_XML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_RE_XML_CDATA = re.compile(r"<!\[CDATA\[[\s\S]*?\]\]>")
_RE_XML_TAG = re.compile(r"(<\?xml[\s\S]{0,400}?\?>|</?[a-zA-Z_][\w:.\-]*(?:\s+[^<>]{0,2000}?)?/?>)")
_RE_XML_TAG_PARTS = re.compile(r"^(<\?|\?|</|<)([a-zA-Z_][\w:.\-]*)(.*?)(\?>|/>|>)$", re.DOTALL)
_RE_XML_ATTR = re.compile(r'([a-zA-Z_][\w:.\-]*)(\s*=\s*)("[^"]*"|\'[^\']*\')')

_RE_SQL_COMMENT = re.compile(r"(--[^\n]*|/\*[\s\S]*?\*/)")
_RE_SQL_STRING = re.compile(r"('(?:''|[^'])*')")
_RE_SQL_NUMBER = re.compile(r"\b(\d+(?:\.\d+)?)\b")
_RE_SQL_WORD = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_$#]*)\b")
_RE_SQL_OPERATOR = re.compile(r"(:=|<>|!=|<=|>=|\|\|=|\|\||=)")

# Detectores rápidos e sem backtracking catastrófico para realce automático ao abrir notas
_RE_HAS_XML = re.compile(r"</?[a-zA-Z_][\w:.\-]*(?:\s+[^<>]{0,500}?)?>")
_RE_HAS_SQL = re.compile(
    r"\b(SELECT\b[\s\S]{1,400}?\bFROM\b|INSERT\s+INTO\b|UPDATE\s+\w+[\s\S]{1,250}?\bSET\b|"
    r"DELETE\s+FROM\b|CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|PROCEDURE|FUNCTION|PACKAGE|TRIGGER|INDEX|SEQUENCE)\b|"
    r"ALTER\s+(?:TABLE|VIEW|PROCEDURE|FUNCTION|PACKAGE|TRIGGER|SESSION)\b|"
    r"BEGIN\b[\s\S]{1,1000}?\bEND\s*;)",
    re.IGNORECASE,
)


class OffsetMapper:
    """
    Converte offsets de caractere (int) em índices Tkinter 'linha.coluna' em O(log L)
    em Python puro, eliminando o custo O(N) de `f"1.0 + {offset} chars"` no Tcl/Tk.
    """

    __slots__ = ("_line_starts", "_base_line", "_base_col")

    def __init__(self, text: str, base_line: int = 1, base_col: int = 0):
        self._base_line = base_line
        self._base_col = base_col
        starts = [0]
        pos = text.find("\n")
        while pos != -1:
            starts.append(pos + 1)
            pos = text.find("\n", pos + 1)
        self._line_starts = starts

    @classmethod
    def from_tk_index(cls, text_widget: tk.Text, start_idx: str, text: str) -> "OffsetMapper":
        resolved = text_widget.index(start_idx)
        dot = resolved.find(".")
        if dot != -1:
            base_line = int(resolved[:dot])
            base_col = int(resolved[dot + 1:])
        else:
            base_line, base_col = 1, 0
        return cls(text, base_line=base_line, base_col=base_col)

    def to_tk(self, offset: int) -> str:
        line_idx = bisect.bisect_right(self._line_starts, offset) - 1
        if line_idx < 0:
            line_idx = 0
        col = offset - self._line_starts[line_idx]
        if line_idx == 0:
            col += self._base_col
        return f"{self._base_line + line_idx}.{col}"


class _IntervalIndex:
    """Índice ordenado de intervalos [start, end) para consulta de pertinência em O(log K)."""

    __slots__ = ("_starts", "_ends")

    def __init__(self, spans: List[Tuple[int, int]]):
        if not spans:
            self._starts: List[int] = []
            self._ends: List[int] = []
            return
        ordered = sorted(spans)
        merged_s: List[int] = [ordered[0][0]]
        merged_e: List[int] = [ordered[0][1]]
        for s, e in ordered[1:]:
            if s <= merged_e[-1]:
                if e > merged_e[-1]:
                    merged_e[-1] = e
            else:
                merged_s.append(s)
                merged_e.append(e)
        self._starts = merged_s
        self._ends = merged_e

    def contains(self, pos: int) -> bool:
        if not self._starts:
            return False
        idx = bisect.bisect_right(self._starts, pos) - 1
        return idx >= 0 and pos < self._ends[idx]


def _apply_tag_batches(text_widget: tk.Text, batches: Dict[str, List[str]]) -> None:
    """Aplica todas as tags coletadas usando chamadas em lote `tag_add(tag, s1, e1, s2, e2, ...)`."""
    CHUNK = 2000  # 1000 pares por chamada Tcl segura contra limite de argumentos
    for tag_name, flat_indices in batches.items():
        total = len(flat_indices)
        if total == 0:
            continue
        if total <= CHUNK:
            text_widget.tag_add(tag_name, *flat_indices)
        else:
            for i in range(0, total, CHUNK):
                text_widget.tag_add(tag_name, *flat_indices[i : i + CHUNK])


def configure_syntax_tags(text_widget: tk.Text, force: bool = False) -> None:
    """
    Configura as tags de cores de sintaxe (XML e SQL) de acordo com o tema atual (Claro/Escuro).
    Mantém cache do modo aplicado no widget para evitar reconfigurações redundantes.
    """
    try:
        mode = ctk.get_appearance_mode()
        if not force and getattr(text_widget, "_syntax_tags_mode", None) == mode:
            return

        is_dark = (mode == "Dark")
        idx = 1 if is_dark else 0

        for tag_name, color_pair in SYNTAX_COLORS.items():
            color = color_pair[idx]
            if tag_name in ("syntax_xml_tag", "syntax_sql_keyword", "syntax_sql_function"):
                text_widget.tag_configure(tag_name, foreground=color, font=("Segoe UI", 11, "bold"))
            elif tag_name in ("syntax_xml_comment", "syntax_sql_comment"):
                text_widget.tag_configure(tag_name, foreground=color, font=("Segoe UI", 11, "italic"))
            else:
                text_widget.tag_configure(tag_name, foreground=color)

        # Garante que a seleção de texto ('sel') fique sempre visível acima das cores de sintaxe
        text_widget.tag_raise("sel")
        text_widget._syntax_tags_mode = mode
    except Exception:
        pass


def clear_syntax_tags(text_widget: tk.Text, start_idx: str = "1.0", end_idx: str = "end") -> None:
    """Remove apenas as tags de sintaxe que efetivamente existem no widget no intervalo especificado."""
    try:
        existing = set(text_widget.tag_names())
        for tag_name in ALL_SYNTAX_TAGS:
            if tag_name in existing:
                text_widget.tag_remove(tag_name, start_idx, end_idx)
    except Exception:
        pass


def convert_selection_case(
    ctk_textbox: ctk.CTkTextbox,
    uppercase: bool = True,
    fallback_entry: Optional[ctk.CTkEntry] = None,
) -> Tuple[bool, str]:
    """
    Converte o texto selecionado no editor (ou no campo de título, se selecionado lá)
    para MAIÚSCULAS (uppercase=True) ou minúsculas (uppercase=False).
    Mantém a seleção ativa e preserva tags por intervalos (sem loop caractere-a-caractere).
    """
    text_widget = ctk_textbox._textbox

    # 1. Verifica se há seleção na caixa de texto principal
    sel_ranges = text_widget.tag_ranges("sel")
    if sel_ranges:
        start_idx = text_widget.index("sel.first")
        end_idx = text_widget.index("sel.last")
        selected_text = text_widget.get(start_idx, end_idx)
        if not selected_text:
            return False, "Selecione um trecho de texto para converter."

        converted = selected_text.upper() if uppercase else selected_text.lower()
        if converted != selected_text:
            commit_history_before_action(ctk_textbox)

            # Preserva intervalos de tags existentes dentro da seleção em O(K) via tag_ranges
            preserved_batches: Dict[str, List[str]] = {}
            s_tuple = tuple(int(p) for p in start_idx.split("."))
            e_tuple = tuple(int(p) for p in end_idx.split("."))
            for tag in text_widget.tag_names():
                if tag in ("sel", "spelling_error"):
                    continue
                ranges = text_widget.tag_ranges(tag)
                if not ranges:
                    continue
                for i in range(0, len(ranges), 2):
                    rs_str, re_str = str(ranges[i]), str(ranges[i + 1])
                    rs_t = tuple(int(p) for p in rs_str.split("."))
                    re_t = tuple(int(p) for p in re_str.split("."))
                    if re_t <= s_tuple:
                        continue
                    if rs_t >= e_tuple:
                        break
                    cs = rs_str if rs_t > s_tuple else start_idx
                    ce = re_str if re_t < e_tuple else end_idx
                    preserved_batches.setdefault(tag, []).extend((cs, ce))

            try:
                text_widget.edit_separator()
            except Exception:
                pass
            text_widget.delete(start_idx, end_idx)
            text_widget.insert(start_idx, converted)
            try:
                text_widget.edit_separator()
            except Exception:
                pass

            new_end_idx = text_widget.index(f"{start_idx} + {len(converted)} chars")
            _apply_tag_batches(text_widget, preserved_batches)
            text_widget.tag_add("sel", start_idx, new_end_idx)
            text_widget.mark_set("insert", new_end_idx)
            text_widget.focus_set()
            record_history_after_action(ctk_textbox)
        else:
            text_widget.tag_add("sel", start_idx, end_idx)

        return True, ""

    # 2. Verifica se há seleção no campo de título (ex: Nome da Nota em Notas & Pastas)
    if fallback_entry is not None:
        try:
            inner_entry = fallback_entry._entry
            if inner_entry.selection_present():
                sel_start = inner_entry.index("sel.first")
                sel_end = inner_entry.index("sel.last")
                full_val = inner_entry.get()
                sub = full_val[sel_start:sel_end]
                conv = sub.upper() if uppercase else sub.lower()
                inner_entry.delete(sel_start, sel_end)
                inner_entry.insert(sel_start, conv)
                inner_entry.select_range(sel_start, sel_start + len(conv))
                inner_entry.focus_set()
                return True, ""
        except Exception:
            pass

    target_label = "MAIÚSCULO" if uppercase else "minúsculo"
    return (
        False,
        f"Selecione primeiro no texto o trecho que deseja transformar em {target_label}.",
    )


def format_xml_string(raw_text: str) -> str:
    """
    Indenta e organiza código XML (mesmo que esteja em uma única linha ou seja um fragmento)
    preservando todo o conteúdo e textos ao redor.
    """
    if not raw_text or "<" not in raw_text or ">" not in raw_text:
        return raw_text

    # Quebra entre tags coladas: ><  ->  >\n<
    formatted = re.sub(r">\s*<", ">\n<", raw_text.strip())
    lines = [ln.strip() for ln in formatted.splitlines() if ln.strip()]

    result_lines: List[str] = []
    indent_level = 0
    indent_str = "  "

    for line in lines:
        # Tag de fechamento: </tag>
        if re.match(r"^</[a-zA-Z_][\w:.\-]*\s*>", line):
            indent_level = max(0, indent_level - 1)
            result_lines.append(f"{indent_str * indent_level}{line}")
        # Declaração XML, comentário, CDATA ou tag auto-fechada: <?xml...?>, <!--...-->, <tag/>
        elif (
            line.startswith("<?")
            or line.startswith("<!")
            or line.endswith("/>")
        ):
            result_lines.append(f"{indent_str * indent_level}{line}")
        # Tag que abre e fecha na mesma linha: <tag>valor</tag>
        elif re.match(r"^<[a-zA-Z_][\w:.\-]*(?:\s+[^<>]*?)?>.*</[a-zA-Z_][\w:.\-]*\s*>$", line):
            result_lines.append(f"{indent_str * indent_level}{line}")
        # Tag de abertura: <tag ...>
        elif re.match(r"^<[a-zA-Z_][\w:.\-]*(?:\s+[^<>]*?)?>$", line):
            result_lines.append(f"{indent_str * indent_level}{line}")
            indent_level += 1
        else:
            result_lines.append(f"{indent_str * indent_level}{line}")

    return "\n".join(result_lines)


def format_sql_string(raw_text: str) -> str:
    """
    Formata código SQL/PLSQL:
    - Converte palavras-chave e funções SQL para MAIÚSCULAS (preservando strings e comentários intactos).
    - Se a query estiver em uma única linha longa, organiza as cláusulas principais em linhas.
    """
    if not raw_text or not raw_text.strip():
        return raw_text

    # Protege comentários e strings durante a conversão de keywords com busca O(log P)
    protected_spans: List[Tuple[int, int]] = []
    for m in _RE_SQL_COMMENT.finditer(raw_text):
        protected_spans.append((m.start(), m.end()))
    for m in _RE_SQL_STRING.finditer(raw_text):
        protected_spans.append((m.start(), m.end()))
    protected_index = _IntervalIndex(protected_spans)

    def _replace_word(match: re.Match) -> str:
        if protected_index.contains(match.start()):
            return match.group(0)
        word = match.group(1)
        upper_w = word.upper()
        if upper_w in SQL_KEYWORDS or upper_w in SQL_FUNCTIONS:
            return upper_w
        return word

    result = _RE_SQL_WORD.sub(_replace_word, raw_text)

    # Se for uma consulta em linha única com mais de 70 caracteres, quebra nas cláusulas principais
    non_empty_lines = [ln for ln in result.strip().splitlines() if ln.strip()]
    if len(non_empty_lines) == 1 and len(non_empty_lines[0]) > 70:
        clause_pattern = re.compile(
            r"\s+\b(FROM|WHERE|INNER\s+JOIN|LEFT\s+(?:OUTER\s+)?JOIN|RIGHT\s+(?:OUTER\s+)?JOIN|"
            r"FULL\s+(?:OUTER\s+)?JOIN|GROUP\s+BY|ORDER\s+BY|HAVING|UNION(?:\s+ALL)?|VALUES|SET)\b",
            re.IGNORECASE,
        )
        result = clause_pattern.sub(lambda m: f"\n{m.group(1).upper()}", result)

    return result


def _collect_xml_batches(
    segment: str,
    mapper: OffsetMapper,
    batches: Dict[str, List[str]],
) -> List[Tuple[int, int]]:
    """
    Coleta todos os tokens XML de `segment` em `batches` usando `mapper` O(log L)
    e retorna os intervalos (start, end) cobertos por tags/comentários/CDATA XML.
    """
    xml_covered: List[Tuple[int, int]] = []
    to_tk = mapper.to_tk

    b_bracket = batches.setdefault("syntax_xml_bracket", [])
    b_tag = batches.setdefault("syntax_xml_tag", [])
    b_attr_name = batches.setdefault("syntax_xml_attr_name", [])
    b_attr_val = batches.setdefault("syntax_xml_attr_val", [])
    b_cdata = batches.setdefault("syntax_xml_cdata", [])
    b_comment = batches.setdefault("syntax_xml_comment", [])

    # 1. Tags XML (<tag attr="val">, </tag>, <?xml ...?>)
    for match in _RE_XML_TAG.finditer(segment):
        tag_start = match.start()
        tag_end = match.end()
        xml_covered.append((tag_start, tag_end))
        tag_text = match.group(0)

        parts = _RE_XML_TAG_PARTS.match(tag_text)
        if not parts:
            b_tag.extend((to_tk(tag_start), to_tk(tag_end)))
            continue

        open_br, tag_name, attrs_part, close_br = parts.groups()

        p0 = tag_start
        p1 = p0 + len(open_br)
        b_bracket.extend((to_tk(p0), to_tk(p1)))

        p2 = p1 + len(tag_name)
        b_tag.extend((to_tk(p1), to_tk(p2)))

        if attrs_part:
            attr_offset = p2
            for attr_m in _RE_XML_ATTR.finditer(attrs_part):
                a_name_s = attr_offset + attr_m.start(1)
                a_name_e = attr_offset + attr_m.end(1)
                b_attr_name.extend((to_tk(a_name_s), to_tk(a_name_e)))

                a_val_s = attr_offset + attr_m.start(3)
                a_val_e = attr_offset + attr_m.end(3)
                b_attr_val.extend((to_tk(a_val_s), to_tk(a_val_e)))

        p3 = tag_end - len(close_br)
        b_bracket.extend((to_tk(p3), to_tk(tag_end)))

    # 2. CDATA
    for match in _RE_XML_CDATA.finditer(segment):
        s, e = match.start(), match.end()
        xml_covered.append((s, e))
        b_cdata.extend((to_tk(s), to_tk(e)))

    # 3. Comentários XML (<!-- ... -->)
    for match in _RE_XML_COMMENT.finditer(segment):
        s, e = match.start(), match.end()
        xml_covered.append((s, e))
        b_comment.extend((to_tk(s), to_tk(e)))

    return xml_covered


def _collect_sql_batches(
    segment: str,
    mapper: OffsetMapper,
    batches: Dict[str, List[str]],
    exclude_index: Optional[_IntervalIndex] = None,
) -> None:
    """Coleta todos os tokens SQL de `segment` em `batches` com busca O(log P) e mapeamento O(log L)."""
    to_tk = mapper.to_tk

    comment_spans: List[Tuple[int, int]] = []
    protected_spans: List[Tuple[int, int]] = []
    b_comment = batches.setdefault("syntax_sql_comment", [])
    b_string = batches.setdefault("syntax_sql_string", [])
    b_operator = batches.setdefault("syntax_sql_operator", [])
    b_number = batches.setdefault("syntax_sql_number", [])
    b_function = batches.setdefault("syntax_sql_function", [])
    b_keyword = batches.setdefault("syntax_sql_keyword", [])

    for m in _RE_SQL_COMMENT.finditer(segment):
        s, e = m.start(), m.end()
        if exclude_index is not None and exclude_index.contains(s):
            continue
        comment_spans.append((s, e))
        protected_spans.append((s, e))
        b_comment.extend((to_tk(s), to_tk(e)))

    comment_index = _IntervalIndex(comment_spans)

    for m in _RE_SQL_STRING.finditer(segment):
        s, e = m.start(), m.end()
        if comment_index.contains(s):
            continue
        if exclude_index is not None and exclude_index.contains(s):
            continue
        protected_spans.append((s, e))
        b_string.extend((to_tk(s), to_tk(e)))

    protected_index = _IntervalIndex(protected_spans)

    def _skip(pos: int) -> bool:
        if protected_index.contains(pos):
            return True
        if exclude_index is not None and exclude_index.contains(pos):
            return True
        return False

    for m in _RE_SQL_OPERATOR.finditer(segment):
        if not _skip(m.start()):
            b_operator.extend((to_tk(m.start()), to_tk(m.end())))

    for m in _RE_SQL_NUMBER.finditer(segment):
        if not _skip(m.start()):
            b_number.extend((to_tk(m.start()), to_tk(m.end())))

    for m in _RE_SQL_WORD.finditer(segment):
        if _skip(m.start()):
            continue
        upper_w = m.group(1).upper()
        if upper_w in SQL_FUNCTIONS:
            b_function.extend((to_tk(m.start()), to_tk(m.end())))
        elif upper_w in SQL_KEYWORDS:
            b_keyword.extend((to_tk(m.start()), to_tk(m.end())))


def highlight_xml_range(text_widget: tk.Text, start_idx: str = "1.0", end_idx: str = "end") -> None:
    """Aplica coloração de sintaxe XML no intervalo indicado usando inserção em lote O(N log L)."""
    configure_syntax_tags(text_widget)
    clear_syntax_tags(text_widget, start_idx, end_idx)

    segment = text_widget.get(start_idx, end_idx)
    if not segment:
        return

    mapper = OffsetMapper.from_tk_index(text_widget, start_idx, segment)
    batches: Dict[str, List[str]] = {}
    _collect_xml_batches(segment, mapper, batches)
    _apply_tag_batches(text_widget, batches)


def highlight_sql_range(text_widget: tk.Text, start_idx: str = "1.0", end_idx: str = "end") -> None:
    """Aplica coloração de sintaxe SQL/PLSQL no intervalo indicado usando inserção em lote O(N log L)."""
    configure_syntax_tags(text_widget)
    clear_syntax_tags(text_widget, start_idx, end_idx)

    segment = text_widget.get(start_idx, end_idx)
    if not segment:
        return

    mapper = OffsetMapper.from_tk_index(text_widget, start_idx, segment)
    batches: Dict[str, List[str]] = {}
    _collect_sql_batches(segment, mapper, batches)
    _apply_tag_batches(text_widget, batches)


def format_and_highlight_xml(ctk_textbox: ctk.CTkTextbox, indent_xml: bool = True) -> bool:
    """
    Formata (indenta) e aplica coloração XML ao trecho selecionado
    ou a todo o texto caso não haja seleção.
    Registra a ação no histórico unificado para permitir Ctrl+Z (Desfazer).
    """
    text_widget = ctk_textbox._textbox
    sel_ranges = text_widget.tag_ranges("sel")

    if sel_ranges:
        start_idx = text_widget.index("sel.first")
        end_idx = text_widget.index("sel.last")
        raw = text_widget.get(start_idx, end_idx)
        if not raw.strip():
            return False
        if indent_xml:
            commit_history_before_action(ctk_textbox)
        formatted = format_xml_string(raw) if indent_xml else raw
        if formatted != raw:
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            text_widget.delete(start_idx, end_idx)
            text_widget.insert(start_idx, formatted)
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            end_idx = text_widget.index(f"{start_idx} + {len(formatted)} chars")
            text_widget.tag_add("sel", start_idx, end_idx)
        highlight_xml_range(text_widget, start_idx, end_idx)
        if indent_xml:
            record_history_after_action(ctk_textbox)
            try:
                text_widget.focus_set()
            except Exception:
                pass
        return True
    else:
        raw = text_widget.get("1.0", "end-1c")
        if not raw.strip():
            return False
        if indent_xml:
            commit_history_before_action(ctk_textbox)
        if indent_xml and _RE_HAS_XML.search(raw):
            formatted = format_xml_string(raw)
            if formatted != raw:
                try:
                    text_widget.edit_separator()
                except Exception:
                    pass
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", formatted)
                try:
                    text_widget.edit_separator()
                except Exception:
                    pass
        highlight_xml_range(text_widget, "1.0", "end-1c")
        if indent_xml:
            record_history_after_action(ctk_textbox)
            try:
                text_widget.focus_set()
            except Exception:
                pass
        return True


def format_and_highlight_sql(ctk_textbox: ctk.CTkTextbox, format_keywords: bool = True) -> bool:
    """
    Formata (padroniza palavras-chave em maiúsculo e estrutura cláusulas) e aplica
    coloração SQL ao trecho selecionado ou a todo o texto caso não haja seleção.
    Registra a ação no histórico unificado para permitir Ctrl+Z (Desfazer).
    """
    text_widget = ctk_textbox._textbox
    sel_ranges = text_widget.tag_ranges("sel")

    if sel_ranges:
        start_idx = text_widget.index("sel.first")
        end_idx = text_widget.index("sel.last")
        raw = text_widget.get(start_idx, end_idx)
        if not raw.strip():
            return False
        if format_keywords:
            commit_history_before_action(ctk_textbox)
        formatted = format_sql_string(raw) if format_keywords else raw
        if formatted != raw:
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            text_widget.delete(start_idx, end_idx)
            text_widget.insert(start_idx, formatted)
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            end_idx = text_widget.index(f"{start_idx} + {len(formatted)} chars")
            text_widget.tag_add("sel", start_idx, end_idx)
        highlight_sql_range(text_widget, start_idx, end_idx)
        if format_keywords:
            record_history_after_action(ctk_textbox)
            try:
                text_widget.focus_set()
            except Exception:
                pass
        return True
    else:
        raw = text_widget.get("1.0", "end-1c")
        if not raw.strip():
            return False
        if format_keywords:
            commit_history_before_action(ctk_textbox)
        formatted = format_sql_string(raw) if format_keywords else raw
        if formatted != raw:
            try:
                text_widget.edit_separator()
            except Exception:
                pass
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", formatted)
            try:
                text_widget.edit_separator()
            except Exception:
                pass
        highlight_sql_range(text_widget, "1.0", "end-1c")
        if format_keywords:
            record_history_after_action(ctk_textbox)
            try:
                text_widget.focus_set()
            except Exception:
                pass
        return True


def perform_undo(
    ctk_textbox: ctk.CTkTextbox,
    on_change_callback: Optional[Callable[[], None]] = None,
) -> bool:
    """
    Executa o Desfazer (Ctrl+Z) no editor de texto usando o histórico unificado
    (desfazendo texto, fonte, tamanho, negrito, itálico, sublinhado, riscado, XML, SQL, etc.).
    """
    mgr = get_editor_history(ctk_textbox)
    if mgr is not None:
        return mgr.undo(override_callback=on_change_callback)

    text_widget = ctk_textbox._textbox
    try:
        if str(text_widget.cget("state")) == "disabled":
            return False
        text_widget.edit_undo()
    except tk.TclError:
        return False
    except Exception:
        return False

    auto_highlight_content(ctk_textbox)
    try:
        text_widget.see("insert")
        text_widget.focus_set()
    except Exception:
        pass

    if on_change_callback:
        on_change_callback()
    return True


def perform_redo(
    ctk_textbox: ctk.CTkTextbox,
    on_change_callback: Optional[Callable[[], None]] = None,
) -> bool:
    """
    Executa o Refazer (Ctrl+Y) no editor de texto usando o histórico unificado.
    """
    mgr = get_editor_history(ctk_textbox)
    if mgr is not None:
        return mgr.redo(override_callback=on_change_callback)

    text_widget = ctk_textbox._textbox
    try:
        if str(text_widget.cget("state")) == "disabled":
            return False
        text_widget.edit_redo()
    except tk.TclError:
        return False
    except Exception:
        return False

    auto_highlight_content(ctk_textbox)
    try:
        text_widget.see("insert")
        text_widget.focus_set()
    except Exception:
        pass

    if on_change_callback:
        on_change_callback()
    return True


def reset_undo_stack(ctk_textbox: ctk.CTkTextbox) -> None:
    """
    Limpa o histórico de Undo/Redo após carregar uma nota do banco,
    definindo o estado carregado (texto + formatação + sintaxe) como ponto inicial.
    """
    reset_editor_history(ctk_textbox)
    try:
        ctk_textbox._textbox.edit_reset()
    except Exception:
        pass


def enable_undo_redo(
    ctk_textbox: ctk.CTkTextbox,
    on_change_callback: Optional[Callable[[], None]] = None,
) -> None:
    """
    Habilita e configura a pilha unificada de Desfazer (Ctrl+Z) e Refazer (Ctrl+Y)
    no CTkTextbox, cobrindo digitação, colagem, recorte e todos os botões de ação.
    """
    text_widget = ctk_textbox._textbox
    try:
        text_widget.configure(undo=True, autoseparators=True, maxundo=-1)
    except Exception:
        pass

    attach_editor_history(ctk_textbox, on_change_callback=on_change_callback)

    def _on_undo_event(_event=None):
        perform_undo(ctk_textbox, on_change_callback)
        return "break"

    def _on_redo_event(_event=None):
        perform_redo(ctk_textbox, on_change_callback)
        return "break"

    text_widget.bind("<<Undo>>", _on_undo_event)
    text_widget.bind("<Control-z>", _on_undo_event)
    text_widget.bind("<Control-Z>", _on_undo_event)
    text_widget.bind("<<Redo>>", _on_redo_event)
    text_widget.bind("<Control-y>", _on_redo_event)
    text_widget.bind("<Control-Y>", _on_redo_event)
    text_widget.bind("<Control-Shift-z>", _on_redo_event)
    text_widget.bind("<Control-Shift-Z>", _on_redo_event)


def auto_highlight_range(
    ctk_textbox: ctk.CTkTextbox,
    start_idx: str = "1.0",
    end_idx: str = "end-1c",
    content: Optional[str] = None,
) -> Optional[str]:
    """
    Detecta automaticamente estruturas XML e/ou SQL em um intervalo específico
    (ex.: apenas o trecho recém-colado) e aplica coloração em lote em uma única passagem.
    Retorna 'XML', 'SQL', 'XML+SQL' ou None.
    """
    try:
        text_widget = ctk_textbox._textbox
        segment = content if content is not None else text_widget.get(start_idx, end_idx)
        if not segment or not segment.strip():
            clear_syntax_tags(text_widget, start_idx, end_idx)
            return None

        has_xml = ("<" in segment and ">" in segment and bool(_RE_HAS_XML.search(segment)))
        has_sql = bool(_RE_HAS_SQL.search(segment))

        if not has_xml and not has_sql:
            return None

        configure_syntax_tags(text_widget)
        clear_syntax_tags(text_widget, start_idx, end_idx)

        mapper = OffsetMapper.from_tk_index(text_widget, start_idx, segment)
        batches: Dict[str, List[str]] = {}

        if has_xml and not has_sql:
            _collect_xml_batches(segment, mapper, batches)
            _apply_tag_batches(text_widget, batches)
            return "XML"
        elif has_sql and not has_xml:
            _collect_sql_batches(segment, mapper, batches)
            _apply_tag_batches(text_widget, batches)
            return "SQL"
        else:
            # Passagem única combinada: coleta XML primeiro e exclui seus intervalos do SQL
            xml_spans = _collect_xml_batches(segment, mapper, batches)
            xml_index = _IntervalIndex(xml_spans)
            _collect_sql_batches(segment, mapper, batches, exclude_index=xml_index)
            _apply_tag_batches(text_widget, batches)
            return "XML+SQL"
    except Exception:
        return None


def auto_highlight_content(
    ctk_textbox: ctk.CTkTextbox,
    content: Optional[str] = None,
) -> Optional[str]:
    """
    Detecta automaticamente se o texto possui estruturas XML e/ou SQL e aplica a
    coloração de sintaxe correspondente em lote (alta performance).
    Retorna 'XML', 'SQL', 'XML+SQL' ou None.
    """
    return auto_highlight_range(ctk_textbox, "1.0", "end-1c", content=content)


def _normalize_with_map(text: str) -> Tuple[str, List[int]]:
    """Normaliza o texto (sem acentos, minúsculo) preservando o mapeamento para o índice original."""
    norm_chars: List[str] = []
    pos_map: List[int] = []
    for orig_idx, ch in enumerate(text):
        decomposed = unicodedata.normalize("NFD", ch.lower())
        for d in decomposed:
            if unicodedata.category(d) != "Mn":
                norm_chars.append(d)
                pos_map.append(orig_idx)
    return "".join(norm_chars), pos_map


def find_query_spans(content: str, query: str) -> List[Tuple[int, int]]:
    """
    Localiza todas as ocorrências das palavras da pesquisa em `content`
    (insensível a maiúsculas e acentuação), retornando lista ordenada de (start, end).
    """
    if not content or not query or not query.strip():
        return []

    terms = [t.strip() for t in query.split() if len(t.strip()) >= 2]
    if not terms and query.strip():
        terms = [query.strip()]

    norm_content, pos_map = _normalize_with_map(content)
    if not norm_content:
        return []

    raw_spans: List[Tuple[int, int]] = []
    for term in terms:
        norm_term, _ = _normalize_with_map(term)
        if not norm_term:
            continue
        start_from = 0
        tlen = len(norm_term)
        while True:
            idx = norm_content.find(norm_term, start_from)
            if idx == -1:
                break
            orig_start = pos_map[idx]
            orig_end = pos_map[idx + tlen - 1] + 1
            raw_spans.append((orig_start, orig_end))
            start_from = idx + tlen

    if not raw_spans:
        return []

    raw_spans.sort(key=lambda s: (s[0], s[1]))
    # Mescla/remove sobreposições mantendo ordem de leitura no texto
    merged: List[Tuple[int, int]] = [raw_spans[0]]
    for s, e in raw_spans[1:]:
        prev_s, prev_e = merged[-1]
        if s < prev_e:
            if e > prev_e:
                merged[-1] = (prev_s, e)
        else:
            merged.append((s, e))
    return merged


def clear_search_highlights(ctk_textbox: ctk.CTkTextbox) -> None:
    """Remove todos os destaques de busca do editor."""
    try:
        tb = ctk_textbox._textbox
        tb.tag_remove("search_highlight", "1.0", "end")
        tb.tag_remove("search_highlight_current", "1.0", "end")
    except Exception:
        pass


def highlight_search_matches(ctk_textbox: ctk.CTkTextbox, query: str) -> List[Tuple[str, str]]:
    """
    Destaca todas as ocorrências da pesquisa no editor em lote e retorna a lista ordenada
    de pares de índices Tkinter (start_idx, end_idx) para navegação com F3.
    """
    matches: List[Tuple[str, str]] = []
    try:
        tb = ctk_textbox._textbox
        tb.tag_configure("search_highlight", background="#F59E0B", foreground="#0F172A")
        tb.tag_configure("search_highlight_current", background="#EA580C", foreground="#FFFFFF")
        tb.tag_remove("search_highlight", "1.0", "end")
        tb.tag_remove("search_highlight_current", "1.0", "end")

        content = tb.get("1.0", "end-1c")
        spans = find_query_spans(content, query)
        if spans:
            mapper = OffsetMapper(content, base_line=1, base_col=0)
            flat: List[str] = []
            for s_off, e_off in spans:
                s_idx = mapper.to_tk(s_off)
                e_idx = mapper.to_tk(e_off)
                flat.append(s_idx)
                flat.append(e_idx)
                matches.append((s_idx, e_idx))
            _apply_tag_batches(tb, {"search_highlight": flat})

        tb.tag_raise("search_highlight")
        tb.tag_raise("search_highlight_current")
    except Exception:
        pass
    return matches


def focus_search_match(
    ctk_textbox: ctk.CTkTextbox,
    matches: List[Tuple[str, str]],
    index: int,
) -> int:
    """
    Destaca a ocorrência `index` como ativa, move o cursor até ela e rola o texto
    para que fique visível. Retorna o índice normalizado.
    """
    if not matches:
        return -1
    idx = index % len(matches)
    try:
        tb = ctk_textbox._textbox
        tb.tag_remove("search_highlight_current", "1.0", "end")
        s_idx, e_idx = matches[idx]
        tb.tag_add("search_highlight_current", s_idx, e_idx)
        tb.tag_raise("search_highlight_current")
        tb.mark_set("insert", s_idx)
        tb.see(s_idx)
        tb.see(e_idx)
    except Exception:
        pass
    return idx
