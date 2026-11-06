import sys
import os
import logging

# Adiciona o diretório base ao sys.path para importações absolutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config
from database.migrations import init_db
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


def main():
    logger.info("Iniciando %s v%s ...", config.APP_NAME, config.APP_VERSION)

    # Define AppUserModelID no Windows para que a barra de tarefas exiba o ícone próprio do aplicativo
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DAILYNotes.DiarioAnotacoes.1.0")
        except Exception:
            pass

    try:
        # 1. Inicializa o banco de dados e cria as tabelas necessárias
        init_db(config.DB_PATH)

        # 2. Inicia a interface gráfica
        app = MainWindow(db_path=config.DB_PATH)
        app.mainloop()

    except Exception as e:
        logger.critical("Erro fatal não tratado na aplicação: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
