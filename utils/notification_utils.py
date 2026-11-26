"""
Utilitário para disparo de notificações nativas do Windows (Toast Notifications).
Utiliza a API nativa do Windows Runtime via PowerShell sem necessidade de dependências externas adicionais.
"""

import os
import sys
import json
import time
import base64
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs

import config

logger = logging.getLogger(__name__)

APP_USER_MODEL_ID = "DailyNotes.DiarioAnotacoes"
APP_DISPLAY_NAME = "DailyNotes - Diário de Anotações"
PROTOCOL_SCHEME = "dailynotes"


def xml_escape(s: str) -> str:
    """Escapa caracteres especiais para inserção segura em XML de Notificações Toast."""
    if not s:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _get_app_icon_path() -> Optional[str]:
    """Retorna o caminho absoluto para o ícone do aplicativo (PNG preferido para Toast)."""
    candidates = [
        os.path.join(config.RESOURCE_DIR, "assets", "icon.png"),
        os.path.join(config.RESOURCE_DIR, "assets", "icon.ico"),
        os.path.join(config.BASE_DIR, "assets", "icon.png"),
        os.path.join(config.BASE_DIR, "assets", "icon.ico"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return None


def register_url_protocol(scheme: str = PROTOCOL_SCHEME) -> bool:
    """
    Registra o protocolo customizado 'dailynotes://' no registro do usuário atual (HKCU)
    para que cliques em botões das notificações Toast acionem o aplicativo diretamente.
    """
    if os.name != "nt":
        return False

    try:
        import winreg

        if getattr(sys, "frozen", False):
            cmd_str = f'"{sys.executable}" "%1"'
        else:
            py_dir = os.path.dirname(sys.executable)
            pythonw_exe = os.path.join(py_dir, "pythonw.exe")
            exe_to_use = pythonw_exe if os.path.isfile(pythonw_exe) else sys.executable
            main_py = os.path.abspath(os.path.join(config.BASE_DIR, "main.py"))
            cmd_str = f'"{exe_to_use}" "{main_py}" "%1"'

        base_key = rf"Software\Classes\{scheme}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base_key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:DailyNotes Protocol")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")

        icon_path = _get_app_icon_path()
        if icon_path:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base_key}\DefaultIcon") as ik:
                winreg.SetValueEx(ik, "", 0, winreg.REG_SZ, f'"{icon_path}",0')

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base_key}\shell\open\command") as ck:
            winreg.SetValueEx(ck, "", 0, winreg.REG_SZ, cmd_str)

        return True
    except Exception as ex:
        logger.debug("Não foi possível registrar protocolo %s://: %s", scheme, ex)
        return False


def parse_toast_protocol_url(url: str) -> Optional[Dict[str, Any]]:
    """
    Interpreta uma URL de ação de notificação Toast no formato:
    - dailynotes://schedule/open?id=123
    - dailynotes://schedule/snooze?id=123&minutes=10
    Retorna dict com action, schedule_id e minutes, ou None se inválido.
    """
    if not url or not str(url).strip().lower().startswith(f"{PROTOCOL_SCHEME}://"):
        return None
    try:
        parsed = urlparse(str(url).strip())
        action_path = f"{parsed.netloc}{parsed.path}".strip("/").lower()
        qs = parse_qs(parsed.query)

        schedule_id = None
        if "id" in qs and qs["id"]:
            try:
                schedule_id = int(qs["id"][0])
            except ValueError:
                schedule_id = None

        minutes = 10
        if "minutes" in qs and qs["minutes"]:
            try:
                minutes = max(1, int(qs["minutes"][0]))
            except ValueError:
                minutes = 10

        if action_path in ("schedule/open", "open"):
            return {"action": "open", "schedule_id": schedule_id}
        if action_path in ("schedule/snooze", "snooze"):
            return {"action": "snooze", "schedule_id": schedule_id, "minutes": minutes}
        if action_path == "task/open":
            return {"action": "open_task", "task_id": schedule_id, "schedule_id": schedule_id}
        if action_path == "task/snooze":
            return {"action": "snooze_task", "task_id": schedule_id, "schedule_id": schedule_id, "minutes": minutes}
        return None
    except Exception:
        return None


def _get_pending_action_file(data_dir: Optional[str] = None) -> str:
    base_dir = data_dir or config.DATA_DIR
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "pending_toast_action.json")


def write_pending_toast_action(action_data: Dict[str, Any], data_dir: Optional[str] = None) -> None:
    """Grava uma ação pendente disparada por botão da notificação para a janela principal processar."""
    target = _get_pending_action_file(data_dir)
    payload = dict(action_data)
    payload["timestamp"] = time.time()
    tmp_path = f"{target}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp_path, target)


def consume_pending_toast_action(data_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Lê e remove o arquivo de ação pendente de notificação Toast, se existir."""
    target = _get_pending_action_file(data_dir)
    if not os.path.isfile(target):
        return None
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            os.remove(target)
        except Exception:
            pass
        return data
    except Exception:
        try:
            os.remove(target)
        except Exception:
            pass
        return None


def ensure_app_user_model_id(
    aumid: str = APP_USER_MODEL_ID,
    display_name: str = APP_DISPLAY_NAME,
) -> str:
    """
    Registra o AppUserModelID (AUMID) do DailyNotes no registro do usuário atual (HKCU)
    para que as notificações do Windows exibam o nome e o ícone do aplicativo em vez
    de 'Windows PowerShell'. Também associa o AUMID ao processo atual.
    """
    if os.name != "nt":
        return aumid

    icon_path = _get_app_icon_path()

    try:
        import winreg
        key_path = rf"Software\Classes\AppUserModelId\{aumid}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, display_name)
            winreg.SetValueEx(key, "ShowInSettings", 0, winreg.REG_DWORD, 1)
            if icon_path:
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon_path)
    except Exception as ex:
        logger.debug("Não foi possível registrar AppUserModelId no registro: %s", ex)

    register_url_protocol()

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(aumid)
    except Exception:
        pass

    return aumid


def send_windows_notification(
    title: str,
    message: str,
    app_id: str = APP_USER_MODEL_ID,
    play_sound: bool = True,
    run_async: bool = True,
    schedule_id: Optional[int] = None,
    snooze_minutes: int = 10,
    task_id: Optional[int] = None,
) -> bool:
    """
    Exibe uma notificação nativa do Windows (Toast Notification) na Central de Ações.
    - title: Título da notificação (ex: 'DailyNotes - Agendamento')
    - message: Mensagem descritiva (ex: 'Reunião às 15:00')
    - play_sound: Toca o sinal sonoro nativo do Windows
    - run_async: Executa em thread separada para não bloquear a interface do usuário
    - schedule_id: ID do agendamento associado (habilita botões Abrir Agendamento e Adiar)
    - snooze_minutes: Minutos para adiar no botão Adiar (padrão 10 min)
    """
    if os.name != "nt":
        logger.info("Notificação ignorada (sistema não é Windows): %s - %s", title, message)
        return False

    def _worker():
        try:
            # Normaliza chamadas legadas que passavam app_id="DailyNotes"
            effective_aumid = APP_USER_MODEL_ID if (not app_id or app_id == "DailyNotes") else app_id
            resolved_aumid = ensure_app_user_model_id(aumid=effective_aumid)

            # Toca sinal sonoro nativo do Windows
            if play_sound:
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except Exception:
                    pass

            t = xml_escape(title)
            m = xml_escape(message)

            icon_path = _get_app_icon_path()
            image_xml = ""
            if icon_path:
                icon_uri = xml_escape(Path(icon_path).as_uri())
                image_xml = f'<image placement="appLogoOverride" hint-crop="circle" src="{icon_uri}"/>'

            if task_id is not None:
                open_arg = xml_escape(f"{PROTOCOL_SCHEME}://task/open?id={int(task_id)}")
                snooze_arg = xml_escape(
                    f"{PROTOCOL_SCHEME}://task/snooze?id={int(task_id)}&minutes={int(snooze_minutes)}"
                )
                actions_xml = f"""
    <actions>
        <action content="✅ Abrir Tarefa" activationType="protocol" arguments="{open_arg}"/>
        <action content="⏰ Adiar {int(snooze_minutes)} min" activationType="protocol" arguments="{snooze_arg}"/>
    </actions>"""
            elif schedule_id is not None:
                open_arg = xml_escape(f"{PROTOCOL_SCHEME}://schedule/open?id={int(schedule_id)}")
                snooze_arg = xml_escape(
                    f"{PROTOCOL_SCHEME}://schedule/snooze?id={int(schedule_id)}&minutes={int(snooze_minutes)}"
                )
                actions_xml = f"""
    <actions>
        <action content="📅 Abrir Agendamento" activationType="protocol" arguments="{open_arg}"/>
        <action content="⏰ Adiar {int(snooze_minutes)} min" activationType="protocol" arguments="{snooze_arg}"/>
    </actions>"""
            else:
                open_arg = xml_escape(f"{PROTOCOL_SCHEME}://schedule/open")
                actions_xml = f"""
    <actions>
        <action content="📅 Abrir Agendamentos" activationType="protocol" arguments="{open_arg}"/>
    </actions>"""

            aumid_escaped = resolved_aumid.replace('"', '`"')

            # Script PowerShell que utiliza a API nativa de Toast Notifications do Windows 10/11
            ps_code = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$xml = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            {image_xml}
            <text>{t}</text>
            <text>{m}</text>
        </binding>
    </visual>{actions_xml}
</toast>
"@

$doc = [Windows.Data.Xml.Dom.XmlDocument]::new()
$doc.LoadXml($xml)
$toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{aumid_escaped}")
$notifier.Show($toast)
"""
            encoded = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")
            cmd = [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                encoded,
            ]

            # Inicia o processo sem abrir janela de console
            startupinfo = None
            if hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE

            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                timeout=12,
            )
            if res.returncode != 0:
                logger.warning("Erro ao disparar notificação Windows: %s", res.stderr)
                return False
            return True
        except Exception as ex:
            logger.warning("Falha ao enviar notificação nativa do Windows: %s", ex)
            return False

    if run_async:
        threading.Thread(target=_worker, daemon=True).start()
        return True
    else:
        return _worker()

