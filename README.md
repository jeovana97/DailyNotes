# Diário de Anotações Inteligente (DailyNotes) 📓

**Versão atual:** `1.8.1`

O **Diário de Anotações Inteligente (DailyNotes)** é um sistema desktop completo para Windows, desenvolvido em **Python** e **CustomTkinter**, projetado para centralizar, organizar e consultar tanto **anotações diárias por data** quanto **notas técnicas/permanentes organizadas em pastas e subpastas**.

Substitui dezenas de arquivos `.txt` soltos por uma base de dados **SQLite** rápida, segura e indexada, oferecendo pesquisa instantânea insensível a maiúsculas e acentuação, corretor ortográfico nativo do Windows com dicionário gerenciável, backup automático agendado e assistente de instalação próprio para Windows.

---

## 🌟 Visão Geral do Sistema e Funcionalidades

### 1. 📝 Diário do Dia
- **Registro Diário Organizado:** Uma anotação centralizada para cada data do calendário por usuário, evitando arquivos duplicados.
- **Navegação Rápida:** Botões **◀ Anterior**, **📅 Hoje** e **Próximo ▶** para alternar rapidamente entre os dias.
- **Salvamento Manual e Automático:** Botão **💾 Salvar (Ctrl+S)** e chave de **Salvamento Automático** após segundos de inatividade, com indicador de status em tempo real (`🟢 Salvo`, `⚪ Alterações não salvas *`).
- **Formatação de Texto (Fonte, Tamanho, Negrito, Itálico, Sublinhado, Riscado, MAIÚSCULO, minúsculo, XML e SQL com Cores):**
  - **Fonte, Tamanho e Estilos (`B`, `I`, `U`, `S`):** Selecione a família da fonte, o tamanho e combine **Negrito (`Ctrl+B`)**, **Itálico (`Ctrl+I`)**, **Sublinhado (`Ctrl+U`)** e **Riscado** sobre trechos selecionados ou no texto inteiro, com persistência automática sem afetar a pesquisa FTS5 ou a exportação, e suporte completo a **Desfazer (`Ctrl+Z`) / Refazer (`Ctrl+Y`)** para todas as edições e botões de ação.
  - **🔠 MAIÚSCULO** e **🔡 minúsculo:** Selecione qualquer trecho no texto (ou no título da nota) e converta instantaneamente para letras maiúsculas ou minúsculas.
  - **</> XML (Cor)** e **🗄️ SQL (Cor):** Formata (indenta tags XML ou padroniza cláusulas/comandos SQL) e aplica **destaque de sintaxe colorido** (tags, atributos, valores, comandos `SELECT`, `FROM`, `WHERE`, `JOIN`, funções, strings e comentários).
- **Colagem Inteligente:** Ao colar qualquer texto (`Ctrl+V` ou menu do botão direito **📄 Colar**), o cursor é posicionado automaticamente no final do texto e a tela rola para exibir a última informação colada.
- **Corretor Ortográfico Nativo do Windows (pt-BR) e Atalhos Rápidos (`Ctrl+Space` e `F5`):**
  - Sublinha em vermelho palavras não reconhecidas em tempo real.
  - Ao clicar com o **botão direito** sobre uma palavra sublinhada, exibe sugestões de correção imediatas do Windows, opção de **➕ Adicionar ao Dicionário** ou **👁️ Ignorar**.
  - **`Ctrl + Space`:** Completa a sugestão do corretor ou corrige automaticamente palavras com erro ortográfico sob o cursor ou ao final do texto (compatível com `Ctrl+Z`).
  - **`F5`:** Insere automaticamente a data e hora atual (`DD/MM/AAAA HH:MM`) na posição do cursor.

### 2. 🗂️ Notas & Pastas (Notas sem Vínculo com Datas)
- **Organização Livre por Assunto:** Ideal para guardar scripts SQL, senhas, leiautes XML, procedimentos, links úteis e anotações de referência permanente.
- **Pastas e Subpastas Ilimitadas:** Crie pastas principais e subpastas aninhadas, renomeie ou exclua pastas facilmente.
- **Formatação Rica, Cores XML/SQL, Conversão de Caixa e Atalhos:** Barra de ferramentas integrada com seletores de **Fonte** e **Tamanho**, botões **Negrito (`B`)**, **Itálico (`I`)**, **Sublinhado (`U`)**, **Riscado (`S`)**, **🔠 MAIÚSCULO**, **🔡 minúsculo**, **</> XML (Cor)**, **🗄️ SQL (Cor)** e **🎨 Limpar Cor**, atalhos **`F5`** (data/hora) e **`Ctrl+Space`** (corretor/autocompletar), histórico unificado de **Desfazer (`Ctrl+Z`) / Refazer (`Ctrl+Y`)** e detecção automática de cores ao abrir notas com XML ou SQL.
- **Importação Direta para Pastas:** Botão **📥 Importar** para importar arquivos `.txt`, `.doc`, `.docx`, `.sql`, `.xml` e `.bat` com qualquer nome (sem precisar de formato de data), perguntando em qual pasta deseja colocar a nota ou permitindo criar uma nova pasta na hora.
- **Mover Nota de Pasta:** Mova qualquer nota entre pastas pelo seletor no topo do editor, pelo botão **📂 Mover** ou pelo menu de opções (`⋯` / clique direito na nota).
- **Pesquisa Exclusiva por Nome da Nota:** Possui barra de busca própria no topo da árvore lateral que filtra instantaneamente pelo título da nota (mantendo essas notas isoladas da Pesquisa Avançada do Diário).

### 3. ✅ Agendamentos & Tarefas (Gerenciador Estilo Microsoft To Do)
- **Cadastro Completo de Tarefas:** Cadastre atividades com **Título**, **Descrição inicial**, **Data de início**, **Data prevista**, **Horário (opcional)**, **Prioridade** (Baixa, Média, Alta, Urgente), **Status** (Pendente, Em andamento, Concluída, Cancelada), **Categoria** e **Lembretes**.
- **Histórico Cronológico de Andamento:** Registre atualizações e observações ao longo da execução dentro de cada tarefa, preservando todos os registros anteriores com data, horário e status no momento. Ao concluir, registra automaticamente a data/hora de conclusão e permite reabrir mantendo todo o histórico.
- **Painel de Produtividade e Visão Split-View:** Indicadores clicáveis (*Pendentes*, *Em andamento*, *Concluídas*, *Atrasadas*, *Para hoje*), **8 abas de visualização**, destaque das tarefas do dia, pesquisa por título/descrição/andamento, filtros por período/status/prioridade, ordenação por 4 critérios, alteração rápida de status na listagem e painel lateral de detalhes completo.
- **Notificações Nativas do Windows (Toast) Vinculadas às Tarefas:** Suporte a lembrete em data/horário específicos (com repetição), aviso no dia do vencimento, aviso antecipado e lembrete diário de tarefa atrasada (sem repetições indevidas), com botões de ação direta para abrir a tarefa ou adiar o aviso.

### 4. 🔍 Pesquisa Avançada de Alta Performance (Diário, Pastas e Arquivos)
- **Busca Instantânea Unificada com SQLite FTS5 Trigram:** Localiza rapidamente qualquer palavra, trecho ou substring no **Diário**, em **Pastas e Arquivos** ou em ambos simultaneamente com paginação progressiva, ignorando diferenças entre maiúsculas/minúsculas e acentuação (ex: buscar `sessao` encontra `sessão`).
- **Identificação de Origem e Navegação `F3`:** Cada resultado exibe claramente se pertence ao **📔 Diário** ou a **📁 Pasta & Arquivos** (com caminho da pasta e título). Ao abrir o documento, todas as palavras-chave ficam destacadas e é possível navegar entre as ocorrências usando **`F3`** (próxima) e **`Shift+F3`** (anterior).
- **Filtros Combinados:** Filtre por **Escopo**, **Data Inicial**, **Data Final**, **Data Exata**, **Ordenação** (mais recentes ou mais antigas) e **Usuário** (para administradores com permissão).
- **Janela de Visualização (Somente Leitura) com Opção de Edição:**
  - Ao clicar em **📖 Abrir Anotação (Leitura)** ou dar duplo clique em um resultado do diário, o sistema abre uma janela dedicada em modo **🔒 Somente Leitura** com os termos destacados e navegação `F3`; para resultados de pasta, abre diretamente na pasta correspondente em **Notas & Pastas** também com destaque e `F3`.
  - Caso deseje alterar a anotação do diário, basta clicar em **✏️ Editar Nota** na própria janela ou em **📝 Abrir no Diário do Dia**.
- **Exportação para Excel (CSV):** Exporte a lista de resultados filtrados para um arquivo `.csv` (UTF-8 com BOM), incluindo a origem (`Diário` ou `Pasta e Arquivos`) e o caminho/título.

### 5. 📅 Histórico & Calendário
- **Calendário Mensal Interativo:** Destaca visualmente todos os dias do mês que possuem anotações registradas.
- **Navegação Direta por Data:** Clique no cabeçalho do mês/ano no calendário para digitar qualquer data (`DD/MM/AAAA`, `MM/AAAA` ou ano) e ir diretamente ao período desejado.
- **Leitura Protegida:** Clicar em **📖 Abrir** em qualquer dia listado abre a janela dedicada em modo **🔒 Somente Leitura**, contando com o botão **✏️ Editar Nota** caso queira editar sem perder a navegação do calendário.

### 6. 📥 Importar Arquivos (`.txt`, `.doc`, `.docx`, `.sql`, `.xml`, `.bat`)
- **Suporte Multi-formato sem Exigir Data no Nome:** Importa um ou vários arquivos (ou uma pasta inteira do computador) nos formatos **`.txt`**, **`.doc`**, **`.docx`** (OOXML, OLE2, RTF, Word XML, HTML/MHTML), **`.sql`**, **`.xml`** e **`.bat`**, usando o nome do arquivo como título da nota e detectando automaticamente formato e codificação (`UTF-8`, `ANSI/Windows-1252`, `ISO-8859-1`).
- **Escolha ou Criação de Pasta na Hora:** Ao iniciar a importação, o sistema pergunta em qual pasta deseja colocar a(s) nota(s) ou permite **criar uma nova pasta/subpasta** imediatamente na mesma janela.
- **Tratamento de Conflitos:** Escolha entre **Ignorar**, **Substituir** ou **Mesclar (Anexar)** caso já exista uma nota com o mesmo nome na pasta escolhida.
- **Histórico do Último TXT Importado:** Exibe no topo da tela um card destacando o **📄 Último TXT Importado** (nome do arquivo, pasta de destino e data/hora da importação), com botão rápido **🗂️ Abrir em Notas & Pastas**.

### 7. 💾 Exportar, Backup Automático e Dicionário Ortográfico
- **🔤 Dicionário do Corretor Ortográfico:**
  - Visualize todas as palavras personalizadas adicionadas ao corretor ortográfico.
  - Adicione novas palavras (siglas, termos técnicos, comandos) ou remova palavras cadastradas a qualquer momento.
- **🛡️ Cópia de Segurança Manual e Automática (`.db`):**
  - **Backup Manual:** Gera a qualquer momento uma cópia íntegra do banco SQLite (`conn.backup()`).
  - **⏰ Configuração de Backup Automático:**
    - Ative o agendamento automático escolhendo o **📁 Local para salvar o arquivo**, a **📅 Data do Backup** e o **🕒 Horário do Backup (`HH:MM`)**, com opção de **Repetir diariamente neste horário**.
    - O sistema monitora o agendamento em segundo plano e gera automaticamente o arquivo `.db` na pasta configurada, exibindo o registro do último backup gerado.
- **🔄 Restauração Segura:** Valida o arquivo `.db`/`.bak` selecionado e cria uma cópia preventiva de segurança antes de restaurar.
- **📂 Exportação em Lote para TXT:** Exporta todas as anotações do diário para uma pasta em arquivos individuais `DD MM AAAA.txt`.

### 8. 🎨 Tema Persistente, Novidades e Controle de Usuários
- **Modo Escuro e Modo Claro Persistentes:** A escolha entre **Modo Escuro** e **Modo Claro** no rodapé da barra lateral é salva automaticamente no perfil do usuário e restaurada sempre que ele fizer login novamente.
- **✨ Novidades Offline:** Botão dedicado na barra lateral para consultar o histórico completo de novidades e melhorias de cada versão diretamente no aplicativo, sem necessidade de internet.
- **Gerenciamento de Usuários (Admin):** Cadastro de novos usuários, ativação/desativação de contas, redefinição de senhas (criptografia **Argon2id**), troca rápida de usuário sem sair da sessão e permissão para visualizar diários de outros usuários.

---

## 📖 Como Usar o Sistema

### Opção 1: Instalando em Qualquer Computador Windows (Sem precisar de Python)
1. Gere o pacote instalador (veja a seção *Como Gerar o Pacote Instalador* abaixo) ou localize o arquivo `dist/DiarioAnotacoes_Setup.exe`.
2. Copie o arquivo **`DiarioAnotacoes_Setup.exe`** para a máquina desejada e dê dois cliques.
3. No **Assistente de Instalação**:
   - Confirme ou escolha a pasta de instalação (padrão: `%LOCALAPPDATA%\Programs\DiarioAnotacoes`).
   - Marque as opções para criar atalhos na **Área de Trabalho** e no **Menu Iniciar**.
   - Clique em **🚀 Instalar Agora**.
4. Ao abrir o aplicativo pela primeira vez, cadastre o **Administrador Inicial** informando nome completo, usuário e senha.

### Opção 2: Executando a partir do Código-Fonte (Python)

#### 1. Pré-requisitos
- **Windows 10 ou Windows 11**
- **Python 3.10+** instalado

#### 2. Instalar Dependências
No terminal (PowerShell ou CMD) na pasta do projeto:
```bash
pip install -r requirements.txt
```

#### 3. Iniciar a Aplicação
```bash
python main.py
```

---

## 📦 Como Gerar o Pacote Instalador do Windows (`.exe`)

Para compilar tanto o **Pacote Instalador do Windows** quanto o **Executável Portátil**, execute:

```bash
python build_exe.py
```

Ao final do processo, serão gerados na pasta `dist/`:
- **`dist/DiarioAnotacoes_Setup.exe`** (e `dist/Instalador_DiarioAnotacoes_Setup.exe`): Instalador gráfico completo para instalar o sistema em outra máquina Windows.
- **`dist/DiarioAnotacoes.exe`**: Versão portátil standalone de arquivo único.

---

## 🧪 Executando os Testes Automatizados

Para rodar toda a suíte de testes unitários e de integração:

```bash
python -m unittest discover -s tests
```

---

## 🏷️ Controle de Versão

Este projeto segue o padrão **Semantic Versioning (`MAJOR.MINOR.PATCH`)** e **Conventional Commits**:

- **`VERSION`**: Armazena a versão atual do aplicativo como fonte única de verdade.
- **`CHANGELOG.md`**: Mantém o histórico completo das versões por data e categoria (`Added`, `Changed`, `Fixed`, `Removed`, `Security`).
- **`version.py`**: Lê dinamicamente o arquivo `VERSION` para exibição na interface e verificação de atualizações via GitHub Releases.

---

## 📂 Estrutura de Diretórios

```text
DAILYNotes/
├── VERSION                         # Versão atual do aplicativo (SemVer)
├── CHANGELOG.md                    # Histórico completo de versões e alterações
├── version.py                      # Leitor centralizado de versão e URLs do GitHub
├── main.py                         # Ponto de entrada principal da aplicação
├── config.py                       # Configurações gerais, caminhos e paleta de temas
├── build_exe.py                    # Gerador automatizado do executável e do instalador Windows
├── installer_wizard.py             # Assistente gráfico de instalação (Setup Wizard) para Windows
├── diario_anotacoes.spec           # Especificação PyInstaller (executável portátil)
├── diario_anotacoes_onedir.spec    # Especificação PyInstaller (pacote base do instalador)
├── instalador_setup.spec           # Especificação PyInstaller (instalador Setup.exe)
├── assets_gen.py                   # Utilitário de preparação de ícones (.ico e .png)
├── assets/                         # Ícones oficiais da aplicação
├── database/                       # Conexão SQLite, schema DDL, FTS5 e migrações
├── models/                         # Modelos de domínio (User, DiaryEntry, Note, NoteFolder)
├── services/                       # Regras de negócio (Auth, Diário, Notas, Busca, Importação, Backup, Ortografia)
├── views/                          # Telas CustomTkinter e componentes visuais (Calendário, Diálogos, Leitor)
├── utils/                          # Utilitários de datas, textos/acentos e validações
└── tests/                          # Testes automatizados unitários e de integração
```
