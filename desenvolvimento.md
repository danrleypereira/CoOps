 
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

### 3. Instale Python e dependências
```bash
sudo apt install python3 python3-pip
pip3 install requests pandas numpy
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
GITHUB_REPOSITORY_OWNER=unb-mds
```

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
# Executa apenas o processamento (requer dados Bronze)
act workflow_call -W .github/workflows/silver-process.yaml --secret-file .secrets --bind
```

**Gold Layer (KPIs Executivos)**:
```bash
# Executa apenas agregação final (requer dados Silver)
act workflow_call -W .github/workflows/gold-aggregate.yaml --secret-file .secrets --bind
```

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
# 1. Bronze: Extração de dados
python3 src/bronze_extract.py --token $GITHUB_TOKEN --org unb-mds --cache

# 2. Silver: Processamento
python3 src/silver_process.py --org unb-mds

# 3. Registry: Atualizar registro
python3 src/registry_manager.py
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
   - **Solução**: `pip3 install requests pandas numpy`
   - **No Ubuntu**: `sudo apt install python3-pip`

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
     https://api.github.com/orgs/unb-mds

# 2. Testar repositórios
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/orgs/unb-mds/repos | jq length

# 3. Testar membros (pode falhar se privados)
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/orgs/unb-mds/members | jq length

# 4. Executar script individual
python3 src/bronze_extract.py --token $GITHUB_TOKEN --org unb-mds
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

 
 
 
