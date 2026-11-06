"""
Serviço de Correção Ortográfica Nativa do Windows utilizando a Windows Spell Checking API.
Disponível nativamente no Windows 8, 10 e 11 via COM (spellcheck.h).
Conta com gerenciamento completo de Dicionário Personalizado (adicionar, listar e remover palavras)
persistido no banco de dados SQLite da aplicação e integrado com a API nativa do Windows.
"""

import os
import sys
import logging
from typing import List, Optional, Set
from dataclasses import dataclass

import config
from database.connection import get_connection, get_db
from database.schema import CREATE_CUSTOM_DICTIONARY_TABLE
from utils.date_utils import get_current_timestamp

logger = logging.getLogger(__name__)


@dataclass
class SpellingError:
    """Representa um erro ortográfico identificado pela API do Windows."""
    start: int
    length: int
    word: str
    action: int = 1  # 1 = Obter sugestões


class WindowsSpellCheckService:
    """
    Interface para o corretor ortográfico nativo do sistema operacional Windows.
    Utiliza as interfaces ISpellCheckerFactory, ISpellChecker e ISpellChecker2 registradas no sistema,
    além de persistir o dicionário personalizado no banco SQLite da aplicação.
    """

    def __init__(
        self,
        preferred_languages: Optional[List[str]] = None,
        db_path: Optional[str] = None,
    ):
        self.db_path = db_path or config.DB_PATH
        self._is_available = False
        self._active_language: Optional[str] = None
        self._checker = None
        self._checker2 = None
        self._factory = None
        self._ignored_words: Set[str] = set()
        self._custom_words: Set[str] = set()

        self._ensure_dictionary_table()

        if sys.platform != "win32":
            logger.info("Corretor ortográfico nativo do Windows indisponível: sistema não é Windows.")
            self.reload_custom_dictionary()
            return

        self._languages = preferred_languages or ["pt-BR", "pt-PT", "en-US"]
        self._initialize_com_and_checker()
        self.reload_custom_dictionary()

    def _ensure_dictionary_table(self):
        """Garante que a tabela custom_dictionary exista no banco configurado."""
        try:
            with get_db(self.db_path) as conn:
                conn.execute(CREATE_CUSTOM_DICTIONARY_TABLE)
        except Exception as e:
            logger.debug(f"Aviso ao garantir tabela custom_dictionary: {e}")

    def _initialize_com_and_checker(self):
        try:
            import comtypes
            import comtypes.client
            from comtypes import GUID, IUnknown, COMMETHOD, HRESULT
            from ctypes import c_wchar_p, c_int, c_ubyte, POINTER
            from ctypes.wintypes import BOOL, ULONG, DWORD, LPWSTR, LPCWSTR

            try:
                comtypes.CoInitialize()
            except Exception:
                pass

            # Identificadores oficiais do Windows SDK (spellcheck.h)
            CLSID_SpellCheckerFactory = GUID("{7AB36653-1796-484B-BDFA-E74F1DB7C1DC}")
            IID_ISpellCheckerFactory  = GUID("{8E018A9D-2415-4677-BF08-794EA61F94BB}")
            IID_ISpellChecker         = GUID("{B6FD0B71-E2BC-4653-8D05-F197E412770B}")
            IID_ISpellChecker2        = GUID("{E7ED1C71-87F7-4378-A840-C9200DACEE47}")
            IID_ISpellingError        = GUID("{B7C82D61-FBE8-4B47-9B27-6C0D2E0DE0A3}")
            IID_IEnumSpellingError    = GUID("{803E3BD4-2828-4410-8290-418D1D73C762}")
            IID_IEnumString           = GUID("{00000101-0000-0000-C000-000000000046}")

            class IEnumString(IUnknown):
                _case_insensitive_ = True
                _iid_ = IID_IEnumString
                _methods_ = [
                    COMMETHOD([], HRESULT, "Next",
                              (["in"], ULONG, "celt"),
                              (["out"], POINTER(c_wchar_p), "rgelt"),
                              (["out"], POINTER(ULONG), "pceltFetched")),
                    COMMETHOD([], HRESULT, "Skip", (["in"], ULONG, "celt")),
                    COMMETHOD([], HRESULT, "Reset"),
                    COMMETHOD([], HRESULT, "Clone", (["out"], POINTER(POINTER(IUnknown)), "ppenum")),
                ]

            class ISpellingError(IUnknown):
                _case_insensitive_ = True
                _iid_ = IID_ISpellingError
                _methods_ = [
                    COMMETHOD([], HRESULT, "get_StartIndex", (["out", "retval"], POINTER(ULONG), "value")),
                    COMMETHOD([], HRESULT, "get_Length", (["out", "retval"], POINTER(ULONG), "value")),
                    COMMETHOD([], HRESULT, "get_CorrectiveAction", (["out", "retval"], POINTER(c_int), "value")),
                    COMMETHOD([], HRESULT, "get_Replacement", (["out", "retval"], POINTER(LPWSTR), "value")),
                ]

            class IEnumSpellingError(IUnknown):
                _case_insensitive_ = True
                _iid_ = IID_IEnumSpellingError
                _methods_ = [
                    COMMETHOD([], HRESULT, "Next", (["out", "retval"], POINTER(POINTER(ISpellingError)), "value")),
                ]

            class ISpellChecker(IUnknown):
                _case_insensitive_ = True
                _iid_ = IID_ISpellChecker
                _methods_ = [
                    COMMETHOD([], HRESULT, "get_LanguageTag", (["out", "retval"], POINTER(LPWSTR), "value")),
                    COMMETHOD([], HRESULT, "Check",
                              (["in"], LPCWSTR, "text"),
                              (["out", "retval"], POINTER(POINTER(IEnumSpellingError)), "value")),
                    COMMETHOD([], HRESULT, "Suggest",
                              (["in"], LPCWSTR, "word"),
                              (["out", "retval"], POINTER(POINTER(IEnumString)), "value")),
                    COMMETHOD([], HRESULT, "Add", (["in"], LPCWSTR, "word")),
                    COMMETHOD([], HRESULT, "Ignore", (["in"], LPCWSTR, "word")),
                    COMMETHOD([], HRESULT, "AutoCorrect", (["in"], LPCWSTR, "from"), (["in"], LPCWSTR, "to")),
                    COMMETHOD([], HRESULT, "GetOptionValue", (["in"], LPCWSTR, "optionId"), (["out", "retval"], POINTER(c_ubyte), "value")),
                    COMMETHOD([], HRESULT, "get_OptionIds", (["out", "retval"], POINTER(POINTER(IEnumString)), "value")),
                    COMMETHOD([], HRESULT, "get_Id", (["out", "retval"], POINTER(LPWSTR), "value")),
                    COMMETHOD([], HRESULT, "get_LocalizedName", (["out", "retval"], POINTER(LPWSTR), "value")),
                    COMMETHOD([], HRESULT, "add_SpellCheckerChanged", (["in"], POINTER(IUnknown), "handler"), (["out", "retval"], POINTER(DWORD), "eventCookie")),
                    COMMETHOD([], HRESULT, "remove_SpellCheckerChanged", (["in"], DWORD, "eventCookie")),
                    COMMETHOD([], HRESULT, "GetOptionDescription", (["in"], LPCWSTR, "optionId"), (["out", "retval"], POINTER(POINTER(IUnknown)), "value")),
                    COMMETHOD([], HRESULT, "ComprehensiveCheck", (["in"], LPCWSTR, "text"), (["out", "retval"], POINTER(POINTER(IEnumSpellingError)), "value")),
                ]

            class ISpellChecker2(ISpellChecker):
                _case_insensitive_ = True
                _iid_ = IID_ISpellChecker2
                _methods_ = [
                    COMMETHOD([], HRESULT, "Remove", (["in"], LPCWSTR, "word")),
                ]

            class ISpellCheckerFactory(IUnknown):
                _case_insensitive_ = True
                _iid_ = IID_ISpellCheckerFactory
                _methods_ = [
                    COMMETHOD([], HRESULT, "get_SupportedLanguages", (["out", "retval"], POINTER(POINTER(IUnknown)), "value")),
                    COMMETHOD([], HRESULT, "IsSupported",
                              (["in"], LPCWSTR, "languageTag"),
                              (["out", "retval"], POINTER(BOOL), "value")),
                    COMMETHOD([], HRESULT, "CreateSpellChecker",
                              (["in"], LPCWSTR, "languageTag"),
                              (["out", "retval"], POINTER(POINTER(ISpellChecker)), "value")),
                ]

            self._factory = comtypes.client.CreateObject(CLSID_SpellCheckerFactory, interface=ISpellCheckerFactory)

            # Tenta encontrar o primeiro idioma disponível na ordem de preferência
            for lang in self._languages:
                try:
                    if self._factory.IsSupported(lang):
                        self._checker = self._factory.CreateSpellChecker(lang)
                        try:
                            self._checker2 = self._checker.QueryInterface(ISpellChecker2)
                        except Exception:
                            self._checker2 = None
                        self._active_language = lang
                        self._is_available = True
                        logger.info(f"Corretor ortográfico nativo do Windows iniciado no idioma: {lang}")
                        break
                except Exception as ex:
                    logger.debug(f"Falha ao inicializar idioma {lang}: {ex}")

        except Exception as e:
            logger.warning(f"Não foi possível inicializar a Windows Spell Checking API: {e}")
            self._is_available = False

    @property
    def is_available(self) -> bool:
        """Indica se a API nativa do Windows está operacional."""
        return self._is_available and self._checker is not None

    @property
    def active_language(self) -> Optional[str]:
        """Retorna a tag do idioma ativo no momento (ex: 'pt-BR')."""
        return self._active_language

    # =========================================================================
    # Gerenciamento do Dicionário Personalizado (Banco SQLite + Windows API)
    # =========================================================================

    def _get_windows_dic_path(self) -> Optional[str]:
        """Retorna o caminho do arquivo default.dic do idioma ativo no Windows, se existir."""
        if sys.platform != "win32":
            return None
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        lang = self._active_language or "pt-BR"
        return os.path.join(appdata, "Microsoft", "Spelling", lang, "default.dic")

    def _remove_word_from_windows_dic_file(self, word: str):
        """Remove uma palavra diretamente do arquivo default.dic do Windows, caso esteja lá."""
        dic_path = self._get_windows_dic_path()
        if not dic_path or not os.path.isfile(dic_path):
            return

        target_lower = word.strip().lower()
        for enc in ("utf-16", "utf-8-sig", "utf-8"):
            try:
                with open(dic_path, "r", encoding=enc) as f:
                    lines = f.readlines()
                filtered = [
                    line for line in lines
                    if line.strip().lstrip("\ufeff").lower() != target_lower
                ]
                if len(filtered) != len(lines):
                    with open(dic_path, "w", encoding=enc) as f:
                        f.writelines(filtered)
                return
            except Exception:
                continue

    def reload_custom_dictionary(self) -> List[str]:
        """
        Recarrega a lista de palavras do dicionário personalizado a partir do banco SQLite.
        """
        self._ensure_dictionary_table()
        words = self.list_custom_words()
        self._custom_words = {w.lower() for w in words}
        return words

    def list_custom_words(self) -> List[str]:
        """
        Retorna a lista de todas as palavras adicionadas ao dicionário personalizado,
        ordenadas alfabeticamente.
        """
        self._ensure_dictionary_table()
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT word FROM custom_dictionary ORDER BY word COLLATE NOCASE ASC"
            )
            rows = cursor.fetchall()
            words = [row["word"] for row in rows if row["word"] and row["word"].strip()]
            self._custom_words = {w.lower() for w in words}
            return words
        except Exception as e:
            logger.debug(f"Erro ao listar palavras do dicionário: {e}")
            return sorted(self._custom_words)
        finally:
            conn.close()

    def add_to_dictionary(self, word: str) -> bool:
        """
        Adiciona a palavra ao dicionário personalizado do corretor ortográfico.
        Ela passa a ser persistida no banco SQLite e não será marcada como erro.
        """
        if not word or not word.strip():
            return False

        clean_word = word.strip()
        self._ensure_dictionary_table()
        now = get_current_timestamp()

        try:
            with get_db(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO custom_dictionary (word, created_at)
                    VALUES (?, ?)
                    ON CONFLICT(word) DO UPDATE SET word = excluded.word
                    """,
                    (clean_word, now),
                )
        except Exception as e:
            logger.warning(f"Erro ao salvar '{clean_word}' na tabela custom_dictionary: {e}")
            return False

        self._custom_words.add(clean_word.lower())
        return True

    def remove_from_dictionary(self, word: str) -> bool:
        """
        Remove uma palavra do dicionário personalizado (do banco SQLite e da API/arquivo do Windows).
        """
        if not word or not word.strip():
            return False

        clean_word = word.strip()
        lower_word = clean_word.lower()
        self._ensure_dictionary_table()

        removed_db = False
        try:
            with get_db(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM custom_dictionary WHERE word = ? COLLATE NOCASE",
                    (clean_word,),
                )
                removed_db = cursor.rowcount > 0
        except Exception as e:
            logger.warning(f"Erro ao remover '{clean_word}' do banco de dados: {e}")

        self._custom_words.discard(lower_word)
        self._ignored_words.discard(lower_word)

        # Caso a palavra também tenha sido adicionada anteriormente ao dicionário global do Windows,
        # remove via ISpellChecker2.Remove e do arquivo default.dic
        if self.is_available and self._checker2 is not None:
            for variant in {clean_word, lower_word, clean_word.upper(), clean_word.capitalize()}:
                try:
                    self._checker2.Remove(variant)
                except Exception:
                    pass

        self._remove_word_from_windows_dic_file(clean_word)

        return removed_db or True

    # =========================================================================
    # Verificação Ortográfica e Sugestões
    # =========================================================================

    def check_text(self, text: str) -> List[SpellingError]:
        """
        Analisa um texto e retorna todos os erros ortográficos com posição e comprimento.
        """
        if not self.is_available or not text or not text.strip():
            return []

        errors: List[SpellingError] = []
        try:
            enum_errors = self._checker.Check(text)
            if not enum_errors:
                return []

            while True:
                try:
                    err = enum_errors.Next()
                    if not err:
                        break
                    start = err.get_StartIndex()
                    length = err.get_Length()
                    action = err.get_CorrectiveAction()

                    # Garante limites válidos dentro do texto original
                    if start < len(text) and (start + length) <= len(text):
                        word = text[start : start + length]
                        w_lower = word.lower()
                        # Ignora palavras na lista da sessão ou no dicionário personalizado
                        if w_lower not in self._ignored_words and w_lower not in self._custom_words:
                            errors.append(SpellingError(start=start, length=length, word=word, action=action))
                except Exception:
                    break

        except Exception as e:
            logger.debug(f"Erro ao verificar texto com Windows Spell Checker: {e}")

        return errors

    def get_suggestions(self, word: str, limit: int = 6) -> List[str]:
        """
        Retorna sugestões de correção ortográfica sugeridas pelo Windows para uma palavra.
        """
        if not self.is_available or not word or not word.strip():
            return []

        suggestions: List[str] = []
        try:
            enum_str = self._checker.Suggest(word.strip())
            if not enum_str:
                return []

            while len(suggestions) < limit:
                try:
                    sug, count = enum_str.Next(1)
                    if not count or not sug:
                        break
                    if sug not in suggestions:
                        suggestions.append(sug)
                except Exception:
                    break

        except Exception as e:
            logger.debug(f"Erro ao obter sugestões para '{word}': {e}")

        return suggestions

    def ignore_word(self, word: str) -> bool:
        """
        Ignora a palavra na sessão de verificação atual.
        """
        if not word:
            return False

        self._ignored_words.add(word.strip().lower())
        if self.is_available:
            try:
                self._checker.Ignore(word.strip())
            except Exception:
                pass
        return True
