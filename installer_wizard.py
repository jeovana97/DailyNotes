"""
Assistente de Instalação (Setup Wizard) para Windows - Diário de Anotações Inteligente.
Este script é compilado pelo PyInstaller em um único pacote instalador executável:
    dist/Instalador_DiarioAnotacoes_Setup.exe (e dist/DiarioAnotacoes_Setup.exe)
que embute o pacote da aplicação (app_payload.zip em modo --onedir) e os ícones da aplicação,
eliminando qualquer necessidade de descompressão de .pyd/.dll em %TEMP% a cada execução.
"""

import os
import sys
import shutil
import zipfile
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "Diário de Anotações Inteligente"
APP_SHORT_NAME = "Diário de Anotações"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "DAILYNotes"
EXE_FILENAME = "DiarioAnotacoes.exe"


def get_bundled_resource_dir() -> str:
    """Retorna o diretório onde os arquivos embutidos pelo PyInstaller estão extraídos."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_default_install_dir() -> str:
    """Retorna o caminho padrão de instalação no Windows (%LOCALAPPDATA%\\Programs\\DiarioAnotacoes)."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        local_appdata = os.path.expanduser("~\\AppData\\Local")
    return os.path.join(local_appdata, "Programs", "DiarioAnotacoes")


def get_clean_child_env() -> dict:
    """
    Retorna um dicionário de variáveis de ambiente limpo das variáveis internas do bootloader
    PyInstaller (_PYI_*, _MEIPASS*, TCL_LIBRARY, TK_LIBRARY) e ativa PYINSTALLER_RESET_ENVIRONMENT=1,
    garantindo que o executável instalado inicie de forma totalmente isolada do processo instalador.
    """
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in list(env.keys()):
        upper_k = key.upper()
        if (
            upper_k.startswith("_PYI_")
            or upper_k.startswith("_MEI")
            or upper_k in ("TCL_LIBRARY", "TK_LIBRARY", "PYTHONPATH", "PYTHONHOME")
        ):
            env.pop(key, None)
    return env


def create_windows_shortcut(target_exe: str, shortcut_path: str, icon_path: str, working_dir: str, description: str):
    """Cria um atalho (.lnk) nativo do Windows utilizando WScript.Shell via PowerShell."""
    ps_script = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$s = $ws.CreateShortcut("{shortcut_path}"); '
        f'$s.TargetPath = "{target_exe}"; '
        f'$s.WorkingDirectory = "{working_dir}"; '
        f'$s.IconLocation = "{icon_path},0"; '
        f'$s.Description = "{description}"; '
        f'$s.Save()'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    )


def register_uninstaller_in_registry(install_dir: str, exe_path: str, icon_path: str, uninstaller_bat: str):
    """Registra o aplicativo em 'Aplicativos Instalados' do usuário no Windows (HKCU)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        reg_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\DiarioAnotacoes"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, icon_path)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller_bat}"')
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except Exception:
        pass


def create_uninstaller_script(install_dir: str, desktop_lnk: str, start_menu_lnk: str) -> str:
    """Gera um script Desinstalar.bat na pasta de instalação."""
    bat_path = os.path.join(install_dir, "Desinstalar.bat")
    content = f"""@echo off
chcp 65001 >nul
echo ============================================================
echo   Desinstalador - {APP_NAME}
echo ============================================================
echo.
taskkill /F /IM "{EXE_FILENAME}" >nul 2>&1
if exist "{desktop_lnk}" del /F /Q "{desktop_lnk}"
if exist "{start_menu_lnk}" del /F /Q "{start_menu_lnk}"
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DiarioAnotacoes" /f >nul 2>&1
echo Atalhos e registros removidos com sucesso.
echo A pasta de dados em "{install_dir}\\data" foi preservada por seguranca.
if exist "{install_dir}\\_internal" rmdir /S /Q "{install_dir}\\_internal"
if exist "{install_dir}\\{EXE_FILENAME}" del /F /Q "{install_dir}\\{EXE_FILENAME}"
echo.
echo Desinstalacao concluida!
pause
"""
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(content)
    return bat_path


class InstallerWizardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Instalador - {APP_NAME} v{APP_VERSION}")
        self.geometry("560x430")
        self.resizable(False, False)
        self.configure(bg="#0F172A")

        self.resource_dir = get_bundled_resource_dir()
        self.bundled_zip = os.path.join(self.resource_dir, "payload", "app_payload.zip")
        if not os.path.isfile(self.bundled_zip):
            self.bundled_zip = os.path.join(self.resource_dir, "build", "app_payload.zip")

        self.bundled_exe = os.path.join(self.resource_dir, "payload", EXE_FILENAME)
        if not os.path.isfile(self.bundled_exe):
            self.bundled_exe = os.path.join(self.resource_dir, "dist", EXE_FILENAME)

        self.bundled_icon_ico = os.path.join(self.resource_dir, "assets", "icon.ico")
        self.bundled_icon_png = os.path.join(self.resource_dir, "assets", "icon.png")

        if os.path.isfile(self.bundled_icon_ico):
            try:
                self.iconbitmap(self.bundled_icon_ico)
            except Exception:
                pass

        # Centraliza na tela
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw // 2) - 280
        y = (sh // 2) - 215
        self.geometry(f"560x430+{max(20, x)}+{max(20, y)}")

        self.install_dir_var = tk.StringVar(value=get_default_install_dir())
        self.desktop_shortcut_var = tk.BooleanVar(value=True)
        self.startmenu_shortcut_var = tk.BooleanVar(value=True)
        self.launch_after_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self):
        # Cabeçalho
        header = tk.Frame(self, bg="#1E293B", height=85, highlightthickness=1, highlightbackground="#334155")
        header.pack(fill="x", padx=18, pady=(16, 12))

        title_lbl = tk.Label(
            header,
            text=f"📦 Instalar {APP_NAME}",
            font=("Segoe UI", 15, "bold"),
            fg="#F8FAFC",
            bg="#1E293B",
            anchor="w",
        )
        title_lbl.pack(fill="x", padx=18, pady=(14, 2))

        sub_lbl = tk.Label(
            header,
            text=f"Versão {APP_VERSION} • Instalação rápida e autônoma para Windows (não requer Python)",
            font=("Segoe UI", 9),
            fg="#94A3B8",
            bg="#1E293B",
            anchor="w",
        )
        sub_lbl.pack(fill="x", padx=18, pady=(0, 14))

        # Corpo
        body = tk.Frame(self, bg="#1E293B", highlightthickness=1, highlightbackground="#334155")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        lbl_dir = tk.Label(
            body,
            text="Pasta de destino da instalação:",
            font=("Segoe UI", 10, "bold"),
            fg="#F8FAFC",
            bg="#1E293B",
            anchor="w",
        )
        lbl_dir.pack(fill="x", padx=18, pady=(14, 4))

        dir_row = tk.Frame(body, bg="#1E293B")
        dir_row.pack(fill="x", padx=18, pady=(0, 14))

        self.entry_dir = tk.Entry(
            dir_row,
            textvariable=self.install_dir_var,
            font=("Segoe UI", 10),
            bg="#0F172A",
            fg="#F8FAFC",
            insertbackground="#F8FAFC",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#475569",
        )
        self.entry_dir.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        btn_browse = tk.Button(
            dir_row,
            text="Procurar...",
            font=("Segoe UI", 9, "bold"),
            bg="#334155",
            fg="#F8FAFC",
            activebackground="#3B82F6",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._browse_dir,
        )
        btn_browse.pack(side="right")

        # Opções de atalhos
        chk_style = {
            "font": ("Segoe UI", 10),
            "fg": "#F8FAFC",
            "bg": "#1E293B",
            "selectcolor": "#0F172A",
            "activebackground": "#1E293B",
            "activeforeground": "#F8FAFC",
            "anchor": "w",
        }

        chk_desktop = tk.Checkbutton(
            body,
            text="Criar ícone de atalho na Área de Trabalho (Desktop)",
            variable=self.desktop_shortcut_var,
            **chk_style,
        )
        chk_desktop.pack(fill="x", padx=18, pady=3)

        chk_start = tk.Checkbutton(
            body,
            text="Criar atalho no Menu Iniciar do Windows",
            variable=self.startmenu_shortcut_var,
            **chk_style,
        )
        chk_start.pack(fill="x", padx=18, pady=3)

        chk_launch = tk.Checkbutton(
            body,
            text="Executar o Diário de Anotações ao finalizar a instalação",
            variable=self.launch_after_var,
            **chk_style,
        )
        chk_launch.pack(fill="x", padx=18, pady=3)

        # Status e Barra de progresso
        self.lbl_status = tk.Label(
            body,
            text="Pronto para instalar.",
            font=("Segoe UI", 9),
            fg="#94A3B8",
            bg="#1E293B",
            anchor="w",
        )
        self.lbl_status.pack(fill="x", padx=18, pady=(12, 4))

        self.progress = ttk.Progressbar(body, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=18, pady=(0, 12))

        # Rodapé de botões
        footer = tk.Frame(self, bg="#0F172A")
        footer.pack(fill="x", padx=18, pady=(0, 16))

        self.btn_install = tk.Button(
            footer,
            text="🚀 Instalar Agora",
            font=("Segoe UI", 11, "bold"),
            bg="#2563EB",
            fg="#FFFFFF",
            activebackground="#1D4ED8",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=22,
            pady=7,
            cursor="hand2",
            command=self._run_installation,
        )
        self.btn_install.pack(side="right", padx=(8, 0))

        self.btn_cancel = tk.Button(
            footer,
            text="Cancelar",
            font=("Segoe UI", 10),
            bg="#334155",
            fg="#F8FAFC",
            activebackground="#475569",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=16,
            pady=7,
            cursor="hand2",
            command=self.destroy,
        )
        self.btn_cancel.pack(side="right")

    def _browse_dir(self):
        chosen = filedialog.askdirectory(
            parent=self,
            title="Selecione a pasta onde deseja instalar o Diário de Anotações",
            initialdir=self.install_dir_var.get(),
        )
        if chosen:
            self.install_dir_var.set(os.path.join(chosen, "DiarioAnotacoes"))

    def _set_status(self, msg: str, pct: int):
        self.lbl_status.configure(text=msg)
        self.progress["value"] = pct
        self.update_idletasks()

    def _run_installation(self):
        target_dir = self.install_dir_var.get().strip()
        if not target_dir:
            messagebox.showwarning("Aviso", "Informe uma pasta de destino para a instalação.")
            return

        has_zip = os.path.isfile(self.bundled_zip)
        has_exe = os.path.isfile(self.bundled_exe)
        if not has_zip and not has_exe:
            messagebox.showerror(
                "Erro",
                "Pacote da aplicação não encontrado dentro do instalador.",
            )
            return

        self.btn_install.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")

        try:
            # 0. Encerra instância anterior caso esteja aberta para evitar bloqueio de DLLs/.pyd
            self._set_status("Preparando ambiente de instalação...", 10)
            subprocess.run(
                ["taskkill", "/F", "/IM", EXE_FILENAME],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )

            # 1. Criação de pastas
            self._set_status("Criando diretórios da aplicação...", 20)
            os.makedirs(target_dir, exist_ok=True)
            os.makedirs(os.path.join(target_dir, "data"), exist_ok=True)
            assets_target = os.path.join(target_dir, "assets")
            os.makedirs(assets_target, exist_ok=True)

            # 2. Extração do pacote da aplicação (--onedir sem descompressão em %TEMP%)
            dest_exe = os.path.join(target_dir, EXE_FILENAME)
            if has_zip:
                self._set_status("Extraindo arquivos do aplicativo...", 35)
                with zipfile.ZipFile(self.bundled_zip, "r") as zf:
                    members = zf.namelist()
                    total = max(len(members), 1)
                    for idx, member in enumerate(members):
                        zf.extract(member, target_dir)
                        if idx % 25 == 0 or idx == total - 1:
                            pct = 35 + int((idx / total) * 35)
                            self._set_status(f"Instalando componentes ({idx + 1}/{total})...", pct)
            else:
                self._set_status("Instalando DiarioAnotacoes.exe...", 55)
                shutil.copy2(self.bundled_exe, dest_exe)

            dest_ico = os.path.join(assets_target, "icon.ico")
            if os.path.isfile(self.bundled_icon_ico):
                shutil.copy2(self.bundled_icon_ico, dest_ico)
            if os.path.isfile(self.bundled_icon_png):
                shutil.copy2(self.bundled_icon_png, os.path.join(assets_target, "icon.png"))

            icon_for_shortcut = dest_ico if os.path.isfile(dest_ico) else dest_exe

            # 3. Criação dos atalhos
            desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.isdir(desktop_dir):
                onedrive = os.environ.get("OneDrive")
                if onedrive and os.path.isdir(os.path.join(onedrive, "Desktop")):
                    desktop_dir = os.path.join(onedrive, "Desktop")

            desktop_lnk = os.path.join(desktop_dir, f"{APP_SHORT_NAME}.lnk")
            appdata = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
            start_menu_dir = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")
            start_menu_lnk = os.path.join(start_menu_dir, f"{APP_SHORT_NAME}.lnk")

            if self.desktop_shortcut_var.get() and os.path.isdir(desktop_dir):
                self._set_status("Criando atalho na Área de Trabalho...", 78)
                create_windows_shortcut(
                    target_exe=dest_exe,
                    shortcut_path=desktop_lnk,
                    icon_path=icon_for_shortcut,
                    working_dir=target_dir,
                    description=APP_NAME,
                )

            if self.startmenu_shortcut_var.get() and os.path.isdir(start_menu_dir):
                self._set_status("Criando atalho no Menu Iniciar...", 88)
                create_windows_shortcut(
                    target_exe=dest_exe,
                    shortcut_path=start_menu_lnk,
                    icon_path=icon_for_shortcut,
                    working_dir=target_dir,
                    description=APP_NAME,
                )

            # 4. Cria desinstalador e registra no Windows
            self._set_status("Registrando aplicativo no Windows...", 95)
            uninstaller_bat = create_uninstaller_script(target_dir, desktop_lnk, start_menu_lnk)
            register_uninstaller_in_registry(target_dir, dest_exe, icon_for_shortcut, uninstaller_bat)

            self._set_status("Instalação concluída com sucesso!", 100)
            messagebox.showinfo(
                "Instalação Concluída",
                f"O {APP_NAME} foi instalado com sucesso em:\n{target_dir}",
            )

            should_launch = self.launch_after_var.get()
            self.destroy()

            if should_launch and os.path.isfile(dest_exe):
                clean_env = get_clean_child_env()
                subprocess.Popen(
                    [dest_exe],
                    cwd=target_dir,
                    env=clean_env,
                    close_fds=True,
                )
        except Exception as e:
            self._set_status(f"Erro na instalação: {e}", 0)
            messagebox.showerror(
                "Erro na Instalação",
                f"Não foi possível concluir a instalação:\n{e}\n\n"
                "Verifique se o aplicativo já está aberto e tente novamente.",
            )
            self.btn_install.configure(state="normal")
            self.btn_cancel.configure(state="normal")


if __name__ == "__main__":
    app = InstallerWizardApp()
    app.mainloop()
