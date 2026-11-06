import datetime
import re
from typing import Optional, Tuple

# Mapeamento de meses e dias em português
MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

DIAS_SEMANA_PT = [
    "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
    "Sexta-feira", "Sábado", "Domingo"
]


def get_today_iso() -> str:
    """Retorna a data de hoje no formato ISO YYYY-MM-DD."""
    return datetime.date.today().isoformat()


def get_current_timestamp() -> str:
    """Retorna o timestamp atual no formato YYYY-MM-DD HH:MM:SS."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_valid_iso_date(date_str: str) -> bool:
    """Verifica se a string é uma data ISO válida (YYYY-MM-DD)."""
    if not date_str or not isinstance(date_str, str):
        return False
    try:
        datetime.date.fromisoformat(date_str)
        return True
    except ValueError:
        return False


def format_date_br(date_val: Optional[str]) -> str:
    """
    Converte uma data ISO (YYYY-MM-DD) para o formato brasileiro (DD/MM/AAAA).
    Se já estiver em DD/MM/AAAA ou inválida, retorna adequadamente.
    """
    if not date_val:
        return ""
    try:
        if "/" in date_val:
            parts = date_val.split("/")
            if len(parts) == 3 and len(parts[2]) == 4:
                return date_val
        d = datetime.date.fromisoformat(date_val)
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(date_val)


def format_date_long_br(date_val: Optional[str]) -> str:
    """
    Formata uma data para extenso em português.
    Exemplo: 'Terça-feira, 27 de Outubro de 2026'
    """
    if not date_val:
        return ""
    try:
        if "/" in date_val:
            d = parse_br_date_to_iso(date_val)
            if not d:
                return date_val
            dt = datetime.date.fromisoformat(d)
        else:
            dt = datetime.date.fromisoformat(date_val)

        dia_semana = DIAS_SEMANA_PT[dt.weekday()]
        dia = dt.day
        mes = MESES_PT[dt.month - 1]
        ano = dt.year
        return f"{dia_semana}, {dia:02d} de {mes} de {ano}"
    except Exception:
        return str(date_val)


def parse_br_date_to_iso(date_str: Optional[str]) -> Optional[str]:
    """
    Converte string DD/MM/AAAA para YYYY-MM-DD.
    Valida dia, mês e ano.
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str)
    if not match:
        return None
    d, m, y = map(int, match.groups())
    try:
        dt = datetime.date(y, m, d)
        return dt.isoformat()
    except ValueError:
        return None


def parse_date_input(input_str: Optional[str]) -> Optional[str]:
    """
    Tenta interpretar uma entrada de data nos formatos DD/MM/AAAA ou YYYY-MM-DD.
    Retorna sempre formato ISO YYYY-MM-DD ou None se inválida.
    """
    if not input_str:
        return None
    input_str = input_str.strip()
    if is_valid_iso_date(input_str):
        return input_str
    return parse_br_date_to_iso(input_str)


def parse_date_from_filename(filename: str) -> Optional[str]:
    """
    Extrai uma data válida do nome de um arquivo.
    Suporta o padrão principal com espaços: 'DD MM AAAA.txt' (ex: '01 10 2026.txt', '27 10 2026.txt')
    E também variações com hífen, underscore ou ponto: 'DD-MM-AAAA.txt', 'DD_MM_AAAA.txt', 'DD.MM.AAAA.txt'
    E formato ISO 'AAAA-MM-DD.txt'.
    Retorna formato ISO YYYY-MM-DD ou None se não for data válida.
    """
    if not filename:
        return None

    # Remove extensão do arquivo
    clean_name = re.sub(r"\.[^.]+$", "", filename).strip()

    # Padrão 1: DD MM AAAA (com espaços, hífens, underscores ou barras)
    match_br = re.search(r"(\b\d{1,2})[\s\-_\.\/](\d{1,2})[\s\-_\.\/](\d{4})\b", clean_name)
    if match_br:
        d, m, y = map(int, match_br.groups())
        try:
            dt = datetime.date(y, m, d)
            return dt.isoformat()
        except ValueError:
            pass

    # Padrão 2: AAAA-MM-DD (ISO)
    match_iso = re.search(r"(\b\d{4})[\s\-_\.\/](\d{1,2})[\s\-_\.\/](\d{1,2})\b", clean_name)
    if match_iso:
        y, m, d = map(int, match_iso.groups())
        try:
            dt = datetime.date(y, m, d)
            return dt.isoformat()
        except ValueError:
            pass

    return None


def add_days_to_iso(date_iso: str, days: int) -> str:
    """Adiciona ou subtrai dias de uma data ISO YYYY-MM-DD."""
    dt = datetime.date.fromisoformat(date_iso)
    new_dt = dt + datetime.timedelta(days=days)
    return new_dt.isoformat()
