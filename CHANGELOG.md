# Changelog

Todas as alterações notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning (SemVer)](https://semver.org/lang/pt-BR/).

---

## [1.8.1] - 2026-11-27
### Fixed
- **Corrigida lentidão e travamento na abertura do Diário do Dia, troca de dias (Anterior / Hoje / Próximo) e colagem de textos (`Ctrl+V`):**
  - Substituído o loop caractere-a-caractere (`O(N)`) em `utils/rich_text.py` (`_recompute_composite_fonts` e `_range_fully_has_tag`) por algoritmo sweep-line de intervalos (`O(K log K)`) com inserção em lote e cache da fonte base aplicada, reduzindo a troca de dias com formatação rica em até **15x**.
  - Otimizado o destaque de sintaxe XML/SQL em `utils/syntax_highlighter.py` com `OffsetMapper` (`O(log L)` em Python puro), aplicação de tags em lote, cache de configuração por tema, passagem única para notas com XML+SQL combinados, busca binária em trechos protegidos e destaque incremental (`auto_highlight_range`) apenas nas linhas afetadas durante a colagem (`Ctrl+V`), reduzindo as chamadas Tcl/Tk em até **90x**.
  - Movida a verificação ortográfica automática do Windows (`services/spellcheck_service.py`) para worker assíncrono em thread STA dedicada (`check_text_async`) com descarte automático de checagens obsoletas e aplicação de marcações em lote, eliminando congelamentos da interface durante abertura, troca de dia e colagem.
  - Removidos reflows síncronos (`update_idletasks`) durante a colagem e salvamento automático silencioso no **Diário do Dia** (`views/diary_view.py`) e em **Notas & Pastas** (`views/notes_view.py`), além de ignorar teclas puras de navegação em `_on_text_modified` e otimizar snapshots de `EditorHistoryManager` (`utils/editor_history.py`).
  - Adicionado cache inteligente da instância de `DiaryView` no `MainWindow` (`views/main_window.py`) para evitar reconstruir todos os botões e barras ao alternar entre o Diário e outros menus, mantendo recarga automática da data e posicionamento do cursor ao final do texto.

---

## [1.8.0] - 2026-11-26
### Added
- **Gerenciador Completo de Tarefas no menu Agendamentos** (estilo Microsoft To Do integrado ao Diário):
  - Novas tabelas SQLite dedicadas (`tarefas`, `historico_tarefas`, `lembretes_tarefas`) com integridade referencial (`ON DELETE CASCADE`) e migração automática segura e idempotente dos agendamentos legados (`schedules`), mantendo compatibilidade total com backup e restauração.
  - Cadastro e edição completos (`views/components/task_dialogs.py` — `TaskFormDialog`) com título, descrição inicial, data de início, data prevista, horário opcional, prioridade (**Baixa**, **Média**, **Alta**, **Urgente**), status (**Pendente**, **Em andamento**, **Concluída**, **Cancelada**), categoria opcional e configuração detalhada de lembretes.
  - Histórico cronológico imutável de andamento (`services/task_history_service.py`) preservando todas as observações e mudanças de status com data, horário e status no momento, sem sobrescrever registros anteriores.
  - Conclusão automática com registro de data/hora (`completed_at`) e reabertura preservando integralmente todo o histórico.
  - Tela principal em layout Split-View (`views/schedules_view.py`) com indicadores clicáveis (*Pendentes*, *Em andamento*, *Concluídas*, *Atrasadas*, *Para hoje*), 8 abas de filtro, destaque de tarefas do dia, pesquisa por título/descrição/conteúdo do histórico, filtros por período/status/prioridade, ordenação por 4 critérios, alteração rápida de status na listagem e painel completo de detalhes (*Informações gerais*, *Ações* e *Andamento*).
  - Sistema modular de lembretes vinculados às tarefas (`services/task_reminder_service.py`) com suporte a data/horário personalizados (com repetição), aviso no dia do vencimento, aviso antecipado, lembrete diário de tarefa atrasada, prevenção contra notificações repetidas e protocolo Toast (`dailynotes://task/open` e `dailynotes://task/snooze`).
- **Importação de documentos Word (`.doc` e `.docx`)**: novo leitor universal (`utils/document_reader.py`) integrado à tela de Importação, Notas & Pastas e Diário, com suporte a OOXML (`.docx`), OLE2 binário (`.doc` via Word COM + extrator nativo em Python puro), RTF, Word 2003 XML plano, HTML/MHTML e texto puro, preservando parágrafos, tabelas e codificações e ignorando arquivos temporários (`~$`).
- **Atalhos produtivos de edição (`utils/editor_shortcuts.py`)** no Diário do Dia, Notas & Pastas e janela de leitura/edição:
  - **`F5`**: insere a data e hora atual (`DD/MM/AAAA HH:MM`) na posição do cursor com suporte completo a `Ctrl+Z`.
  - **`Ctrl + Space`**: completa a frase/sugestão do corretor ou corrige automaticamente erro ortográfico sob o cursor ou ao final do texto, integrado ao histórico de desfazer.

### Changed
- **Performance da Pesquisa Avançada**: adicionados índices virtuais **SQLite FTS5 `trigram`** (`diaries_fts_trigram` e `notes_fts_trigram`) com backfill automático, consultas otimizadas em C nativo para substrings sem acento, cards leves e paginação progressiva na interface (`views/search_view.py`), reduzindo drasticamente o tempo de pesquisa em grandes bases.

### Fixed
- Corrigida a importação de arquivos com extensão `.docx` que internamente possuem formato RTF, OLE2 binário, Word XML plano, HTML/MHTML ou texto simples (eliminando o erro `File is not a zip file`), passando a identificar o formato real pela assinatura de bytes do arquivo.

---

## [1.7.0] - 2026-11-24
### Added
- Suporte e botão **Itálico (`I` / `Ctrl+I`)** no **Diário do Dia**, em **Notas & Pastas** e na janela de leitura/edição (`DiaryNoteReaderDialog`), combinável com Fonte, Tamanho, Negrito, Sublinhado e Riscado com persistência em `formatting_json`.
- Gerenciador unificado de histórico (`utils/editor_history.py` — `EditorHistoryManager`) com snapshots completos de texto, formatação rica, coloração XML/SQL, cursor e seleção.

### Fixed
- Corrigido o **Desfazer (`Ctrl+Z` / `↩️`)** e **Refazer (`Ctrl+Y` / `Ctrl+Shift+Z` / `↪️`)** para desfazer e refazer passo a passo todas as ações dos botões da barra (troca de fonte, tamanho da fonte, negrito, itálico, sublinhado, riscado, MAIÚSCULO/minúsculo, formatação/coloração XML e SQL, limpar cores e nova anotação) além de qualquer edição de texto (digitação, colagem, recorte e substituição ortográfica) no Diário, Notas & Pastas e janela de leitura/edição.
- Corrigido o aumento indevido no tamanho da fonte ao aplicar **Negrito (`B`)** (e Itálico), alinhando o cálculo da fonte em pixels negativos escalados pelo DPI (`-round(size * scaling)`) com o padrão interno do `CTkFont`.
- Garantido o retorno imediato do foco ao editor após seleção em dropdowns (`CTkComboBox`) de fonte/tamanho e ações da barra para que `Ctrl+Z` responda de imediato.

---

## [1.6.0] - 2026-11-22
### Added
- Formatação rica de texto no **Diário do Dia**, em **Notas & Pastas** e na janela de leitura/edição (`DiaryNoteReaderDialog`): seletores de **Fonte** e **Tamanho**, além de botões combináveis de **Negrito (`B` / `Ctrl+B`)**, **Sublinhado (`U` / `Ctrl+U`)** e **Riscado (`S`)**, aplicáveis tanto sobre texto selecionado quanto globalmente/durante a digitação contínua.
- Motor dedicado de formatação (`utils/rich_text.py`) com persistência em JSON (`formatting_json`) nas tabelas `diaries` e `notes` (com migração incremental automática para bancos antigos), preservando integralmente o texto puro para busca FTS5, busca sem acentos, destaque `F3`, corretor ortográfico e exportações.
- Renderização da formatação rica salva também na pré-visualização diária da tela **Histórico & Calendário**.
- Botão **✨ Novidades** no rodapé da barra lateral com modal dedicado (`WhatsNewDialog`) para consultar offline o histórico completo de novidades de cada versão diretamente a partir do `CHANGELOG.md`, sem precisar abrir a tela de verificação de atualização.

### Changed
- `ResponsiveToolbar` ampliada para aceitar widgets arbitrários (`add_widget`) e estilos de fonte sublinhado/riscado nos botões da barra de formatação.
- Detecção de alterações não salvas e salvamento automático nos editores atualizados para considerar mudanças exclusivas de formatação (fonte, tamanho, negrito, sublinhado ou riscado).
- Empacotamento PyInstaller (`diario_anotacoes.spec` e `diario_anotacoes_onedir.spec`) atualizado para incluir `CHANGELOG.md` no executável final.

---

## [1.5.0] - 2026-11-19
### Added
- Pesquisa Avançada ampliada com seletor de escopo (**Diário e Pastas**, **Somente Diário** e **Pastas e Arquivos**), exibindo selo visual identificando a origem (**📔 Diário** ou **📁 Pasta & Arquivos** com caminho completo da pasta e título da nota) e botão para abrir diretamente na pasta correspondente.
- Destaque automático insensível a maiúsculas e acentuação de todas as palavras-chave pesquisadas e navegação por teclado com **`F3`** (próxima ocorrência) e **`Shift+F3`** (ocorrência anterior) tanto na janela de visualização do Diário quanto nas notas abertas de Pastas & Arquivos, com indicador de progresso `🔍 X/N (F3 ▸)`.
- Botão rápido **🔄 Trocar Usuário** na barra lateral com modal dedicado (`SwitchUserDialog`) para alternar entre contas ativas sem voltar à tela de login.
- Botão **◀ / ▶** no menu lateral para recolher a barra apenas em ícones (com tooltips) e ampliar a área útil da tela aberta à direita, além de barra de rolagem fina (`6 px`), suave e auto-oculta quando a altura da janela for reduzida.
- Estrutura profissional de versionamento com arquivo `VERSION` como fonte única de verdade (integrada ao `version.py` e empacotamento PyInstaller), `CHANGELOG.md` padronizado e regra permanente de processo em `.agent/rules/versioning.md`.

### Changed
- Exportação CSV da Pesquisa Avançada atualizada para incluir as colunas **Origem** (`Diário` ou `Pasta e Arquivos`) e **Título / Pasta**.
- Ícone do menu **Notas & Pastas** ajustado para `📁` para renderização nítida e centralizada no modo recolhido.

### Fixed
- Corrigido o corte/achatamento do botão **OK** e demais botões inferiores em diálogos modais (`MessageDialog` e `UnsavedChangesDialog`) com ajuste automático de altura ao conteúdo real (`_fit_modal_height`).

---

## [1.4.1] - 2026-11-16
### Fixed
- Corrigido o erro `[WinError 740]` ao abrir o instalador durante a atualização automática a partir de versões anteriores (`v1.3.1`), passando a solicitar elevação UAC sob demanda apenas quando a pasta de destino exigir privilégios administrativos (ex.: `C:\Program Files\DiarioAnotacoes`).
- Corrigido o cálculo de quebra de linha (`wraplength`) no card de segurança da janela de atualização considerando a escala DPI do monitor (`125%`/`150%`).

---

## [1.4.0] - 2026-11-16
### Added
- Identidade própria (`DailyNotes - Diário de Anotações`) e ícone do aplicativo nas notificações nativas do Windows via registro de `AppUserModelId`.
- Botões nativos de ação direta (**Abrir Agendamento** e **Adiar 10 min**) nas notificações Toast do Windows com suporte a protocolo customizado `dailynotes://`.
- Pré-visualização completa da anotação de um dia específico na tela **Histórico & Calendário** ao clicar em uma data do calendário, com botão para retornar à listagem completa do mês.
- Tooltips flutuantes exibindo o nome completo das ações ao passar o mouse sobre todos os ícones das barras de ferramentas no **Diário do Dia** e em **Notas & Pastas**.

### Changed
- Pasta padrão do assistente de instalação alterada para `C:\Program Files\DiarioAnotacoes`, com preservação automática do local real de instalação durante atualizações (`--install-dir`).
- Fallback automático do diretório de dados (`DATA_DIR`) para `%LOCALAPPDATA%\DiarioAnotacoes\data` quando instalado em diretórios protegidos pelo Windows.
- Ao retornar ao **Diário do Dia** a partir de outros menus, o cursor e a rolagem vão automaticamente para o final do texto quando já houver conteúdo registrado.

### Fixed
- Corrigido o posicionamento do cursor após colagem (`Ctrl+V` / `Windows+V`) para permanecer exatamente no final do texto colado, em vez de ir para o final do arquivo.

---

## [1.3.1] - 2026-11-13
### Fixed
- Corrigido o erro `[SSL: CERTIFICATE_VERIFY_FAILED]` na verificação e download de atualizações via GitHub Releases no executável empacotado, carregando certificados dos repositórios `ROOT` e `CA` do Windows com fallback SSL automático.

---

## [1.3.0] - 2026-11-12
### Added
- Novo menu **Agendamentos** com cadastro de lembretes por data, horário, prioridade e repetição, além de verificador periódico e notificações nativas do Windows.
- Suporte à importação e exportação de arquivos nos formatos `.xml`, `.bat` e `.sql` no menu **Notas & Pastas** e na tela de **Importação**.
- Centralização inteligente das janelas e diálogos modais considerando múltiplos monitores e a área útil da tela principal.

### Changed
- Pastas no menu **Notas & Pastas** passam a iniciar minimizadas/recolhidas por padrão, exibindo suas notas apenas quando clicadas.

---

## [1.2.0] - 2026-11-08
### Added
- Barras de ferramentas responsivas (`ResponsiveToolbar`) com menu de transbordamento `»` quando a janela estiver estreita.
- Painel de configuração do Backup Automático agendado com retenção rotativa semanal (7 dias).

### Changed
- Botões de ação e formatação convertidos para símbolos compactos no **Diário do Dia** e em **Notas & Pastas**.

### Fixed
- Corrigida a visibilidade dos botões **Salvar Novo Usuário** e **Cancelar** no modal do Gerenciador de Usuários em diferentes resoluções e escalas DPI.

---

## [1.1.0] - 2026-11-07
### Added
- Controle de versão centralizado e verificação automática de novas releases no GitHub com download do instalador e preservação integral do banco de dados local (`diario.db`).
- Suporte a desfazer/refazer (`Ctrl+Z` / `Ctrl+Y`), formatação e destaque colorido para XML e SQL, e módulo de **Notas & Pastas**.

---

## [1.0.0] - 2026-11-06
### Added
- Versão inicial completa do **Diário de Anotações Inteligente (DailyNotes)** com SQLite, autenticação Argon2, pesquisa avançada FTS5, calendário interativo, importação/exportação de arquivos `.txt`, corretor ortográfico nativo do Windows e instalador Windows.
