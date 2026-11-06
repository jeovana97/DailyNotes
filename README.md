# Diário de Anotações Inteligente (DailyNotes) 📓

O **Diário de Anotações Inteligente (DailyNotes)** é um sistema desktop completo para Windows, desenvolvido em **Python** e **CustomTkinter**, projetado para centralizar, organizar e consultar tanto **anotações diárias por data** quanto **notas técnicas/permanentes organizadas em pastas e subpastas**.

Substitui dezenas de arquivos `.txt` soltos por uma base de dados **SQLite** rápida, segura e indexada, oferecendo pesquisa instantânea insensível a maiúsculas e acentuação, corretor ortográfico nativo do Windows com dicionário gerenciável, backup automático agendado e assistente de instalação próprio para Windows.

---

## 🌟 Visão Geral do Sistema e Funcionalidades

### 1. 📝 Diário do Dia
- **Registro Diário Organizado:** Uma anotação centralizada para cada data do calendário por usuário, evitando arquivos duplicados.
- **Navegação Rápida:** Botões **◀ Anterior**, **📅 Hoje** e **Próximo ▶** para alternar rapidamente entre os dias.
- **Salvamento Manual e Automático:** Botão **💾 Salvar (Ctrl+S)** e chave de **Salvamento Automático** após segundos de inatividade, com indicador de status em tempo real (`🟢 Salvo`, `⚪ Alterações não salvas *`).
- **Formatação de Texto (MAIÚSCULO, minúsculo, XML e SQL com Cores):**
  - **🔠 MAIÚSCULO** e **🔡 minúsculo:** Selecione qualquer trecho no texto (ou no título da nota) e converta instantaneamente para letras maiúsculas ou minúsculas.
  - **</> XML (Cor)** e **🗄️ SQL (Cor):** Formata (indenta tags XML ou padroniza cláusulas/comandos SQL) e aplica **destaque de sintaxe colorido** (tags, atributos, valores, comandos `SELECT`, `FROM`, `WHERE`, `JOIN`, funções, strings e comentários).
- **Colagem Inteligente:** Ao colar qualquer texto (`Ctrl+V` ou menu do botão direito **📄 Colar**), o cursor é posicionado automaticamente no final do texto e a tela rola para exibir a última informação colada.
- **Corretor Ortográfico Nativo do Windows (pt-BR):**
  - Sublinha em vermelho palavras não reconhecidas em tempo real.
  - Ao clicar com o **botão direito** sobre uma palavra sublinhada, exibe sugestões de correção imediatas do Windows, opção de **➕ Adicionar ao Dicionário** ou **👁️ Ignorar**.

### 2. 🗂️ Notas & Pastas (Notas sem Vínculo com Datas)
- **Organização Livre por Assunto:** Ideal para guardar scripts SQL, senhas, leiautes XML, procedimentos, links úteis e anotações de referência permanente.
- **Pastas e Subpastas Ilimitadas:** Crie pastas principais e subpastas aninhadas, renomeie ou exclua pastas facilmente.
- **Formatação Colorida XML/SQL e Conversão de Caixa:** Barra de ferramentas integrada com botões **🔠 MAIÚSCULO**, **🔡 minúsculo**, **</> XML (Cor)**, **🗄️ SQL (Cor)** e **🎨 Limpar Cor**, além de detecção automática de cores ao abrir notas com XML ou SQL.
- **Importação Direta para Pastas:** Botão **📥 Importar TXT** para importar arquivos `.txt` com qualquer nome (sem precisar de formato de data), perguntando em qual pasta deseja colocar a nota ou permitindo criar uma nova pasta na hora.
- **Mover Nota de Pasta:** Mova qualquer nota entre pastas pelo seletor no topo do editor, pelo botão **📂 Mover** ou pelo menu de opções (`⋯` / clique direito na nota).
- **Pesquisa Exclusiva por Nome da Nota:** Possui barra de busca própria no topo da árvore lateral que filtra instantaneamente pelo título da nota (mantendo essas notas isoladas da Pesquisa Avançada do Diário).

### 3. 🔍 Pesquisa Avançada no Diário
- **Busca Instantânea (FTS5 + Normalização):** Localiza qualquer palavra ou expressão nas anotações do diário, ignorando diferenças entre maiúsculas/minúsculas e acentuação (ex: buscar `sessao` encontra `sessão`).
- **Filtros Combinados:** Filtre por **Data Inicial**, **Data Final**, **Data Exata**, **Ordenação** (mais recentes ou mais antigas) e **Usuário** (para administradores com permissão).
- **Janela de Visualização (Somente Leitura) com Opção de Edição:**
  - Ao clicar em **📖 Abrir Anotação (Leitura)** ou dar duplo clique em um resultado, o sistema **não sai da tela de pesquisa**: abre uma janela dedicada em modo **🔒 Somente Leitura** com os termos pesquisados destacados no texto.
  - Caso deseje alterar a anotação, basta clicar no botão **✏️ Editar Nota** na própria janela (habilitando o botão **💾 Salvar Alterações**) ou clicar em **📝 Abrir no Diário do Dia**.
- **Exportação para Excel (CSV):** Exporte a lista de resultados filtrados para um arquivo `.csv` (UTF-8 com BOM).

### 4. 📅 Histórico & Calendário
- **Calendário Mensal Interativo:** Destaca visualmente todos os dias do mês que possuem anotações registradas.
- **Navegação Direta por Data:** Clique no cabeçalho do mês/ano no calendário para digitar qualquer data (`DD/MM/AAAA`, `MM/AAAA` ou ano) e ir diretamente ao período desejado.
- **Leitura Protegida:** Clicar em **📖 Abrir** em qualquer dia listado abre a janela dedicada em modo **🔒 Somente Leitura**, contando com o botão **✏️ Editar Nota** caso queira editar sem perder a navegação do calendário.

### 5. 📥 Importar TXT (Direto para Pastas)
- **Sem Necessidade de Formato de Data:** Importa um ou vários arquivos `.txt` (ou uma pasta inteira do computador) com **qualquer nome de arquivo**, usando o nome do arquivo como título da nota e detectando automaticamente a codificação (`UTF-8`, `ANSI/Windows-1252`, `ISO-8859-1`).
- **Escolha ou Criação de Pasta na Hora:** Ao iniciar a importação, o sistema pergunta em qual pasta deseja colocar a(s) nota(s) ou permite **criar uma nova pasta/subpasta** imediatamente na mesma janela.
- **Tratamento de Conflitos:** Escolha entre **Ignorar**, **Substituir** ou **Mesclar (Anexar)** caso já exista uma nota com o mesmo nome na pasta escolhida.
- **Histórico do Último TXT Importado:** Exibe no topo da tela um card destacando o **📄 Último TXT Importado** (nome do arquivo, pasta de destino e data/hora da importação), com botão rápido **🗂️ Abrir em Notas & Pastas**.

### 6. 💾 Exportar, Backup Automático e Dicionário Ortográfico
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

### 7. 🎨 Tema Persistente e Controle de Usuários
- **Modo Escuro e Modo Claro Persistentes:** A escolha entre **Modo Escuro** e **Modo Claro** no rodapé da barra lateral é salva automaticamente no perfil do usuário e restaurada sempre que ele fizer login novamente.
- **Gerenciamento de Usuários (Admin):** Cadastro de novos usuários, ativação/desativação de contas, redefinição de senhas (criptografia **Argon2id**) e permissão para visualizar diários de outros usuários.

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

## 📂 Estrutura de Diretórios

```text
DAILYNotes/
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
