"""
Leitor universal de documentos para importação no DailyNotes.
Suporta:
- Arquivos de texto puro (.txt, .xml, .bat, .sql) com detecção automática de codificação
- Documentos Microsoft Word moderno (.docx) via stdlib (zipfile + XML), preservando texto,
  tabelas e formatação rica (Fonte, Tamanho, Negrito, Itálico, Sublinhado e Riscado)
- Documentos Microsoft Word legado (.doc) com suporte completo em múltiplos formatos reais:
  1. .docx renomeado como .doc (assinatura ZIP/OOXML)
  2. RTF salvo como .doc (assinatura '{\\rtf')
  3. HTML/MHTML salvo como .doc
  4. Binário Microsoft Word 97-2003 OLE2/CFBF:
     - Via automação COM do Microsoft Word (se instalado no Windows, preservando tabelas e formatação)
     - Via parser nativo OLE2 + FIB + CLX Piece Table em Python puro (100% offline, sem Word)
"""

import html
from html.parser import HTMLParser
import json
import logging
import os
import re
import struct
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List, Optional, Tuple

from utils.text_utils import detect_encoding

logger = logging.getLogger(__name__)

_OLE2_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_KNOWN_FONTS_MAP: Dict[str, str] = {
    "segoe ui": "Segoe UI",
    "arial": "Arial",
    "calibri": "Calibri",
    "consolas": "Consolas",
    "courier new": "Courier New",
    "georgia": "Georgia",
    "tahoma": "Tahoma",
    "times new roman": "Times New Roman",
    "verdana": "Verdana",
}
_DEFAULT_FONT_FAMILY = "Segoe UI"
_DEFAULT_FONT_SIZE = 15


# =============================================================================
# 1. Parser Nativo de DOCX (OOXML — stdlib zipfile + ElementTree)
# =============================================================================

def _is_xml_bool_on(elem: Optional[ET.Element], false_vals=("0", "false", "none", "off")) -> bool:
    if elem is None:
        return False
    val = elem.attrib.get(f"{_W_NS}val")
    if val is None:
        return True
    return val.strip().lower() not in false_vals


def _extract_run_style(r_elem: ET.Element) -> Dict[str, object]:
    """Extrai estilos suportados (bold, italic, underline, overstrike, family, size) de um <w:r>."""
    rpr = r_elem.find(f"{_W_NS}rPr")
    if rpr is None:
        return {}

    style: Dict[str, object] = {}
    if _is_xml_bool_on(rpr.find(f"{_W_NS}b")):
        style["bold"] = True
    if _is_xml_bool_on(rpr.find(f"{_W_NS}i")):
        style["italic"] = True
    if _is_xml_bool_on(rpr.find(f"{_W_NS}u")):
        style["underline"] = True
    if _is_xml_bool_on(rpr.find(f"{_W_NS}strike")) or _is_xml_bool_on(rpr.find(f"{_W_NS}dstrike")):
        style["overstrike"] = True

    rfonts = rpr.find(f"{_W_NS}rFonts")
    if rfonts is not None:
        raw_fam = (
            rfonts.attrib.get(f"{_W_NS}ascii")
            or rfonts.attrib.get(f"{_W_NS}hAnsi")
            or rfonts.attrib.get(f"{_W_NS}cs")
            or ""
        ).strip()
        matched = _KNOWN_FONTS_MAP.get(raw_fam.lower())
        if matched and matched != _DEFAULT_FONT_FAMILY:
            style["family"] = matched

    sz_elem = rpr.find(f"{_W_NS}sz")
    if sz_elem is not None:
        raw_sz = sz_elem.attrib.get(f"{_W_NS}val", "").strip()
        if raw_sz.isdigit():
            # No OOXML w:sz é em half-points (ex.: 22 = 11pt ≈ 15px padrão do editor)
            pt_size = int(raw_sz) / 2.0
            px_size = max(10, min(32, round(pt_size * (4.0 / 3.0))))
            if abs(px_size - _DEFAULT_FONT_SIZE) >= 2:
                style["size"] = px_size

    return style


def _merge_adjacent_spans(raw_spans: List[Tuple[str, int, int, int]]) -> List[Dict[str, str]]:
    """
    Mescla spans adjacentes da mesma tag na mesma linha e converte para o formato
    JSON do RichTextController ({'tag', 'start': 'L.C', 'end': 'L.C'}).
    """
    if not raw_spans:
        return []
    raw_spans.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    merged: List[Tuple[str, int, int, int]] = [raw_spans[0]]
    for tag, line_no, c0, c1 in raw_spans[1:]:
        p_tag, p_line, p_c0, p_c1 = merged[-1]
        if tag == p_tag and line_no == p_line and c0 <= p_c1:
            merged[-1] = (p_tag, p_line, p_c0, max(p_c1, c1))
        else:
            merged.append((tag, line_no, c0, c1))
    return [
        {"tag": tag, "start": f"{line_no}.{c0}", "end": f"{line_no}.{c1}"}
        for tag, line_no, c0, c1 in merged
        if c1 > c0
    ]


def _extract_docx_body_xml(zf: zipfile.ZipFile) -> bytes:
    """Localiza o XML principal do documento dentro do pacote ZIP (.docx / OOXML)."""
    names = zf.namelist()
    if "word/document.xml" in names:
        return zf.read("word/document.xml")

    # Busca case-insensitive por word/document.xml ou word/document*.xml
    lower_map = {name.lower().lstrip("/"): name for name in names}
    if "word/document.xml" in lower_map:
        return zf.read(lower_map["word/document.xml"])

    for low, orig in lower_map.items():
        if low.startswith("word/document") and low.endswith(".xml"):
            return zf.read(orig)

    # Tenta descobrir via _rels/.rels (officeDocument relationship)
    rels_name = lower_map.get("_rels/.rels")
    if rels_name:
        try:
            rels_root = ET.fromstring(zf.read(rels_name))
            for rel in rels_root:
                rel_type = rel.attrib.get("Type", "").lower()
                if "officedocument" in rel_type:
                    target = rel.attrib.get("Target", "").lstrip("/").lower()
                    if target in lower_map:
                        return zf.read(lower_map[target])
        except Exception:
            pass

    raise ValueError("Arquivo .docx inválido: 'word/document.xml' não encontrado.")


def _parse_wordprocessing_xml(xml_bytes: bytes) -> Tuple[str, str]:
    """
    Faz parse de XML WordprocessingML (tanto word/document.xml de .docx quanto
    Word 2003 XML plano) extraindo parágrafos, tabelas e formatação rica.
    """
    root = ET.fromstring(xml_bytes)

    # Detecta dinamicamente o namespace WordprocessingML (2006 OOXML ou 2003 WordML)
    ns_prefix = _W_NS
    if root.tag.startswith("{"):
        ns_prefix = root.tag.split("}", 1)[0] + "}"

    body = root.find(f"{ns_prefix}body")
    if body is None:
        # Procura body em qualquer profundidade (ex: <w:wordDocument><w:body>)
        for elem in root.iter():
            if elem.tag.endswith("}body") or elem.tag == "body":
                body = elem
                if elem.tag.startswith("{"):
                    ns_prefix = elem.tag.split("}", 1)[0] + "}"
                break
    if body is None:
        return "", ""

    lines: List[str] = []
    raw_spans: List[Tuple[str, int, int, int]] = []

    def _local(tag_name: str) -> str:
        return tag_name.split("}", 1)[1] if "}" in tag_name else tag_name

    def _attr_val(el: ET.Element, attr_local: str) -> Optional[str]:
        val = el.attrib.get(f"{ns_prefix}{attr_local}")
        if val is not None:
            return val
        for k, v in el.attrib.items():
            if _local(k) == attr_local:
                return v
        return None

    def _is_bool_on(el: Optional[ET.Element], false_vals=("0", "false", "none", "off")) -> bool:
        if el is None:
            return False
        val = _attr_val(el, "val")
        if val is None:
            return True
        return val.strip().lower() not in false_vals

    def _extract_style(r_elem: ET.Element) -> Dict[str, object]:
        rpr = None
        for ch in r_elem:
            if _local(ch.tag) == "rPr":
                rpr = ch
                break
        if rpr is None:
            return {}

        style: Dict[str, object] = {}
        for ch in rpr:
            loc = _local(ch.tag)
            if loc == "b" and _is_bool_on(ch):
                style["bold"] = True
            elif loc == "i" and _is_bool_on(ch):
                style["italic"] = True
            elif loc == "u" and _is_bool_on(ch):
                style["underline"] = True
            elif loc in ("strike", "dstrike") and _is_bool_on(ch):
                style["overstrike"] = True
            elif loc == "rFonts":
                raw_fam = (
                    _attr_val(ch, "ascii")
                    or _attr_val(ch, "hAnsi")
                    or _attr_val(ch, "cs")
                    or ""
                ).strip()
                matched = _KNOWN_FONTS_MAP.get(raw_fam.lower())
                if matched and matched != _DEFAULT_FONT_FAMILY:
                    style["family"] = matched
            elif loc == "sz":
                raw_sz = (_attr_val(ch, "val") or "").strip()
                if raw_sz.isdigit():
                    pt_size = int(raw_sz) / 2.0
                    px_size = max(10, min(32, round(pt_size * (4.0 / 3.0))))
                    if abs(px_size - _DEFAULT_FONT_SIZE) >= 2:
                        style["size"] = px_size
        return style

    def _append_paragraph(p_elem: ET.Element, target_buf: Optional[List[str]] = None, collect_spans: bool = True):
        """Processa um <w:p> gravando linhas em `lines` ou em um buffer de célula de tabela."""
        cur_chars: List[str] = []

        def _flush_line():
            line_text = "".join(cur_chars)
            cur_chars.clear()
            if target_buf is not None:
                target_buf.append(line_text)
            else:
                lines.append(line_text)

        def _walk_runs(container: ET.Element):
            for child in container:
                loc = _local(child.tag)
                if loc == "r":
                    style = _extract_style(child) if (collect_spans and target_buf is None) else {}
                    for sub in child:
                        sub_loc = _local(sub.tag)
                        if sub_loc == "t":
                            txt = sub.text or ""
                            if txt:
                                line_no = len(lines) + 1
                                c0 = sum(len(x) for x in cur_chars)
                                cur_chars.append(txt)
                                c1 = c0 + len(txt)
                                if style:
                                    if style.get("bold"):
                                        raw_spans.append(("bold", line_no, c0, c1))
                                    if style.get("italic"):
                                        raw_spans.append(("italic", line_no, c0, c1))
                                    if style.get("underline"):
                                        raw_spans.append(("underline", line_no, c0, c1))
                                    if style.get("overstrike"):
                                        raw_spans.append(("overstrike", line_no, c0, c1))
                                    if "family" in style:
                                        raw_spans.append((f"family:{style['family']}", line_no, c0, c1))
                                    if "size" in style:
                                        raw_spans.append((f"size:{style['size']}", line_no, c0, c1))
                        elif sub_loc == "tab":
                            cur_chars.append("\t")
                        elif sub_loc in ("br", "cr"):
                            _flush_line()
                elif loc in ("hyperlink", "ins", "smartTag", "sdt", "fldSimple"):
                    if loc == "sdt":
                        for sc in child:
                            if _local(sc.tag) == "sdtContent":
                                _walk_runs(sc)
                    else:
                        _walk_runs(child)

        _walk_runs(p_elem)
        _flush_line()

    def _walk_body(container: ET.Element):
        for elem in container:
            loc = _local(elem.tag)
            if loc == "p":
                _append_paragraph(elem)
            elif loc == "tbl":
                for tr in elem:
                    if _local(tr.tag) != "tr":
                        continue
                    cells_text: List[str] = []
                    for tc in tr:
                        if _local(tc.tag) != "tc":
                            continue
                        cell_lines: List[str] = []
                        for p in tc:
                            if _local(p.tag) == "p":
                                _append_paragraph(p, target_buf=cell_lines, collect_spans=False)
                        cell_str = " ".join(ln.strip() for ln in cell_lines if ln.strip())
                        cells_text.append(cell_str)
                    if any(cells_text):
                        lines.append(" | ".join(cells_text))
            elif loc in ("sdt", "sect", "sub-section"):
                if loc == "sdt":
                    for sc in elem:
                        if _local(sc.tag) == "sdtContent":
                            _walk_body(sc)
                else:
                    _walk_body(elem)

    _walk_body(body)

    # Remove linhas vazias excedentes apenas no final do documento (mantém índices 1..N válidos)
    while lines and not lines[-1].strip():
        lines.pop()

    content = "\n".join(lines)
    max_line = len(lines)
    valid_spans = [
        sp for sp in raw_spans
        if 1 <= sp[1] <= max_line and sp[3] <= len(lines[sp[1] - 1])
    ]
    spans = _merge_adjacent_spans(valid_spans)

    formatting_json = ""
    if spans:
        payload = {
            "font_family": _DEFAULT_FONT_FAMILY,
            "font_size": _DEFAULT_FONT_SIZE,
            "spans": spans,
        }
        formatting_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    return content, formatting_json


def read_docx_file(file_path: str) -> Tuple[str, str]:
    """
    Lê um arquivo .docx (OOXML ZIP) preservando parágrafos, quebras de linha, tabelas e formatação rica.
    Retorna (texto_puro, formatting_json).
    """
    with zipfile.ZipFile(file_path, "r") as zf:
        xml_bytes = _extract_docx_body_xml(zf)
    return _parse_wordprocessing_xml(xml_bytes)


# =============================================================================
# 2. Parser Nativo de RTF (para arquivos .doc que na verdade são RTF)
# =============================================================================

_RTF_SKIP_DESTINATIONS = frozenset({
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object",
    "header", "footer", "headerl", "headerr", "headerf",
    "footerl", "footerr", "footerf", "fldinst", "listtable",
    "listoverridetable", "revtbl", "rsidtbl", "generator", "themedata",
    "colorschememapping", "datastore", "xmlnstbl", "latentstyles", "mmathPr",
})


def _read_rtf_bytes(raw: bytes) -> str:
    """Extrai texto limpo com acentuação de documentos RTF."""
    text = raw.decode("latin1", errors="replace")
    out: List[str] = []
    stack: List[Tuple[int, bool]] = []
    uc_skip = 1
    ignorable = False
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if ch == "{":
            stack.append((uc_skip, ignorable))
            i += 1
        elif ch == "}":
            if stack:
                uc_skip, ignorable = stack.pop()
            i += 1
        elif ch in ("\r", "\n"):
            i += 1
        elif ch == "\\":
            i += 1
            if i >= n:
                break
            nxt = text[i]
            if nxt in ("\\", "{", "}"):
                if not ignorable:
                    out.append(nxt)
                i += 1
            elif nxt == "~":
                if not ignorable:
                    out.append(" ")
                i += 1
            elif nxt == "-":
                i += 1
            elif nxt == "_":
                if not ignorable:
                    out.append("-")
                i += 1
            elif nxt == "*":
                ignorable = True
                i += 1
            elif nxt == "'":
                # Hex escape \'xx (cp1252)
                hex_part = text[i + 1 : i + 3]
                if len(hex_part) == 2:
                    try:
                        b = bytes([int(hex_part, 16)])
                        if not ignorable:
                            out.append(b.decode("cp1252", errors="replace"))
                    except ValueError:
                        pass
                    i += 3
                else:
                    i += 1
            elif nxt.isalpha():
                w_start = i
                while i < n and text[i].isalpha():
                    i += 1
                word = text[w_start:i]
                num_start = i
                if i < n and text[i] in ("-", "+"):
                    i += 1
                while i < n and text[i].isdigit():
                    i += 1
                num_str = text[num_start:i]
                if i < n and text[i] == " ":
                    i += 1

                if word in _RTF_SKIP_DESTINATIONS:
                    ignorable = True
                elif word == "uc" and num_str:
                    try:
                        uc_skip = max(0, int(num_str))
                    except ValueError:
                        pass
                elif word == "u" and num_str:
                    try:
                        code = int(num_str)
                        if code < 0:
                            code += 65536
                        if not ignorable:
                            out.append(chr(code))
                        # Pula caracteres substitutos ANSI conforme \ucN
                        skipped = 0
                        while skipped < uc_skip and i < n:
                            if text[i] == "\\" and i + 3 < n and text[i + 1] == "'":
                                i += 4
                            elif text[i] in ("{", "}"):
                                break
                            else:
                                i += 1
                            skipped += 1
                    except Exception:
                        pass
                elif not ignorable:
                    if word in ("par", "line"):
                        out.append("\n")
                    elif word == "tab":
                        out.append("\t")
                    elif word == "emdash":
                        out.append("—")
                    elif word == "endash":
                        out.append("–")
                    elif word in ("lquote", "rquote"):
                        out.append("'")
                    elif word in ("ldblquote", "rdblquote"):
                        out.append('"')
                    elif word == "bullet":
                        out.append("• ")
            else:
                i += 1
        else:
            if not ignorable:
                out.append(ch)
            i += 1

    return "".join(out).strip()


# =============================================================================
# 3. Parser Nativo de HTML/Word-HTML (para arquivos .doc gerados em HTML)
# =============================================================================

class _SimpleHTMLTextExtractor(HTMLParser):
    _BLOCK_TAGS = frozenset({"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"})
    _SKIP_TAGS = frozenset({"script", "style", "head", "xml", "title"})

    def __init__(self):
        super().__init__()
        self._parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        t = tag.lower()
        if t in self._SKIP_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0:
            if t == "br":
                self._parts.append("\n")
            elif t == "td" or t == "th":
                if self._parts and not self._parts[-1].endswith(("\n", " | ")):
                    self._parts.append(" | ")

    def handle_endtag(self, tag: str):
        t = tag.lower()
        if t in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif self._skip_depth == 0 and t in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str):
        if self._skip_depth == 0 and data:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = html.unescape("".join(self._parts))
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        # Colapsa múltiplas linhas em branco consecutivas
        cleaned: List[str] = []
        prev_blank = False
        for ln in lines:
            if not ln:
                if not prev_blank and cleaned:
                    cleaned.append("")
                prev_blank = True
            else:
                cleaned.append(ln)
                prev_blank = False
        return "\n".join(cleaned).strip()


def _read_html_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "iso-8859-1"):
        try:
            decoded = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        decoded = raw.decode("latin1", errors="replace")

    parser = _SimpleHTMLTextExtractor()
    parser.feed(decoded)
    return parser.get_text()


# =============================================================================
# 4. Parser Nativo OLE2 / CFBF + MS-DOC (Word 97-2003 em Python puro!)
# =============================================================================

_ENDOFCHAIN = 0xFFFFFFFE
_FREESECT = 0xFFFFFFFF


def _read_ole2_streams(data: bytes) -> Dict[str, bytes]:
    """
    Lê os streams de um arquivo Compound File Binary Format (OLE2 / .doc)
    em Python puro usando apenas `struct`, sem dependências externas.
    """
    if len(data) < 512 or data[:8] != _OLE2_SIGNATURE:
        raise ValueError("Arquivo não possui assinatura OLE2 válida.")

    sector_shift = struct.unpack_from("<H", data, 0x1E)[0]
    mini_sector_shift = struct.unpack_from("<H", data, 0x20)[0]
    sector_size = 1 << sector_shift
    mini_sector_size = 1 << mini_sector_shift

    first_dir_sector = struct.unpack_from("<I", data, 0x30)[0]
    mini_stream_cutoff = struct.unpack_from("<I", data, 0x38)[0]
    first_minifat_sector = struct.unpack_from("<I", data, 0x3C)[0]
    first_difat_sector = struct.unpack_from("<I", data, 0x44)[0]
    num_difat_sectors = struct.unpack_from("<I", data, 0x48)[0]

    def _sector_offset(sec_id: int) -> int:
        return (sec_id + 1) * sector_size

    def _read_sector(sec_id: int) -> bytes:
        off = _sector_offset(sec_id)
        return data[off : off + sector_size]

    # 1. Monta lista de setores da FAT a partir do cabeçalho (109 entradas) + cadeia DIFAT
    fat_sectors: List[int] = [
        sec for sec in struct.unpack_from("<109I", data, 0x4C)
        if sec not in (_FREESECT, _ENDOFCHAIN)
    ]
    difat_sec = first_difat_sector
    entries_per_sector = sector_size // 4
    visited_difat = set()
    for _ in range(num_difat_sectors):
        if difat_sec in (_FREESECT, _ENDOFCHAIN) or difat_sec in visited_difat:
            break
        visited_difat.add(difat_sec)
        buf = _read_sector(difat_sec)
        if len(buf) < sector_size:
            break
        vals = struct.unpack(f"<{entries_per_sector}I", buf)
        for sec in vals[:-1]:
            if sec not in (_FREESECT, _ENDOFCHAIN):
                fat_sectors.append(sec)
        difat_sec = vals[-1]

    # 2. Monta tabela FAT completa
    fat: List[int] = []
    for sec_id in fat_sectors:
        buf = _read_sector(sec_id)
        if len(buf) < sector_size:
            break
        fat.extend(struct.unpack(f"<{entries_per_sector}I", buf))

    def _read_chain(start_sec: int, max_size: Optional[int] = None) -> bytes:
        chunks: List[bytes] = []
        sec = start_sec
        visited = set()
        total = 0
        while sec not in (_FREESECT, _ENDOFCHAIN) and sec < len(fat) and sec not in visited:
            visited.add(sec)
            chunk = _read_sector(sec)
            chunks.append(chunk)
            total += len(chunk)
            if max_size is not None and total >= max_size:
                break
            sec = fat[sec]
        raw = b"".join(chunks)
        return raw[:max_size] if max_size is not None else raw

    # 3. Lê o Directory Stream e extrai entradas (128 bytes cada)
    dir_bytes = _read_chain(first_dir_sector)
    entries = []
    for off in range(0, len(dir_bytes) - 127, 128):
        name_len = struct.unpack_from("<H", dir_bytes, off + 64)[0]
        obj_type = dir_bytes[off + 66]
        if obj_type == 0 or name_len < 2 or name_len > 64:
            continue
        name = dir_bytes[off : off + name_len - 2].decode("utf-16-le", errors="ignore")
        start_sec = struct.unpack_from("<I", dir_bytes, off + 116)[0]
        size_low = struct.unpack_from("<I", dir_bytes, off + 120)[0]
        entries.append((name, obj_type, start_sec, size_low))

    # 4. Lê MiniStream (do Root Entry, obj_type == 5) e MiniFAT caso existam streams pequenos
    mini_stream = b""
    minifat: List[int] = []
    for _name, obj_type, start_sec, size_low in entries:
        if obj_type == 5 and start_sec not in (_FREESECT, _ENDOFCHAIN):
            mini_stream = _read_chain(start_sec, size_low)
            break

    if first_minifat_sector not in (_FREESECT, _ENDOFCHAIN) and mini_stream:
        mf_bytes = _read_chain(first_minifat_sector)
        if len(mf_bytes) >= 4:
            minifat = list(struct.unpack(f"<{len(mf_bytes) // 4}I", mf_bytes[: (len(mf_bytes) // 4) * 4]))

    def _read_mini_chain(start_sec: int, size: int) -> bytes:
        chunks: List[bytes] = []
        sec = start_sec
        visited = set()
        total = 0
        while sec not in (_FREESECT, _ENDOFCHAIN) and sec < len(minifat) and sec not in visited:
            visited.add(sec)
            off = sec * mini_sector_size
            chunks.append(mini_stream[off : off + mini_sector_size])
            total += mini_sector_size
            if total >= size:
                break
            sec = minifat[sec]
        return b"".join(chunks)[:size]

    # 5. Extrai streams de interesse
    streams: Dict[str, bytes] = {}
    for name, obj_type, start_sec, size_low in entries:
        if obj_type != 2 or size_low == 0:
            continue
        if name in ("WordDocument", "1Table", "0Table"):
            if size_low < mini_stream_cutoff and mini_stream and minifat:
                streams[name] = _read_mini_chain(start_sec, size_low)
            else:
                streams[name] = _read_chain(start_sec, size_low)
    return streams


def _clean_msword_control_chars(raw_text: str) -> str:
    """Limpa códigos de campo e caracteres de controle internos do Word binário (.doc)."""
    # Resolve campos internos (\x13 código \x14 resultado visível \x15): mantém apenas o resultado visível
    out: List[str] = []
    field_depth = 0
    in_field_code = False
    for ch in raw_text:
        if ch == "\x13":
            field_depth += 1
            in_field_code = True
            continue
        if ch == "\x14":
            in_field_code = False
            continue
        if ch == "\x15":
            field_depth = max(0, field_depth - 1)
            if field_depth == 0:
                in_field_code = False
            continue
        if in_field_code:
            continue

        if ch == "\r" or ch == "\x0b":
            out.append("\n")
        elif ch == "\x0c":
            out.append("\n\n")
        elif ch == "\x07":
            # Delimitador de célula/linha em tabelas do Word
            out.append("\t")
        elif ch == "\t" or ch == "\n" or ord(ch) >= 32:
            out.append(ch)

    text = "".join(out)
    # Converte múltiplas tabs de tabela em separador legível mantendo parágrafos
    cleaned_lines: List[str] = []
    for ln in text.splitlines():
        if "\t\t" in ln:
            parts = [p.strip() for p in ln.split("\t") if p.strip()]
            cleaned_lines.append(" | ".join(parts))
        else:
            cleaned_lines.append(ln.rstrip())
    return "\n".join(cleaned_lines).strip()


def read_ole2_doc_native(file_path: str) -> str:
    """
    Parser nativo em Python puro para arquivos .doc (Microsoft Word 97-2003 OLE2)
    seguindo a especificação MS-DOC (FIB + Table Stream + CLX Piece Table).
    Não requer Microsoft Word nem dependências externas.
    """
    with open(file_path, "rb") as f:
        data = f.read()

    streams = _read_ole2_streams(data)
    word_doc = streams.get("WordDocument")
    if not word_doc or len(word_doc) < 0x1B0:
        raise ValueError("Stream 'WordDocument' inválido ou ausente no arquivo .doc.")

    # Verifica criptografia (bit 0x0100 em FibBase.flags no offset 0x000A)
    flags = struct.unpack_from("<H", word_doc, 0x000A)[0]
    if flags & 0x0100:
        raise ValueError("O documento .doc está protegido por senha (criptografado).")

    table_name = "1Table" if (flags & 0x0200) else "0Table"
    table_stream = streams.get(table_name) or streams.get("1Table") or streams.get("0Table")
    if not table_stream:
        raise ValueError(f"Stream de tabela ('{table_name}') não encontrado no arquivo .doc.")

    # ccpText (número de caracteres do texto principal) no offset 0x004C
    ccp_text = struct.unpack_from("<I", word_doc, 0x004C)[0]
    # Localização da estrutura CLX (Piece Table) no Table Stream: fcClx (0x01A2) e lcbClx (0x01A6)
    fc_clx = struct.unpack_from("<I", word_doc, 0x01A2)[0]
    lcb_clx = struct.unpack_from("<I", word_doc, 0x01A6)[0]

    if fc_clx + lcb_clx > len(table_stream) or lcb_clx < 5:
        raise ValueError("Estrutura CLX inválida no arquivo .doc.")

    clx = table_stream[fc_clx : fc_clx + lcb_clx]
    pos = 0
    # Pula eventuais registros Prc (clxt == 0x01)
    while pos < len(clx) and clx[pos] == 0x01:
        if pos + 3 > len(clx):
            break
        cb_grpprl = struct.unpack_from("<H", clx, pos + 1)[0]
        pos += 3 + cb_grpprl

    if pos >= len(clx) or clx[pos] != 0x02:
        raise ValueError("Tabela de peças (Pcdt) não localizada na estrutura CLX do arquivo .doc.")

    pcdt_len = struct.unpack_from("<I", clx, pos + 1)[0]
    plc_pcd = clx[pos + 5 : pos + 5 + pcdt_len]

    # PlcPcd contém (n+1) CPs de 4 bytes + n Pcds de 8 bytes -> tamanho = 4 + 12*n
    n_pieces = (len(plc_pcd) - 4) // 12
    if n_pieces <= 0:
        return ""

    cps = struct.unpack_from(f"<{n_pieces + 1}I", plc_pcd, 0)
    pcd_base = (n_pieces + 1) * 4

    pieces_text: List[str] = []
    for idx in range(n_pieces):
        cp_start = cps[idx]
        cp_end = cps[idx + 1]
        if ccp_text > 0 and cp_start >= ccp_text:
            break
        if ccp_text > 0 and cp_end > ccp_text:
            cp_end = ccp_text
        char_count = cp_end - cp_start
        if char_count <= 0:
            continue

        pcd_off = pcd_base + idx * 8
        fc_val = struct.unpack_from("<I", plc_pcd, pcd_off + 2)[0]
        is_compressed = bool(fc_val & 0x40000000)
        fc_offset = fc_val & 0x3FFFFFFF

        if is_compressed:
            byte_off = fc_offset // 2
            chunk = word_doc[byte_off : byte_off + char_count]
            pieces_text.append(chunk.decode("cp1252", errors="replace"))
        else:
            byte_off = fc_offset
            chunk = word_doc[byte_off : byte_off + char_count * 2]
            pieces_text.append(chunk.decode("utf-16-le", errors="replace"))

    return _clean_msword_control_chars("".join(pieces_text))


def _try_convert_doc_via_word_com(file_path: str) -> Optional[Tuple[str, str]]:
    """
    No Windows, se o Microsoft Word estiver instalado, converte silenciosamente .doc -> .docx
    em pasta temporária para preservar 100% de tabelas, listas e formatação rica.
    Retorna None caso o Word não esteja disponível (acionando o parser nativo Python).
    """
    if os.name != "nt":
        return None
    try:
        import comtypes
        import comtypes.client
    except Exception:
        return None

    word_app = None
    doc = None
    co_inited = False
    tmp_dir = tempfile.mkdtemp(prefix="dailynotes_doc_")
    tmp_docx = os.path.join(tmp_dir, "converted.docx")

    try:
        try:
            comtypes.CoInitialize()
            co_inited = True
        except Exception:
            pass

        word_app = comtypes.client.CreateObject("Word.Application")
        word_app.Visible = False
        try:
            word_app.DisplayAlerts = 0  # wdAlertsNone
        except Exception:
            pass

        abs_path = os.path.abspath(file_path)
        doc = word_app.Documents.Open(
            abs_path,
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
        )
        # 16 = wdFormatXMLDocument (.docx)
        doc.SaveAs2(tmp_docx, FileFormat=16)
        doc.Close(SaveChanges=False)
        doc = None

        if os.path.isfile(tmp_docx):
            return read_docx_file(tmp_docx)
        return None
    except Exception as e:
        logger.debug("Automação Word COM indisponível para '%s' (usando parser nativo): %s", file_path, e)
        return None
    finally:
        if doc is not None:
            try:
                doc.Close(SaveChanges=False)
            except Exception:
                pass
        if word_app is not None:
            try:
                word_app.Quit(SaveChanges=False)
            except Exception:
                pass
        if co_inited:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
        try:
            if os.path.isfile(tmp_docx):
                os.remove(tmp_docx)
            if os.path.isdir(tmp_dir):
                os.rmdir(tmp_dir)
        except Exception:
            pass


def _read_mhtml_or_html_bytes(raw: bytes) -> str:
    """Extrai texto de documentos HTML ou MHTML (Single File Web Page exportado pelo Word)."""
    head_low = raw[:256].lower()
    if b"mime-version:" in head_low or b"content-transfer-encoding: quoted-printable" in raw[:1024].lower():
        try:
            import email
            msg = email.message_from_bytes(raw)
            html_chunks: List[str] = []
            for part in msg.walk():
                ctype = (part.get_content_type() or "").lower()
                if ctype == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_chunks.append(_read_html_bytes(payload))
            if html_chunks:
                return "\n\n".join(ch for ch in html_chunks if ch.strip()).strip()
        except Exception:
            pass
    return _read_html_bytes(raw)


def read_doc_file(file_path: str, use_word_com: bool = True) -> Tuple[str, str]:
    """
    Lê documentos Word (.doc e .docx) detectando automaticamente o formato real pela assinatura:
    - OOXML ZIP (.docx verdadeiro ou renomeado)
    - RTF salvo como .doc ou .docx (ex.: WordPad / sistemas de chamados)
    - Word 2003 XML plano (WordprocessingML <?xml ...?>)
    - HTML / MHTML salvo como .doc ou .docx
    - Binário OLE2 (Word 97-2003 ou .docx legado/container OLE2) via Word COM ou parser nativo
    - Texto puro salvo com extensão .doc ou .docx
    Retorna (texto_puro, formatting_json).
    """
    with open(file_path, "rb") as f:
        head = f.read(1024)

    if not head:
        return "", ""

    # Caso 1: Pacote ZIP / OOXML válido (.docx padrão ou renomeado como .doc)
    if head.startswith(b"PK\x03\x04") and zipfile.is_zipfile(file_path):
        try:
            return read_docx_file(file_path)
        except Exception as e:
            if use_word_com:
                com_res = _try_convert_doc_via_word_com(file_path)
                if com_res is not None:
                    return com_res
            raise e

    # Remove eventual BOM UTF-8 antes de inspecionar assinaturas textuais
    head_nobom = head[3:] if head.startswith(b"\xef\xbb\xbf") else head
    head_stripped = head_nobom.lstrip()
    head_lower = head_stripped[:512].lower()

    # Caso 2: RTF salvo como .doc ou .docx (muito comum em WordPad / ERPs / chamados)
    if head_stripped.startswith(b"{\\rtf"):
        with open(file_path, "rb") as f:
            return _read_rtf_bytes(f.read()), ""

    # Caso 3: Word 2003 XML plano (WordprocessingML / Flat OPC XML)
    if head_lower.startswith(b"<?xml") or b"worddocument" in head_lower or b"mso-application" in head_lower:
        if (
            b"worddocument" in head_lower
            or b"wordprocessingml" in head_lower
            or b"word.document" in head_lower
            or b"<w:body" in head_lower
        ):
            try:
                with open(file_path, "rb") as f:
                    return _parse_wordprocessing_xml(f.read())
            except Exception:
                pass

    # Caso 4: HTML ou MHTML salvo como .doc ou .docx
    if (
        head_lower.startswith(b"<html")
        or head_lower.startswith(b"<!doctype html")
        or head_lower.startswith(b"<meta")
        or head_lower.startswith(b"mime-version:")
        or b"<html" in head_lower
    ):
        with open(file_path, "rb") as f:
            return _read_mhtml_or_html_bytes(f.read()), ""

    # Caso 5: Binário OLE2 (Word 97-2003 ou .docx empacotado em OLE2)
    if head.startswith(_OLE2_SIGNATURE):
        if use_word_com:
            com_res = _try_convert_doc_via_word_com(file_path)
            if com_res is not None:
                return com_res
        return read_ole2_doc_native(file_path), ""

    # Caso 6: Arquivo de texto puro (UTF-8, ANSI ou UTF-16) salvo com extensão .doc ou .docx
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        with open(file_path, "r", encoding="utf-16", errors="replace") as f:
            return f.read(), ""

    if b"\x00" not in head:
        enc = detect_encoding(file_path)
        with open(file_path, "r", encoding=enc, errors="replace") as f:
            return f.read(), ""

    # Caso 7: Outro formato binário proprietário -> tenta Word COM se disponível no Windows
    if use_word_com:
        com_res = _try_convert_doc_via_word_com(file_path)
        if com_res is not None:
            return com_res

    raise ValueError(
        "Formato binário de documento Word não reconhecido (verifique se o arquivo não está corrompido ou protegido por senha)."
    )


# =============================================================================
# 5. Ponto de Entrada Unificado
# =============================================================================

def read_document_file(file_path: str, use_word_com: bool = True) -> Tuple[str, str, str]:
    """
    Lê qualquer arquivo suportado pelo DailyNotes (.txt, .xml, .bat, .sql, .doc, .docx).
    Para .doc e .docx, detecta o formato interno real pela assinatura (OOXML ZIP, RTF,
    Word XML, HTML/MHTML, OLE2 binário ou texto puro).
    Retorna (conteudo_texto, formato_ou_codificacao, formatting_json).
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".docx", ".doc"):
        content, fmt_json = read_doc_file(file_path, use_word_com=use_word_com)
        return content, ext.lstrip("."), fmt_json

    encoding = detect_encoding(file_path)
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        content = f.read()
    return content, encoding, ""
