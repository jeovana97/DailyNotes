import os
import shutil
import subprocess
import sys
import zipfile


def create_app_payload_zip(app_dir: str, output_zip: str):
    """Compacta a pasta --onedir do aplicativo em um arquivo ZIP verificado para embutir no instalador."""
    os.makedirs(os.path.dirname(output_zip), exist_ok=True)
    if os.path.exists(output_zip):
        os.remove(output_zip)

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, _, files in os.walk(app_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, app_dir)
                zf.write(abs_path, rel_path)

    # Verifica integridade CRC de todos os arquivos no ZIP
    with zipfile.ZipFile(output_zip, "r") as zf:
        bad_file = zf.testzip()
        if bad_file is not None:
            raise RuntimeError(f"Arquivo corrompido detectado no payload ZIP: {bad_file}")


def build():
    print("=" * 70)
    print("  Diário de Anotações Inteligente - Gerador de Pacote Instalador")
    print("=" * 70)

    # 1. Garante que os ícones estão criados/atualizados
    print("[1/5] Atualizando ícones da aplicação...")
    try:
        import assets_gen
        assets_gen.generate_app_icon()
    except Exception as e:
        print(f"Aviso: não foi possível gerar ícone: {e}")

    # 2. Compila a versão --onedir (para o instalador extrair sem depender de %TEMP%/_MEI)
    print("[2/5] Compilando pacote da aplicação para o instalador (modo --onedir)...")
    cmd_onedir = [sys.executable, "-m", "PyInstaller", "--clean", "-y", "diario_anotacoes_onedir.spec"]
    res_onedir = subprocess.run(cmd_onedir)
    if res_onedir.returncode != 0:
        print("\n[ERRO] Falha ao compilar o pacote base da aplicação.")
        sys.exit(res_onedir.returncode)

    onedir_path = os.path.join("dist", "DiarioAnotacoes_App")
    if not os.path.isdir(onedir_path):
        print(f"\n[ERRO] Diretório esperado não encontrado: {onedir_path}")
        sys.exit(1)

    payload_zip = os.path.join("build", "app_payload.zip")
    print("      Compactando e verificando integridade CRC32 do payload...")
    create_app_payload_zip(onedir_path, payload_zip)

    # 3. Executa PyInstaller para empacotar o Assistente de Instalação
    print("[3/5] Gerando pacote instalador do Windows (Instalador_DiarioAnotacoes_Setup.exe)...")
    cmd_installer = [sys.executable, "-m", "PyInstaller", "--clean", "-y", "instalador_setup.spec"]
    result_installer = subprocess.run(cmd_installer)
    if result_installer.returncode != 0:
        print("\n[ERRO] Falha ao compilar o pacote instalador do Windows.")
        sys.exit(result_installer.returncode)

    # 4. Compila também o executável portátil standalone sem compressão CArchive
    print("[4/5] Compilando executável portátil standalone (DiarioAnotacoes.exe)...")
    cmd_app = [sys.executable, "-m", "PyInstaller", "--clean", "-y", "diario_anotacoes.spec"]
    result_app = subprocess.run(cmd_app)
    if result_app.returncode != 0:
        print("\n[ERRO] Falha ao compilar o executável portátil.")
        sys.exit(result_app.returncode)

    # Remove pasta intermediária DiarioAnotacoes_App de dist/ para manter dist/ limpa
    if os.path.isdir(onedir_path):
        shutil.rmtree(onedir_path, ignore_errors=True)

    setup_path = os.path.join("dist", "Instalador_DiarioAnotacoes_Setup.exe")
    setup_short_path = os.path.join("dist", "DiarioAnotacoes_Setup.exe")
    exe_path = os.path.join("dist", "DiarioAnotacoes.exe")

    # Mantém ambos os nomes do instalador atualizados em dist/
    if os.path.exists(setup_path):
        shutil.copy2(setup_path, setup_short_path)

    # Remove arquivos .rar antigos de builds anteriores para evitar uso acidental de versão antiga
    for old_rar in ("DiarioAnotacoes_Setup.rar", "DiarioAnotacoes.rar"):
        old_rar_path = os.path.join("dist", old_rar)
        if os.path.exists(old_rar_path):
            try:
                os.remove(old_rar_path)
            except Exception:
                pass

    print("\n" + "=" * 70)
    print("[5/5] CONCLUÍDO COM SUCESSO!")
    if os.path.exists(setup_path):
        setup_mb = os.path.getsize(setup_path) / (1024 * 1024)
        print(f"  -> Pacote Instalador 1: {os.path.abspath(setup_path)} ({setup_mb:.2f} MB)")
    if os.path.exists(setup_short_path):
        setup2_mb = os.path.getsize(setup_short_path) / (1024 * 1024)
        print(f"  -> Pacote Instalador 2: {os.path.abspath(setup_short_path)} ({setup2_mb:.2f} MB)")
    if os.path.exists(exe_path):
        app_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"  -> Aplicativo Portátil: {os.path.abspath(exe_path)} ({app_mb:.2f} MB)")
    print("=" * 70)


if __name__ == "__main__":
    build()
