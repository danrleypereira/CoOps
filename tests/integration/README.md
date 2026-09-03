# Testes de Integração - ETL Pipeline

Este diretório contém testes de integração para o pipeline ETL (Bronze → Silver → Gold) e componentes relacionados do projeto.

## Estrutura dos Testes

### 1. `test_bronze_to_silver_integration.py`
Testa a transformação de dados da camada Bronze para Silver:

- ✅ `test_member_analytics_transformation` - Valida processamento de métricas de membros
- ✅ `test_contribution_metrics_transformation` - Valida métricas de contribuição
- ✅ `test_collaboration_networks_transformation` - Valida redes de colaboração
- ✅ `test_temporal_analysis_transformation` - Valida análise temporal de eventos
- ✅ `test_complete_bronze_to_silver_pipeline` - Valida fluxo completo Bronze→Silver
- ✅ `test_handles_empty_bronze_data` - Testa comportamento com dados vazios
- ✅ `test_handles_malformed_bronze_data` - Testa tratamento de dados malformados

### 2. `test_silver_to_gold_integration.py`
Testa a transformação de dados da camada Silver para Gold:

- ✅ `test_timeline_aggregation_last_7_days` - Valida agregação dos últimos 7 dias
- ✅ `test_timeline_aggregation_last_12_months` - Valida agregação de 12 meses
- ✅ `test_complete_silver_to_gold_pipeline` - Valida fluxo completo Silver→Gold
- ✅ `test_timeline_sorts_chronologically` - Verifica ordenação cronológica
- ✅ `test_aggregation_preserves_metrics` - Verifica preservação de métricas
- ✅ `test_handles_empty_silver_data` - Testa comportamento com dados vazios
- ✅ `test_handles_partial_silver_data` - Testa dados parciais
- ✅ `test_author_repository_mapping` - Valida mapeamento autor-repositório
- ✅ `test_monthly_aggregation_logic` - Valida lógica de agregação mensal

### 3. `test_complete_etl_pipeline.py`
Testa o pipeline ETL end-to-end completo:

- ✅ `test_complete_etl_pipeline_execution` - Valida execução completa Bronze→Silver→Gold
- ✅ `test_data_consistency_across_layers` - Verifica consistência entre camadas
- ✅ `test_member_maturity_classification` - Valida classificação de maturidade
- ✅ `test_contribution_metrics_accuracy` - Verifica geração de métricas
- ✅ `test_temporal_aggregation_accuracy` - Valida agregações temporais
- ✅ `test_timeline_reflects_recent_activity` - Verifica atividades recentes
- ✅ `test_pipeline_handles_incremental_updates` - Testa atualizações incrementais
- ✅ `test_error_propagation_handling` - Testa propagação de erros

### 4. `test_process_scripts_integration.py` 🆕
Testa a integração dos scripts principais de processamento:

- ✅ `test_silver_process_runs_all_processors` - Valida execução de todos processadores silver
- ✅ `test_gold_process_depends_on_silver` - Verifica dependência Gold→Silver
- ✅ `test_complete_etl_script_sequence` - Valida sequência completa de scripts
- ✅ `test_process_scripts_handle_empty_data` - Testa tratamento de dados vazios
- ✅ `test_process_scripts_are_idempotent` - Verifica idempotência dos scripts
- ✅ `test_silver_process_order_independence` - Testa independência de ordem
- ✅ `test_gold_process_fails_without_silver_data` - Valida tratamento de dados faltantes
- ✅ `test_data_flows_from_bronze_to_silver` - Verifica fluxo de dados Bronze→Silver
- ✅ `test_data_flows_from_silver_to_gold` - Verifica fluxo de dados Silver→Gold
- ✅ `test_bronze_updates_trigger_silver_updates` - Testa reprocessamento
- ✅ `test_silver_process_continues_on_single_processor_failure` - Testa recuperação de erro
- ✅ `test_process_scripts_preserve_existing_data_on_failure` - Testa preservação de dados

### 5. `test_bronze_extractors_integration.py` 🆕
Testa a integração entre extratores da camada Bronze:

- ⏭️ `test_repositories_extraction_basic` - Extração básica de repositórios (skipped)
- ⏭️ `test_commits_extraction_basic` - Extração básica de commits (skipped)
- ⏭️ `test_issues_extraction_basic` - Extração básica de issues (skipped)
- ⏭️ `test_members_extraction_basic` - Extração básica de membros (skipped)
- ⏭️ `test_extraction_order_matters` - Verifica ordem de extração (skipped)
- ⏭️ `test_cache_usage_prevents_redundant_calls` - Testa uso de cache (skipped)
- ✅ `test_repository_ids_consistent_across_extractions` - Valida consistência de IDs
- ✅ `test_user_references_consistent` - Valida referências de usuários
- ✅ `test_timestamp_formats_consistent` - Verifica formatos de timestamp
- ✅ `test_bronze_files_have_metadata` - Valida metadados nos arquivos
- ✅ `test_extraction_handles_empty_organization` - Testa org vazia
- ✅ `test_extraction_handles_api_failures` - Testa falhas de API
- ✅ `test_partial_extraction_preserves_data` - Testa preservação parcial

### 6. `test_registry_manager_integration.py` 🆕
Testa o gerenciamento do catálogo de dados:

- ✅ `test_scan_data_directory_finds_files` - Valida busca de arquivos
- ✅ `test_categorize_bronze_files_groups_correctly` - Testa categorização
- ⚠️ `test_create_master_registry_structure` - Estrutura do registro (needs fix)
- ⚠️ `test_registry_tracks_file_metadata` - Rastreamento de metadados (needs fix)
- ⏭️ `test_validate_registry_integrity_passes_valid_registry` - Validação (skipped)
- ⚠️ `test_registry_updates_incrementally` - Atualizações incrementais (needs fix)
- ⏭️ `test_generate_registry_report_creates_summary` - Relatório (skipped)
- ✅ `test_registry_handles_empty_directories` - Testa diretórios vazios
- ✅ `test_registry_categorizes_different_file_types` - Categorização de tipos
- ⚠️ `test_catalog_tracks_all_layers` - Rastreamento de camadas (needs fix)
- ✅ `test_registry_timestamp_is_valid` - Validação de timestamp
- ✅ `test_registry_file_inventory_completeness` - Completude do inventário

## Executando os Testes

> Prefixe os comandos com `poetry run` (ou ative o venv com `poetry env activate`).

### Todos os testes de integração
```powershell
poetry run pytest tests/integration/ -v
```

### Testes específicos por arquivo
```powershell
# Bronze → Silver
poetry run pytest tests/integration/test_bronze_to_silver_integration.py -v

# Silver → Gold
poetry run pytest tests/integration/test_silver_to_gold_integration.py -v

# Pipeline Completo
poetry run pytest tests/integration/test_complete_etl_pipeline.py -v
```

### Com cobertura de código
```powershell
poetry run pytest tests/integration/ --cov=coops --cov-report=html
```

### Executar teste específico
```powershell
poetry run pytest tests/integration/test_bronze_to_silver_integration.py::TestBronzeToSilverIntegration::test_member_analytics_transformation -v
```

## Arquitetura dos Testes

### Fixtures Compartilhadas (`conftest.py`)

- **`fake_io`**: Mock do sistema de I/O que armazena dados em memória ao invés de disco
  - Substitui `load_json_data` e `save_json_data`
  - Permite testes isolados sem dependências de arquivos reais
  - Verifica fluxo de dados entre camadas

### Padrão de Teste

1. **Arrange**: Criar dados mock na camada bronze/silver
2. **Act**: Executar processadores da camada seguinte
3. **Assert**: Verificar:
   - Arquivos foram gerados corretamente
   - Estrutura dos dados está correta
   - Métricas foram calculadas adequadamente
   - Dados são consistentes entre camadas

## Dados de Teste

Os testes usam dados mock que simulam:

- **Membros**: 2-3 usuários com diferentes níveis de maturidade
- **Commits**: 15-30 commits distribuídos ao longo do tempo
- **Issues**: 3-4 issues em diferentes estados (open/closed)
- **Pull Requests**: PRs de diferentes autores

## Resultados Atuais

**Status**: ✅ **49/53 testes passando (93%)** + **8 skipped**

### ✅ Totalmente Funcionando
- ✅ Transformação Bronze → Silver (7/7 testes)
- ✅ Transformação Silver → Gold (10/10 testes)
- ✅ Pipeline ETL End-to-End (8/8 testes)
- ✅ Scripts de Processamento (12/12 testes) 🆕

### 🔶 Parcialmente Funcionando
- 🔶 Extratores Bronze (7/13 testes) - 6 skipped (requerem API real) 🆕

### ⚠️ Requer Correção
- ⚠️ Gerenciador de Registro (6/13 testes) - 4 failing, 2 skipped 🆕

### 📊 Cobertura de Código
- **silver/member_analytics.py**: 85%
- **silver/contribution_metrics.py**: 74%
- **silver/collaboration_networks.py**: 75%
- **silver/temporal_analysis.py**: 77%
- **gold/timeline_aggregation.py**: 95%
- **utils/registry_manager.py**: 85%
- **Cobertura Total**: 42% (+5% desde início)

## Próximos Passos

### Imediato
1. **Corrigir registry_manager tests**: Integrar `create_master_registry` com `fake_io` fixture
2. **Implementar funções faltantes**: 
   - `validate_registry_integrity()` em `utils/registry_manager.py`
   - `generate_registry_report()` em `utils/registry_manager.py`

### Curto Prazo
3. **Aumentar cobertura de código geral**: Atualmente em 42%, meta 60%
4. **Implementar MockGitHubClient**: Permitir testes dos extratores bronze sem API real
5. **Adicionar mais cenários de borda**:
   - Dados com timestamps inconsistentes  
   - Repositórios com grande volume de dados
   - Falhas de rede simuladas

### Longo Prazo
6. **Testes de performance**: Validar com datasets maiores (1000+ commits)
7. **Testes de idempotência**: Verificar que reprocessar gera mesmos resultados
8. **Testes de integração com API real**: Usando repositórios de teste pequenos

## Convenções

- Testes começam com `test_`
- Classes de teste começam com `Test`
- Use fixtures para dados reutilizáveis
- Testes devem ser independentes (sem ordem de execução)
- Sempre limpe o estado entre testes (gerenciado pelo pytest automaticamente)

## Troubleshooting

### Erro: "ModuleNotFoundError: No module named 'pandas'"
```powershell
poetry install --extras dev
```

### Erro: "No module named pytest"
```powershell
poetry install --extras dev
```

### Testes falhando com datas
- Verifique se as datas mock são recentes (último ano)
- Considere usar `freezegun` para controlar o tempo nos testes

## Contribuindo

Ao adicionar novos testes de integração:

1. Siga o padrão Arrange-Act-Assert
2. Use fixtures compartilhadas quando possível
3. Documente o propósito do teste no docstring
4. Valide múltiplos aspectos (estrutura, conteúdo, consistência)
5. Teste cenários de sucesso E falha
