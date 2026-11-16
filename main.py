import sys
import os
import logging

# Adiciona o diretório base ao sys.path para importações absolutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config
from database.migrations import init_db
from services.schedule_service import ScheduleService
from utils.notification_utils import (
    ensure_app_user_model_id,
    parse_toast_protocol_url,
    write_pending_toast_action,
)
from views.main_window import MainWindow

# Configuração de Logs da Aplicação (sem registrar dados sensíveis ou senhas)
LOG_FILE = os.path.join(config.DATA_DIR, "app.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("DiarioAnotacoes")


def _acquire_single_instance_mutex():
    """
    Cria um Mutex nomeado no Windows para identificar se já existe uma instância
    da aplicação rodando. Retorna (handle, already_running).
    """
    if sys.platform != "win32":
        return None, False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "DailyNotes_Running_Instance_Mutex")
        already_running = (kernel32.GetLastError() == 183)  # ERROR_ALREADY_EXISTS
        return handle, already_running
    except Exception:
        return None, False


def main():
    logger.info("Iniciando %s v%s ...", config.APP_NAME, config.APP_VERSION)

    # Define e registra AppUserModelID e protocolo dailynotes:// no Windows
    if sys.platform == "win32":
        try:
            ensure_app_user_model_id()
        except Exception:
            pass

    # Verifica se foi acionado por um botão de notificação Toast (dailynotes://...)
    toast_cmd = None
    for arg in sys.argv[1:]:
        parsed = parse_toast_protocol_url(arg)
        if parsed:
            toast_cmd = parsed
            break

    _mutex_handle, already_running = _acquire_single_instance_mutex()

    try:
        # 1. Inicializa o banco de dados e cria as tabelas necessárias
        init_db(config.DB_PATH)

        if toast_cmd is not None:
            action = toast_cmd.get("action")
            sched_id = toast_cmd.get("schedule_id")
            if action == "snooze":
                minutes = toast_cmd.get("minutes", 10)
                if sched_id is not None:
                    ScheduleService(config.DB_PATH).snooze_schedule(sched_id, minutes=minutes)
                write_pending_toast_action(
                    {"action": "snooze_refresh", "schedule_id": sched_id, "minutes": minutes}
                )
                return
            elif action == "open":
                write_pending_toast_action(
                    {"action": "open_schedule", "schedule_id": sched_id}
                )
                if already_running:
                    # A instância já aberta processará a ação e trará a janela para frente
                    return

        # 2. Inicia a interface gráfica
        app = MainWindow(db_path=config.DB_PATH)
        app.mainloop()

    except Exception as e:
        logger.critical("Erro fatal não tratado na aplicação: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
