 
 # Rodando GitHub Actions localmente com GitHub CLI e act

## 📋 Pré-requisitos

### 1. Instale o GitHub CLI (gh)
No terminal:
```bash
sudo apt update
sudo apt install gh
```

### 2. Instale o act
No terminal:
```bash
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
```

### 3. Instale Python, Poetry e as dependências
```bash
sudo apt install python3 python3-pip
pipx install poetry
poetry install --extras dev
```

## 🔑 Configuração do Token

### 4. Gere um token do GitHub (PAT)
- Vá em https://github.com/settings/tokens
- Clique em "Generate new token (classic)"
- Dê as seguintes permissões:
  - `repo` (acesso completo a repositórios)
  - `read:org` (leitura de dados da organização)
  - `read:user` (leitura de dados de usuários)
- Copie o token gerado

### 5. Crie o arquivo `.secrets` na raiz do projeto
```bash
# Copie o arquivo de exemplo
cp EXAMPLE.secrets .secrets

# Edite com seus dados reais
nano .secrets
```

Conteúdo do arquivo `.secrets`:
```
GITHUB_TOKEN=ghp_seu_token_real_aqui
GITHUB_ORG=coops-org
```

> `GITHUB_ORG` no `.secrets` só controla a org extraída quando você roda via `poetry run coops-bronze` direto, ou via `act`/`gh act --secret-file .secrets` no workflow completo. Em produção (push/schedule reais no GitHub Actions) o workflow sempre usa a org dona do repositório (`github.repository_owner`), ignorando esse valor — não existe esse secret configurado lá.

## 🚀 Executando os Workflows

### Arquitetura Medallion (Novo Sistema)

O novo sistema usa arquitetura em camadas: Bronze → Silver → Gold

#### Opção 1: Pipeline Completo (Bronze → Silver → Gold)
```bash
# Executa todo o pipeline automaticamente
act workflow_dispatch -W .github/workflows/bronze-extract.yaml --secret-file .secrets --bind
```

#### Opção 2: Camadas Individuais

**Bronze Layer (Extração de Dados Brutos)**:
```bash
# Executa apenas a extração de dados brutos
act workflow_dispatch -W .github/workflows/bronze-extract.yaml --secret-file .secrets --bind -j extract-bronze-data
```

**Silver Layer (Processamento de Analytics)**:
```bash
# Executa apenas o processamento (requer dados Bronze já em data/bronze/)
act workflow_dispatch -W .github/workflows/silver-process.yaml --secret-file .secrets --bind --container-options "--user $(id -u):$(id -g)" -j process-silver-data
```

**Gold Layer (KPIs Executivos)**:
```bash
# Executa apenas a agregação final (requer dados Silver já em data/silver/)
act workflow_dispatch -W .github/workflows/gold-process.yaml --secret-file .secrets --bind --container-options "--user $(id -u):$(id -g)" -j process-gold-data
```

> ℹ️ `gold-process.yaml` é o workflow de Gold efetivamente encadeado pelo pipeline (é o que `silver-process.yaml` dispara no job `trigger-gold-processing`, e o único com o step de AI analysis opcional via `GEMINI_API_KEY`). O arquivo `gold-aggregate.yaml` também existe no repo mas é um workflow legado/órfão, não chamado por nenhum outro — não use ele pra testar o pipeline real.

> ⚠️ **Silver e Gold exigem `--bind` (não rodam sem ele)**: diferente do `bronze-extract.yaml`, os steps "Pull latest data files" de `silver-process.yaml` e `gold-process.yaml` rodam `git branch --show-current` / `git pull` **sem** o guard `if: ${{ !env.ACT }}` que o Checkout tem. Como o Checkout é pulado sob `act`/`gh act` (mesmo motivo explicado abaixo), se você esquecer o `--bind` o container não tem repositório git nenhum montado e o comando falha com `fatal: not a git repository (or any parent up to mount point ...)`. Sempre inclua `--bind` (e o `--container-options` pra não sujar os arquivos gerados com `root:root`) nesses dois workflows.

#### Teste Rápido (poucos commits, ideal para debug local)

O workflow de Bronze aceita `max_repos`, `max_commits_per_repo`, `skip_structure`, `since`, `max_issues` e `max_prs` como inputs de `workflow_dispatch`, só usados quando disparado manualmente (push/schedule continuam extraindo tudo). Use isso pra testar rápido sem esperar a extração completa da organização:
```bash
# Extrai só até 3 repositórios, 5 commits/issues/PRs por repositório, pula a
# extração de estrutura e limita a extração a commits a partir de 2026
gh act workflow_dispatch \
  -W .github/workflows/bronze-extract.yaml \
  -j extract-bronze-data \
  --secret-file .secrets \
  --bind \
  --container-options "--user $(id -u):$(id -g)" \
  --input max_repos=3 \
  --input max_commits_per_repo=5 \
  --input skip_structure=true \
  --input since=2026-01-01T00:00:00Z \
  --input max_issues=5 \
  --input max_prs=5
```
`max_repos`/`max_issues`/`max_prs` também limitam a paginação da busca correspondente (não é só um corte no que é salvo, acelera a busca em si). Como o filtro de blacklist/forks roda depois do corte de `max_repos`, o resultado pode ter menos repositórios que o pedido se os primeiros da lista forem filtrados. `max_issues`/`max_prs` compartilham a mesma chamada paginada (issues e PRs vêm juntos da API do GitHub), então o cap usa o maior dos dois valores pra parar de paginar cedo. Eventos de issues (`issue_events_*.json`) não são afetados por esses caps.

Esse é o comando padrão para testes rápidos da extração. Requer a extensão `gh-act` (`gh extension install nektos/gh-act`) como alternativa ao `act` instalado via script (passo 2 acima) — ambos funcionam, `gh act` só reusa a autenticação já configurada no `gh`.

> ⚠️ **Cuidado com `--bind`**: ele monta o repositório real dentro do container, e o container roda como `root` — qualquer arquivo criado/modificado (em `cache/`, `data/`, etc.) fica `root:root` no host. O step de "Checkout repository" do `bronze-extract.yaml` já tem `if: ${{ !env.ACT }}` (mesmo padrão de `silver-process.yaml`/`gold-process.yaml`), então sob `act`/`gh act` ele é pulado — `actions/checkout@v4` faria `git clean -ffdx` por padrão antes de rodar, o que apagaria até arquivos ignorados pelo `.gitignore` (como o `.secrets`) direto no seu repo real. Isso já protege os arquivos rastreados/`.secrets`, mas não evita o `root:root` nos arquivos gerados durante a extração — pra isso, adicione `--container-options "--user $(id -u):$(id -g)"` no comando (roda o container com seu UID/GID; se seu `act` ignorar essa flag, use `sudo chown -R $(whoami):$(whoami) .` como fallback). Mesmo assim, prefira commitar ou `git stash -u` antes de rodar localmente, como rede de segurança extra.

### Workflow Legacy (Sistema Antigo - DEPRECATED)
```bash
# Sistema antigo (ainda funciona mas redirecionará para o novo)
act workflow_dispatch -W .github/workflows/start.yaml --secret-file .secrets --bind
```

## 📁 Estrutura de Dados Gerados

Após execução bem-sucedida, você terá:

### Bronze Layer (Dados Brutos)
```
data/bronze/
├── repositories_filtered.json    # Repositórios da organização
├── members_detailed.json         # Membros com dados completos
├── issues_all.json              # Todas as issues
├── prs_all.json                 # Todos os pull requests
├── commits_all.json             # Todos os commits
└── issue_events_all.json        # Eventos das issues/PRs
```

### Silver Layer (Analytics Processados)
```
data/silver/
├── members_analytics.json           # Análise de maturidade dos membros
├── contribution_metrics.json        # Métricas de contribuição
├── collaboration_edges.json         # Rede de colaboração
├── temporal_events.json            # Eventos ordenados no tempo
├── activity_heatmap.json           # Mapa de calor de atividade
└── cycle_times.json                # Tempos de resolução
```

### Gold Layer (KPIs Executivos)
```
data/gold/
├── executive_dashboard.json        # KPIs executivos
└── performance_tiers.json          # Classificação de performance
```

## 🛠️ Execução Manual (Alternativa)

Se preferir executar os scripts diretamente:

```bash
# 0. Instalar o pacote (uma vez): poetry install

# 1. Bronze: Extração de dados (GITHUB_TOKEN/GITHUB_ORG vêm do .secrets ou do ambiente)
poetry run coops-bronze --cache

# 2. Silver: Processamento
poetry run coops-silver

# 3. Registry: Atualizar registro
poetry run coops-registry
```

## 🔍 Parâmetros Úteis do act

- `--bind`: Arquivos criados aparecem na máquina local
- `--secret-file .secrets`: Usa arquivo de secrets local
- `--dry-run`: Simula sem executar
- `--verbose`: Saída detalhada para debug
- `-j job-name`: Executa job específico
- `--pull=false`: Não baixa imagens Docker (mais rápido)

## 📊 Verificação dos Resultados

### Verificar dados Bronze:
```bash
ls -la data/bronze/
jq '.organization_health' data/bronze/repositories_filtered.json
```

### Verificar dados Silver:
```bash
ls -la data/silver/
jq '.total_contributors' data/silver/contribution_metrics.json
```

### Verificar dados Gold:
```bash
ls -la data/gold/
jq '.organization_health' data/gold/executive_dashboard.json
```

### Verificar registry completo:
```bash
jq '.bronze | keys' data/master_registry.json
jq '.silver | keys' data/master_registry.json
```

## 🐛 Troubleshooting

### Problemas Comuns:

1. **❌ Failed to fetch members**
   - **Causa**: Organização pode ter membros privados ou token com permissões limitadas
   - **Solução**: Sistema tem fallback inteligente que busca contribuidores ativos
   - **Token recomendado**: `read:org` para membros públicos
   - **Fallback**: Descobre colaboradores via API de contributors dos repositórios
   - **Resultado**: Funciona mesmo com organizações que têm membros privados

2. **❌ Error: 'name' (KeyError)**
   - **Causa**: Estrutura JSON com metadados inesperados
   - **Solução**: Scripts agora tratam metadados automaticamente
   - **Verificar**: Se repositories_filtered.json existe e é válido

3. **❌ API 403 Forbidden**
   - **Causa**: Token sem permissões ou rate limit
   - **Solução**: Verificar permissões do token:
     - `repo` (acesso a repositórios)
     - `read:org` (dados da organização)
     - `read:user` (perfis de usuários)

4. **❌ Empty data files**
   - **Causa**: Organização sem dados públicos
   - **Solução**: Sistema cria arquivos vazios para manter estrutura
   - **Normal**: Para organizações com poucos dados públicos

5. **❌ Rate limit exceeded**
   - **Solução**: Aguarde reset ou use `--cache` para evitar re-downloads
   - **Verificar**: Headers mostram quando rate limit reseta

6. **❌ Dependências Python**
   - **Solução**: `poetry install --extras dev`
   - **No Ubuntu**: `sudo apt install python3-pip && pipx install poetry`

7. **❌ `fatal: not a git repository (or any parent up to mount point ...)` ao rodar Silver/Gold**
   - **Causa**: Rodou `silver-process.yaml` ou `gold-process.yaml` sem `--bind`. O Checkout é pulado sob `act` (`if: ${{ !env.ACT }}`), e sem `--bind` não sobra nenhum repositório git no container pro step seguinte ("Pull latest data files") rodar `git branch`/`git pull`
   - **Solução**: sempre inclua `--bind` (e `--container-options "--user $(id -u):$(id -g)"`) ao rodar esses dois workflows via `act`/`gh act`, como no exemplo da seção "Camadas Individuais"

### Logs detalhados:
```bash
# Execução com logs verbosos
act --verbose workflow_dispatch -W .github/workflows/bronze-extract.yaml --secret-file .secrets

# Verificar cache de API
ls -la cache/

# Verificar permissões do token
curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user
```

### Verificação passo-a-passo:

```bash
# 1. Testar token
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
   https://api.github.com/orgs/coops-org

# 2. Testar repositórios
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
   https://api.github.com/orgs/coops-org/repos | jq length

# 3. Testar membros (pode falhar se privados)
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
   https://api.github.com/orgs/coops-org/members | jq length

# 4. Executar etapa individual
poetry run coops-bronze --token $GITHUB_TOKEN --org coops-org
```

### Dados esperados após execução bem-sucedida:

```bash
# Verificar arquivos Bronze gerados
ls -la data/bronze/
# Deve conter: repositories_*.json, members_*.json, issues_*.json, etc.

# Verificar conteúdo dos arquivos
jq 'length' data/bronze/repositories_filtered.json
jq '.organization_health' data/bronze/members_detailed.json 2>/dev/null || echo "Arquivo vazio (normal)"
```

## 📈 Próximos Passos

1. **Execute o pipeline Bronze** para coletar dados brutos
2. **Analise os dados Silver** gerados para insights
3. **Use os KPIs Gold** para dashboards executivos
4. **Configure cron jobs** para execução automatizada
5. **Personalize métricas** editando os scripts Silver/Gold

Pronto! Agora você pode executar todo o pipeline de métricas GitHub localmente com a nova arquitetura Medallion.

 
 
 
