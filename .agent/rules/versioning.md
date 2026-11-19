# Padrão Obrigatório de Versionamento e Publicação (DailyNotes)

Sempre que o usuário solicitar uma correção, melhoria ou customização e pedir para subir as alterações no GitHub (ou publicar uma nova versão), siga **obrigatoriamente** este processo:

## 1. Semantic Versioning (`MAJOR.MINOR.PATCH`)
Determine automaticamente o incremento correto analisando as alterações no código:
- **MAJOR**: alterações estruturais significativas, mudanças incompatíveis ou reformulação importante do aplicativo.
- **MINOR**: inclusão de novas funcionalidades, melhorias e customizações compatíveis.
- **PATCH**: correções de erros, bugs e problemas identificados no funcionamento existente.

Regras estritas:
- Nunca alterar a versão sem analisar o tipo de mudança.
- Nunca incrementar `MAJOR` por pequenas melhorias.
- Não criar nova versão quando não houver alteração real no código.

## 2. Arquivos de Controle
- **`VERSION`**: Fonte única de verdade com o número da versão atual (`X.Y.Z`).
- **`CHANGELOG.md`**: Registrar cada versão por data (`YYYY-MM-DD`) e separar as alterações nas categorias:
  - `Added` (novas funcionalidades)
  - `Changed` (melhorias e alterações)
  - `Fixed` (correções de erros)
  - `Removed` (funcionalidades removidas)
  - `Security` (correções relacionadas à segurança)
  - Nunca duplicar registros nem apagar histórico de versões anteriores.
- **`README.md`**: Manter a versão atual e as informações principais do projeto atualizadas.

## 3. Processo Obrigatório a Cada Publicação
1. Analisar todas as alterações realizadas no código (`git status` e `git diff`).
2. Classificar cada alteração como correção (`PATCH`), melhoria/nova funcionalidade (`MINOR`) ou alteração estrutural incompatível (`MAJOR`).
3. Verificar se existem outras alterações pendentes no Git (não sobrescrever nem enviar alterações fora do escopo sem autorização).
4. Ler a versão atual em `VERSION` e definir automaticamente o próximo número SemVer.
5. Atualizar o arquivo `VERSION`.
6. Atualizar o `CHANGELOG.md` no topo (mantendo o histórico anterior intacto).
7. Atualizar o `README.md` (versão atual e documentação se aplicável).
8. Executar a suíte de testes (`python -m unittest discover -s tests`) e validar que não há erros de sintaxe ou regressões.
9. Conferir o `git diff` para garantir que somente as alterações desejadas serão enviadas.
10. Criar commit seguindo **Conventional Commits** (`fix:`, `feat:`, `refactor:`, `docs:`, `chore:`, etc.).
11. Criar tag Git anotada correspondente à nova versão (`vX.Y.Z`).
12. Enviar commits e tag para o GitHub (`git push origin main` e `git push origin vX.Y.Z`). Nunca executar comandos destrutivos no Git sem autorização e não considerar concluído se o push falhar.

## 4. Formato Obrigatório do Resumo Final
Ao finalizar qualquer publicação, apresentar ao usuário um resumo contendo:
- Versão anterior
- Nova versão
- Tipo de atualização (`PATCH`, `MINOR` ou `MAJOR`)
- Descrição das alterações realizadas
- Arquivos modificados
- Número (hash) e descrição do commit
- Tag criada
- Situação do envio ao GitHub
