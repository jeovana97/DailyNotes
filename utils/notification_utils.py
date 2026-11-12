"""
Utilitário para disparo de notificações nativas do Windows (Toast Notifications).
Utiliza a API nativa do Windows Runtime via PowerShell sem necessidade de dependências externas adicionais.
"""

import os
import sys
import base64
import logging
import threading
import subprocess

logger = logging.getLogger(__name__)


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


def send_windows_notification(
    title: str,
    message: str,
    app_id: str = "DailyNotes",
    play_sound: bool = True,
    run_async: bool = True,
) -> bool:
    """
    Exibe uma notificação nativa do Windows (Toast Notification) na Central de Ações.
    - title: Título da notificação (ex: 'DailyNotes - Agendamento')
    - message: Mensagem descritiva (ex: 'Reunião às 15:00')
    - play_sound: Toca o sinal sonoro nativo do Windows
    - run_async: Executa em thread separada para não bloquear a interface do usuário
    """
    if os.name != "nt":
        logger.info("Notificação ignorada (sistema não é Windows): %s - %s", title, message)
        return False

    def _worker():
        try:
            # Toca sinal sonoro nativo do Windows
            if play_sound:
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except Exception:
                    pass

            t = xml_escape(title)
            m = xml_escape(message)

            # Script PowerShell que utiliza a API nativa de Toast Notifications do Windows 10/11
            ps_code = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$xml = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>{t}</text>
            <text>{m}</text>
        </binding>
    </visual>
</toast>
"@

$doc = [Windows.Data.Xml.Dom.XmlDocument]::new()
$doc.LoadXml($xml)
$toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe")
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

