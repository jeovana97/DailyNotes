import re
from typing import Tuple
from .date_utils import parse_date_input


def validate_username(username: str) -> Tuple[bool, str]:
    """
    Valida o nome de usuário para login.
    Regras:
    - Pelo menos 3 caracteres
    - Apenas letras, números, pontos e underlines
    """
    if not username or not username.strip():
        return False, "O nome de usuário não pode estar em branco."

    username = username.strip()
    if len(username) < 3:
        return False, "O nome de usuário deve conter no mínimo 3 caracteres."

    if not re.match(r"^[a-zA-Z0-9_\.]+$", username):
        return False, "O usuário deve conter apenas letras, números, ponto (.) ou sublinhado (_)."

    return True, ""


def validate_password(password: str) -> Tuple[bool, str]:
    """
    Valida a senha do usuário.
    Regras:
    - No mínimo 4 caracteres
    """
    if not password:
        return False, "A senha não pode estar em branco."

    if len(password) < 4:
        return False, "A senha deve conter pelo menos 4 caracteres."

    return True, ""


def validate_date(date_str: str) -> Tuple[bool, str]:
    """
    Valida se uma data inserida pelo usuário é válida (DD/MM/AAAA ou YYYY-MM-DD).
    """
    if not date_str or not date_str.strip():
        return False, "A data não pode estar vazia."

    iso = parse_date_input(date_str)
    if not iso:
        return False, "Data inválida. Utilize o formato DD/MM/AAAA (ex: 27/10/2026)."

    return True, ""
