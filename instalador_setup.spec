# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

datas = []

# Empacota o pacote ZIP da aplicação compilada em modo --onedir (sem aninhar .exe onefile dentro de onefile)
payload_zip = os.path.join('build', 'app_payload.zip')
if os.path.exists(payload_zip):
    datas.append((payload_zip, 'payload'))

# Inclui a pasta de ícones/assets para exibir na interface do instalador e copiar na instalação
if os.path.exists('assets'):
    datas.append(('assets', 'assets'))

a = Analysis(
    ['installer_wizard.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'winreg',
        'zipfile',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PIL',
        'customtkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Desativa compressão zlib de CArchive no bootloader do instalador para evitar erro -3 (Z_DATA_ERROR)
uncompressed_cdict = {
    'EXTENSION': False,
    'BINARY': False,
    'DATA': False,
    'EXECUTABLE': False,
    'PYSOURCE': False,
    'PYMODULE': False,
    'SPLASH': False,
    'PYZ': False,
    'SYMLINK': False,
}

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Instalador_DiarioAnotacoes_Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Interface gráfica do assistente de instalação (sem console)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    cdict=uncompressed_cdict,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)
