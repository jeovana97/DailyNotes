# Diário de Anotações Inteligente
# Configurações gerais da aplicação

import os
import sys

# Informações da Aplicação
try:
    from version import APP_NAME, APP_VERSION, APP_AUTHOR, GITHUB_REPO_OWNER, GITHUB_REPO_NAME, GITHUB_API_LATEST_RELEASE, GITHUB_RELEASES_URL
except ImportError:
    APP_NAME = "Diário de Anotações Inteligente"
    APP_VERSION = "1.2.0"
    APP_AUTHOR = "DAILYNotes"
    GITHUB_REPO_OWNER = "jeovana97"
    GITHUB_REPO_NAME = "DailyNotes"
    GITHUB_API_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
    GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases"

# Diretório base da aplicação (suporta execução normal e congelada por PyInstaller)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = BASE_DIR

# Diretório de ícones e recursos visuais
ASSETS_DIR = os.path.join(RESOURCE_DIR, "assets")
ICON_ICO_PATH = os.path.join(ASSETS_DIR, "icon.ico")
ICON_PNG_PATH = os.path.join(ASSETS_DIR, "icon.png")

# Diretório de dados persistentes do usuário
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Caminho do banco de dados SQLite
DB_PATH = os.path.join(DATA_DIR, "diario.db")

# Configurações visuais do CustomTkinter
APPEARANCE_MODE = "dark"  # "dark" ou "light"
DEFAULT_COLOR_THEME = "blue"  # "blue", "green", "dark-blue"

# Cores da interface moderna com suporte nativo adaptativo a Tema Claro e Escuro
# Cada token usa o formato (Modo_Claro, Modo_Escuro), permitindo que o CustomTkinter
# atualize dinamicamente todos os componentes ao alternar o tema.
COLORS = {
    # Cores de Ação e Destaque
    "primary": ("#2563EB", "#3B82F6"),         # Azul Real / Azul Elétrico
    "primary_hover": ("#1D4ED8", "#2563EB"),
    "secondary": ("#7C3AED", "#8B5CF6"),       # Roxo / Violeta
    "secondary_hover": ("#6D28D9", "#7C3AED"),
    "accent": ("#4F46E5", "#6366F1"),          # Índigo
    "accent_hover": ("#4338CA", "#4F46E5"),
    "success": ("#059669", "#10B981"),         # Esmeralda
    "success_hover": ("#047857", "#059669"),
    "warning": ("#D97706", "#F59E0B"),         # Âmbar
    "warning_hover": ("#B45309", "#D97706"),
    "danger": ("#DC2626", "#EF4444"),          # Vermelho suave
    "danger_hover": ("#B91C1C", "#DC2626"),

    # Tokens Semânticos de Superfície e Tipografia (Light Mode, Dark Mode)
    "bg_dark": ("#F8FAFC", "#0B1120"),          # Fundo geral da janela
    "sidebar": ("#F1F5F9", "#0F172A"),         # Fundo da barra lateral
    "card_dark": ("#FFFFFF", "#1E293B"),        # Cards, painéis e barras
    "card_dark_alt": ("#E2E8F0", "#334155"),    # Botões secundários e sub-cards
    "text_dark": ("#0F172A", "#F8FAFC"),        # Texto principal de alto contraste
    "text_muted": ("#64748B", "#94A3B8"),      # Texto secundário e legendas
    "border_dark": ("#CBD5E1", "#334155"),      # Bordas e divisores
    "button_text": ("#0F172A", "#F8FAFC"),     # Texto de botões neutros/secundários

    # Aliases retrocompatíveis
    "bg_light": "#F8FAFC",
    "card_light": "#FFFFFF",
    "card_light_alt": "#E2E8F0",
    "text_light": "#0F172A",
    "border_light": "#CBD5E1",
}

# Configurações de Autosave
AUTOSAVE_DELAY_SECONDS = 5
