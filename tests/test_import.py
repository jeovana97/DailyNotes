import json
import os
import struct
import tempfile
import unittest
import zipfile
from database.migrations import init_db
from services.authentication_service import AuthenticationService
from services.diary_service import DiaryService
from services.import_service import ImportService, ConflictResolution
from utils.document_reader import read_ole2_doc_native, read_doc_file


class TestImportService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_import.db")
        init_db(self.db_path)
        self.auth_service = AuthenticationService(db_path=self.db_path)
        self.diary_service = DiaryService(db_path=self.db_path)
        self.import_service = ImportService(diary_service=self.diary_service)

        self.user, _ = self.auth_service.create_initial_admin("user_import", "Usuário Importador", "senha1234")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_single_utf8_file(self):
        # Cria arquivo no formato padrão "01 10 2026.txt"
        file_path = os.path.join(self.temp_dir.name, "01 10 2026.txt")
        content = "Reunião de início de mês. Metas traçadas com acentuação e pontuação: ação, coração, café."
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        res = self.import_service.import_file(file_path, self.user.id)
        self.assertEqual(res["status"], "imported")
        self.assertEqual(res["date_iso"], "2026-10-01")

        entry = self.diary_service.get_entry_by_date(self.user.id, "2026-10-01")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.content, content)

    def test_import_windows_1252_encoding(self):
        # Cria arquivo em Windows-1252 (ANSI)
        file_path = os.path.join(self.temp_dir.name, "02 10 2026.txt")
        content = "Anotação gravada em ANSI: Atenção às configurações de produção!"
        with open(file_path, "w", encoding="cp1252") as f:
            f.write(content)

        res = self.import_service.import_file(file_path, self.user.id)
        self.assertEqual(res["status"], "imported")

        entry = self.diary_service.get_entry_by_date(self.user.id, "2026-10-02")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.content, content)

    def test_conflict_resolutions(self):
        date_iso = "2026-10-03"
        # Cria anotação prévia
        self.diary_service.save_entry(self.user.id, date_iso, "Conteúdo original pré-existente.")

        file_path = os.path.join(self.temp_dir.name, "03 10 2026.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("Novo conteúdo importado do arquivo.")

        # 1. Modo SKIP (ignorar)
        res_skip = self.import_service.import_file(
            file_path, self.user.id, conflict_resolution=ConflictResolution.SKIP
        )
        self.assertEqual(res_skip["status"], "skipped")
        entry = self.diary_service.get_entry_by_date(self.user.id, date_iso)
        self.assertEqual(entry.content, "Conteúdo original pré-existente.")

        # 2. Modo MERGE (mesclar)
        res_merge = self.import_service.import_file(
            file_path, self.user.id, conflict_resolution=ConflictResolution.MERGE
        )
        self.assertEqual(res_merge["status"], "imported")
        entry_merged = self.diary_service.get_entry_by_date(self.user.id, date_iso)
        self.assertIn("Conteúdo original pré-existente.", entry_merged.content)
        self.assertIn("Novo conteúdo importado do arquivo.", entry_merged.content)

        # 3. Modo REPLACE (substituir)
        res_replace = self.import_service.import_file(
            file_path, self.user.id, conflict_resolution=ConflictResolution.REPLACE
        )
        self.assertEqual(res_replace["status"], "imported")
        entry_replaced = self.diary_service.get_entry_by_date(self.user.id, date_iso)
        self.assertEqual(entry_replaced.content, "Novo conteúdo importado do arquivo.")

    def test_batch_folder_import(self):
        folder = os.path.join(self.temp_dir.name, "batch_notes")
        os.makedirs(folder, exist_ok=True)

        # Cria 3 arquivos válidos e 1 inválido
        with open(os.path.join(folder, "10 10 2026.txt"), "w", encoding="utf-8") as f:
            f.write("Nota dia 10")
        with open(os.path.join(folder, "11 10 2026.txt"), "w", encoding="utf-8") as f:
            f.write("Nota dia 11")
        with open(os.path.join(folder, "12 10 2026.txt"), "w", encoding="utf-8") as f:
            f.write("Nota dia 12")
        with open(os.path.join(folder, "arquivo_sem_data.txt"), "w", encoding="utf-8") as f:
            f.write("Ignorado")

        report = self.import_service.import_folder(folder, self.user.id)
        self.assertEqual(report["total"], 4)
        self.assertEqual(report["imported"], 3)
        self.assertEqual(report["errors"], 1)

        # Verifica registro do último TXT importado
        last_txt = self.import_service.get_last_imported_txt(self.user.id)
        self.assertIsNotNone(last_txt)
        self.assertEqual(last_txt["filename"], "12 10 2026.txt")
        self.assertEqual(last_txt["entry_date"], "2026-10-12")
        self.assertEqual(last_txt["date_br"], "12/10/2026")

    def test_import_notes_into_folders_without_date_format(self):
        # Cria uma pasta de destino
        folder_obj = self.import_service.note_service.create_folder(self.user.id, "Consultas SQL e XML")

        # Cria arquivos TXT com nomes livres (sem formato de data)
        sql_file = os.path.join(self.temp_dir.name, "consulta_clientes_ativos.txt")
        with open(sql_file, "w", encoding="utf-8") as f:
            f.write("select id, nome from clientes where ativo = 1;")

        xml_file = os.path.join(self.temp_dir.name, "ERRO XML NFE.txt")
        with open(xml_file, "w", encoding="utf-8") as f:
            f.write("<nfeProc><NFe><infNFe Id='NFe1'><ide><cUF>35</cUF></ide></infNFe></NFe></nfeProc>")

        res1 = self.import_service.import_note_file(
            file_path=sql_file,
            user_id=self.user.id,
            folder_id=folder_obj.id,
        )
        self.assertEqual(res1["status"], "imported")
        self.assertEqual(res1["folder_id"], folder_obj.id)
        self.assertIsNotNone(res1["note_id"])

        res2 = self.import_service.import_note_file(
            file_path=xml_file,
            user_id=self.user.id,
            folder_id=folder_obj.id,
        )
        self.assertEqual(res2["status"], "imported")

        # Verifica se as notas foram salvas dentro da pasta escolhida
        notes_in_folder = self.import_service.note_service.list_notes(
            self.user.id, folder_id=folder_obj.id, all_notes=False
        )
        self.assertEqual(len(notes_in_folder), 2)
        titles = {n.title for n in notes_in_folder}
        self.assertEqual(titles, {"consulta_clientes_ativos", "ERRO XML NFE"})

        # Verifica o último TXT importado apontando para a pasta
        last_info = self.import_service.get_last_imported_txt(self.user.id)
        self.assertIsNotNone(last_info)
        self.assertEqual(last_info["target_type"], "note")
        self.assertEqual(last_info["filename"], "ERRO XML NFE.txt")
        self.assertEqual(last_info["folder_id"], folder_obj.id)
        self.assertEqual(last_info["folder_name"], "Consultas SQL e XML")

    def test_import_folder_to_notes_batch(self):
        src_dir = os.path.join(self.temp_dir.name, "notas_avulsas")
        os.makedirs(src_dir, exist_ok=True)

        with open(os.path.join(src_dir, "SENHAS CIS.txt"), "w", encoding="utf-8") as f:
            f.write("admin / 1234")
        with open(os.path.join(src_dir, "SESSAO PRESA.txt"), "w", encoding="utf-8") as f:
            f.write("ALTER SYSTEM KILL SESSION;")

        dest_folder = self.import_service.note_service.create_folder(self.user.id, "Importadas")
        report = self.import_service.import_folder_to_notes(
            folder_path=src_dir,
            user_id=self.user.id,
            target_folder_id=dest_folder.id,
        )
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["imported"], 2)
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["target_folder_name"], "Importadas")

    def test_import_notes_sql_xml_bat_formats(self):
        folder_dev = self.import_service.note_service.create_folder(self.user.id, "Scripts e Layouts")

        # Cria arquivos nos formatos solicitados: .sql, .xml, .bat
        sql_path = os.path.join(self.temp_dir.name, "procedure_atualiza.sql")
        with open(sql_path, "w", encoding="utf-8") as f:
            f.write("CREATE OR REPLACE PROCEDURE atualiza_estoque IS BEGIN NULL; END;")

        xml_path = os.path.join(self.temp_dir.name, "layout_pedido.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write("<pedido id='100'><item cod='1' qtd='2'/></pedido>")

        bat_path = os.path.join(self.temp_dir.name, "executa_backup.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write("@echo off\r\necho Iniciando rotina...\r\npause")

        # Importa individualmente
        r_sql = self.import_service.import_note_file(sql_path, self.user.id, folder_id=folder_dev.id)
        self.assertEqual(r_sql["status"], "imported")

        r_xml = self.import_service.import_note_file(xml_path, self.user.id, folder_id=folder_dev.id)
        self.assertEqual(r_xml["status"], "imported")

        r_bat = self.import_service.import_note_file(bat_path, self.user.id, folder_id=folder_dev.id)
        self.assertEqual(r_bat["status"], "imported")

        # Valida notas criadas na pasta
        notes = self.import_service.note_service.list_notes(self.user.id, folder_id=folder_dev.id, all_notes=False)
        self.assertEqual(len(notes), 3)
        titles = {n.title for n in notes}
        self.assertEqual(titles, {"procedure_atualiza", "layout_pedido", "executa_backup"})

        # Testa importação de pasta com lote de arquivos mistos (.sql, .xml, .bat, .txt)
        batch_dir = os.path.join(self.temp_dir.name, "batch_mix")
        os.makedirs(batch_dir, exist_ok=True)
        with open(os.path.join(batch_dir, "script1.sql"), "w", encoding="utf-8") as f:
            f.write("SELECT * FROM dual;")
        with open(os.path.join(batch_dir, "doc.xml"), "w", encoding="utf-8") as f:
            f.write("<doc/>")
        with open(os.path.join(batch_dir, "run.bat"), "w", encoding="utf-8") as f:
            f.write("exit /b 0")
        with open(os.path.join(batch_dir, "nota.txt"), "w", encoding="utf-8") as f:
            f.write("Anotacao normal")
        with open(os.path.join(batch_dir, "ignorado.bin"), "w", encoding="utf-8") as f:
            f.write("ignorar")

        folder_batch = self.import_service.note_service.create_folder(self.user.id, "Lote Misto")
        report = self.import_service.import_folder_to_notes(batch_dir, self.user.id, target_folder_id=folder_batch.id)
        self.assertEqual(report["total"], 4)
        self.assertEqual(report["imported"], 4)
        self.assertEqual(report["errors"], 0)

    @staticmethod
    def _create_sample_docx(path: str):
        """Gera um arquivo .docx (OOXML) válido com parágrafos, tabela e estilos ricos."""
        doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:rPr><w:b/><w:i/><w:rFonts w:ascii="Arial"/><w:sz w:val="30"/></w:rPr>
        <w:t>Relatório de Emissão</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:r><w:t xml:space="preserve">Status: </w:t></w:r>
      <w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>Concluído</w:t></w:r>
      <w:r><w:t xml:space="preserve"> </w:t></w:r>
      <w:r><w:rPr><w:strike/></w:rPr><w:t>Pendente</w:t></w:r>
    </w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Código</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Descrição</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>8492</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Nota Fiscal Eletrônica</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>"""
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("word/document.xml", doc_xml.encode("utf-8"))

    @staticmethod
    def _create_sample_ole2_doc(path: str, text_cp1252: str, text_utf16: str):
        """
        Gera um arquivo binário .doc (OLE2/CFBF + FIB + 1Table CLX Piece Table) real
        contendo uma peça comprimida cp1252 e outra peça Unicode UTF-16LE.
        """
        sector_size = 512

        # 1. Monta stream WordDocument (>= 4096 bytes para ficar na FAT normal)
        cp1252_bytes = text_cp1252.encode("cp1252")
        utf16_bytes = text_utf16.encode("utf-16-le")
        text1_off = 0x200
        text2_off = (text1_off + len(cp1252_bytes) + 1) & ~1  # alinhado em 2 bytes

        word_doc = bytearray(max(4096, text2_off + len(utf16_bytes) + 64))
        word_doc[text1_off : text1_off + len(cp1252_bytes)] = cp1252_bytes
        word_doc[text2_off : text2_off + len(utf16_bytes)] = utf16_bytes

        # 2. Monta stream 1Table com estrutura CLX (clxt=0x02 + pcdt_len + 3 CPs + 2 Pcds)
        len1 = len(text_cp1252)
        len2 = len(text_utf16)
        total_chars = len1 + len2

        # Pcd1: comprimido cp1252 (bit 0x40000000 ligado, fc = byte_off * 2)
        fc1 = 0x40000000 | (text1_off * 2)
        pcd1 = struct.pack("<HIH", 0, fc1, 0)
        # Pcd2: UTF-16LE (bit 0x40000000 desligado, fc = byte_off)
        fc2 = text2_off
        pcd2 = struct.pack("<HIH", 0, fc2, 0)

        plc_pcd = struct.pack("<3I", 0, len1, total_chars) + pcd1 + pcd2
        clx = bytes([0x02]) + struct.pack("<I", len(plc_pcd)) + plc_pcd

        table_stream = bytearray(4096)
        table_stream[: len(clx)] = clx

        # Preenche campos FIB em WordDocument:
        # 0x000A flags = 0x0200 (usa 1Table, sem criptografia)
        struct.pack_into("<H", word_doc, 0x000A, 0x0200)
        # 0x004C ccpText = total_chars
        struct.pack_into("<I", word_doc, 0x004C, total_chars)
        # 0x01A2 fcClx = 0, 0x01A6 lcbClx = len(clx)
        struct.pack_into("<I", word_doc, 0x01A2, 0)
        struct.pack_into("<I", word_doc, 0x01A6, len(clx))

        # 3. Empacota como Compound File Binary Format (OLE2)
        def _pad_sectors(b: bytes) -> bytes:
            rem = len(b) % sector_size
            return b + (b"\x00" * (sector_size - rem) if rem else b"")

        wd_padded = _pad_sectors(bytes(word_doc))
        tb_padded = _pad_sectors(bytes(table_stream))
        wd_secs = len(wd_padded) // sector_size
        tb_secs = len(tb_padded) // sector_size

        # Layout dos setores:
        # 0: FAT
        # 1: Directory
        # 2 .. 2+wd_secs-1: WordDocument
        # 2+wd_secs .. 2+wd_secs+tb_secs-1: 1Table
        fat_sec = 0
        dir_sec = 1
        wd_start = 2
        tb_start = wd_start + wd_secs

        FATSECT = 0xFFFFFFFD
        ENDOFCHAIN = 0xFFFFFFFE
        FREESECT = 0xFFFFFFFF

        fat_entries = [FREESECT] * (sector_size // 4)
        fat_entries[fat_sec] = FATSECT
        fat_entries[dir_sec] = ENDOFCHAIN
        for s in range(wd_secs):
            fat_entries[wd_start + s] = (wd_start + s + 1) if s + 1 < wd_secs else ENDOFCHAIN
        for s in range(tb_secs):
            fat_entries[tb_start + s] = (tb_start + s + 1) if s + 1 < tb_secs else ENDOFCHAIN
        fat_sector_bytes = struct.pack(f"<{sector_size // 4}I", *fat_entries)

        def _dir_entry(name: str, obj_type: int, start_s: int, size: int) -> bytes:
            entry = bytearray(128)
            if name:
                enc = (name + "\x00").encode("utf-16-le")
                entry[: len(enc)] = enc
                struct.pack_into("<H", entry, 64, len(enc))
            entry[66] = obj_type
            entry[67] = 1  # black node
            struct.pack_into("<3I", entry, 68, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
            struct.pack_into("<I", entry, 116, start_s)
            struct.pack_into("<I", entry, 120, size)
            return bytes(entry)

        dir_sector = bytearray(sector_size)
        dir_sector[0:128] = _dir_entry("Root Entry", 5, ENDOFCHAIN, 0)
        dir_sector[128:256] = _dir_entry("WordDocument", 2, wd_start, len(word_doc))
        dir_sector[256:384] = _dir_entry("1Table", 2, tb_start, len(table_stream))

        header = bytearray(512)
        header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        struct.pack_into("<H", header, 0x18, 0x003E)  # minor version
        struct.pack_into("<H", header, 0x1A, 0x0003)  # major version 3
        struct.pack_into("<H", header, 0x1C, 0xFFFE)  # little-endian BOM
        struct.pack_into("<H", header, 0x1E, 9)       # sector shift 512
        struct.pack_into("<H", header, 0x20, 6)       # mini sector shift 64
        struct.pack_into("<I", header, 0x2C, 1)       # 1 FAT sector
        struct.pack_into("<I", header, 0x30, dir_sec) # first dir sector
        struct.pack_into("<I", header, 0x38, 0x1000)  # mini stream cutoff 4096
        struct.pack_into("<I", header, 0x3C, ENDOFCHAIN)
        struct.pack_into("<I", header, 0x44, ENDOFCHAIN)
        struct.pack_into("<I", header, 0x48, 0)
        difat = [FREESECT] * 109
        difat[0] = fat_sec
        struct.pack_into("<109I", header, 0x4C, *difat)

        with open(path, "wb") as f:
            f.write(header)
            f.write(fat_sector_bytes)
            f.write(dir_sector)
            f.write(wd_padded)
            f.write(tb_padded)

    def test_import_docx_preserves_text_tables_and_formatting(self):
        folder_word = self.import_service.note_service.create_folder(self.user.id, "Documentos Word")
        docx_path = os.path.join(self.temp_dir.name, "Manual_NFSe.docx")
        self._create_sample_docx(docx_path)

        res = self.import_service.import_note_file(docx_path, self.user.id, folder_id=folder_word.id)
        self.assertEqual(res["status"], "imported")
        note = self.import_service.note_service.get_note(self.user.id, res["note_id"])
        self.assertIsNotNone(note)
        self.assertEqual(note.title, "Manual_NFSe")
        self.assertIn("Relatório de Emissão", note.content)
        self.assertIn("Status: Concluído Pendente", note.content)
        self.assertIn("8492 | Nota Fiscal Eletrônica", note.content)

        # Valida preservação da formatação rica (.docx -> formatting_json)
        self.assertTrue(note.formatting_json)
        fmt = json.loads(note.formatting_json)
        tags = {sp["tag"] for sp in fmt["spans"]}
        self.assertIn("bold", tags)
        self.assertIn("italic", tags)
        self.assertIn("underline", tags)
        self.assertIn("overstrike", tags)
        self.assertIn("family:Arial", tags)

        # Também funciona importando .docx datado para o Diário
        dated_docx = os.path.join(self.temp_dir.name, "26 11 2026.docx")
        self._create_sample_docx(dated_docx)
        res_diary = self.import_service.import_file(dated_docx, self.user.id)
        self.assertEqual(res_diary["status"], "imported")
        entry = self.diary_service.get_entry_by_date(self.user.id, "2026-11-26")
        self.assertIn("Relatório de Emissão", entry.content)
        self.assertTrue(entry.formatting_json)

    def test_import_doc_ole2_rtf_html_and_batch(self):
        folder_docs = self.import_service.note_service.create_folder(self.user.id, "Word Legado")

        # 1. Binário OLE2 verdadeiro (Word 97-2003) — valida parser Python puro (sem depender de Word)
        ole2_path = os.path.join(self.temp_dir.name, "procedimento_legado.doc")
        self._create_sample_ole2_doc(
            ole2_path,
            "Atenção: emissão da nota fiscal!\r",
            "Resumo técnico com \x13 HYPERLINK http://x \x14Link Visível\x15 e conclusão.",
        )
        extracted_native = read_ole2_doc_native(ole2_path)
        self.assertIn("Atenção: emissão da nota fiscal!", extracted_native)
        self.assertIn("Link Visível", extracted_native)
        self.assertNotIn("HYPERLINK", extracted_native)

        txt_no_com, _ = read_doc_file(ole2_path, use_word_com=False)
        self.assertIn("Atenção: emissão da nota fiscal!", txt_no_com)

        # 2. RTF salvo como .doc
        rtf_path = os.path.join(self.temp_dir.name, "relatorio_rtf.doc")
        rtf_content = (
            r"{\rtf1\ansi\ansicpg1252{\fonttbl{\f0 Arial;}}"
            r"Relat\'f3rio de cota\'e7\'e3o\par Linha 2 com \u233?xito.}"
        )
        with open(rtf_path, "w", encoding="latin1") as f:
            f.write(rtf_content)

        # 3. HTML salvo como .doc
        html_path = os.path.join(self.temp_dir.name, "exportacao_erp.doc")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write("<html><head><title>Ignore</title></head><body><h1>Aten&ccedil;&atilde;o</h1><p>Pedido aprovado.</p></body></html>")

        # 4. DOCX renomeado como .doc
        renamed_doc = os.path.join(self.temp_dir.name, "renomeado.doc")
        self._create_sample_docx(renamed_doc)

        for fpath, expected in [
            (rtf_path, "Relatório de cotação"),
            (html_path, "Atenção"),
            (renamed_doc, "Relatório de Emissão"),
        ]:
            r = self.import_service.import_note_file(fpath, self.user.id, folder_id=folder_docs.id)
            self.assertEqual(r["status"], "imported", f"Falha ao importar {fpath}: {r}")
            n = self.import_service.note_service.get_note(self.user.id, r["note_id"])
            self.assertIn(expected, n.content)

        # 5. Lote de pasta contendo .doc, .docx e .txt mistos
        mix_dir = os.path.join(self.temp_dir.name, "mix_word")
        os.makedirs(mix_dir, exist_ok=True)
        self._create_sample_docx(os.path.join(mix_dir, "ata.docx"))
        with open(os.path.join(mix_dir, "memo.doc"), "w", encoding="latin1") as f:
            f.write(rtf_content)
        with open(os.path.join(mix_dir, "notas.txt"), "w", encoding="utf-8") as f:
            f.write("Texto simples")

        folder_mix = self.import_service.note_service.create_folder(self.user.id, "Lote Word")
        rep = self.import_service.import_folder_to_notes(mix_dir, self.user.id, target_folder_id=folder_mix.id)
        self.assertEqual(rep["total"], 3)
        self.assertEqual(rep["imported"], 3)
        self.assertEqual(rep["errors"], 0)

    def test_import_non_zip_docx_variants_without_badzip_error(self):
        """
        Garante que arquivos com extensão .docx que internamente são RTF, OLE2, Word XML plano,
        HTML, texto puro (UTF-8/UTF-16) ou vazios sejam importados sem erro 'File is not a zip file'.
        Também garante que arquivos temporários de lock (~$*.docx) sejam ignorados no lote.
        """
        folder_chamados = self.import_service.note_service.create_folder(self.user.id, "Chamados DOCX")

        # 1. RTF salvo com extensão .docx
        rtf_docx = os.path.join(self.temp_dir.name, "36289 - ERRO DE VALIDACAO.docx")
        with open(rtf_docx, "w", encoding="latin1") as f:
            f.write(r"{\rtf1\ansi{\fonttbl{\f0 Arial;}}Erro de valida\'e7\'e3o de servi\'e7o.}")

        # 2. Binário OLE2 salvo com extensão .docx
        ole2_docx = os.path.join(self.temp_dir.name, "36301 - BOLECODE ITAU.docx")
        self._create_sample_ole2_doc(ole2_docx, "Erro no registro de Bolecode Itaú.\r", "Ajuste concluído.")

        # 3. Word 2003 XML plano salvo com extensão .docx
        wordml_docx = os.path.join(self.temp_dir.name, "36302 - FLAG FINANCEIRA.docx")
        wordml = """<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Word.Document"?>
<w:wordDocument xmlns:w="http://schemas.microsoft.com/office/word/2003/wordml">
  <w:body>
    <w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Criar flag análise financeira</w:t></w:r></w:p>
  </w:body>
</w:wordDocument>"""
        with open(wordml_docx, "w", encoding="utf-8") as f:
            f.write(wordml)

        # 4. HTML salvo com extensão .docx
        html_docx = os.path.join(self.temp_dir.name, "36318 - TOKEN PEDIDO.docx")
        with open(html_docx, "w", encoding="utf-8") as f:
            f.write("<html><body><p>Baixar pedido ao informar o token.</p></body></html>")

        # 5. Texto puro UTF-8 e UTF-16 salvo com extensão .docx
        txt_docx = os.path.join(self.temp_dir.name, "36319 - TEXTO PURO.docx")
        with open(txt_docx, "w", encoding="utf-8") as f:
            f.write("Anotação em texto simples salva como docx.")

        utf16_docx = os.path.join(self.temp_dir.name, "36320 - TEXTO UTF16.docx")
        with open(utf16_docx, "w", encoding="utf-16") as f:
            f.write("Anotação UTF-16 com acentuação.")

        # 6. Arquivo vazio de 0 bytes .docx -> ignorado (skipped), não erro
        empty_docx = os.path.join(self.temp_dir.name, "vazio.docx")
        with open(empty_docx, "wb") as f:
            pass

        for path, expected in [
            (rtf_docx, "Erro de validação de serviço."),
            (wordml_docx, "Criar flag análise financeira"),
            (html_docx, "Baixar pedido ao informar o token."),
            (txt_docx, "Anotação em texto simples"),
            (utf16_docx, "Anotação UTF-16 com acentuação."),
        ]:
            r = self.import_service.import_note_file(path, self.user.id, folder_id=folder_chamados.id)
            self.assertEqual(r["status"], "imported", f"Falhou em {path}: {r}")
            note = self.import_service.note_service.get_note(self.user.id, r["note_id"])
            self.assertIn(expected, note.content)

        # Testa OLE2 salvo como .docx diretamente pelo parser nativo (sem depender de Word COM)
        ole2_txt, _ = read_doc_file(ole2_docx, use_word_com=False)
        self.assertIn("Erro no registro de Bolecode Itaú.", ole2_txt)
        self.assertIn("Ajuste concluído.", ole2_txt)

        # Arquivo vazio -> skipped sem erro
        r_empty = self.import_service.import_note_file(empty_docx, self.user.id, folder_id=folder_chamados.id)
        self.assertEqual(r_empty["status"], "skipped")

        # Testa que lock temporário '~$arquivo.docx' é ignorado na importação de pasta
        lock_dir = os.path.join(self.temp_dir.name, "dir_with_lock")
        os.makedirs(lock_dir, exist_ok=True)
        with open(os.path.join(lock_dir, "~$36289.docx"), "wb") as f:
            f.write(b"\x00\x01lock_temporario_word")
        with open(os.path.join(lock_dir, "valido.docx"), "w", encoding="latin1") as f:
            f.write(r"{\rtf1\ansi Conteudo valido}")

        folder_lock = self.import_service.note_service.create_folder(self.user.id, "Sem Lock")
        rep_lock = self.import_service.import_folder_to_notes(lock_dir, self.user.id, target_folder_id=folder_lock.id)
        self.assertEqual(rep_lock["total"], 1)
        self.assertEqual(rep_lock["imported"], 1)
        self.assertEqual(rep_lock["errors"], 0)


if __name__ == "__main__":
    unittest.main()
