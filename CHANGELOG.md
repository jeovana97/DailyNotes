# Changelog

Todas as alterações notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning (SemVer)](https://semver.org/lang/pt-BR/).

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
