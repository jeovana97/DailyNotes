# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Coleta os arquivos de dados e temas do CustomTkinter
datas = collect_data_files('customtkinter')

# Inclui os ícones da pasta assets se existirem
if os.path.exists('assets'):
    datas.append(('assets', 'assets'))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        'darkdetect',
        'argon2',
        'argon2.low_level',
        '_cffi_backend',
        'comtypes',
        'comtypes.client',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PIL._avif',
        'PIL._webp',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Desativa compressão zlib no CArchive para binários/extensões (.pyd/.dll),
# evitando qualquer falha "decompression resulted in return code -3!" no bootloader do Windows.
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
    name='DiarioAnotacoes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Sem janela de prompt preta (aplicação GUI pura)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    cdict=uncompressed_cdict,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)
