# 📌 Possiveis Issues do Projeto

## 🧩 1. Expandir Sistema de Filtros

**Descrição:**  
Expandir os filtros atuais (repositórios e pessoas) para suportar novos tipos de análise.

**Escopo:**
- Times e grupos (criados no frontend)
- Tags do GitHub (labels de issues e PRs)
- Combinação de múltiplos filtros

**Exemplos:**
- Time Backend + Label "bug"
- Grupo X + Repositório Y + período

---

## 🚀 2. Adicionar Métricas de Deploy

**Descrição:**  
Implementar métricas baseadas em deploy (DORA).

**Escopo:**
- Lead Time (commit → deploy)
- Frequência de deploy
- Taxa de falha
- Tempo de recuperação (MTTR)



---

## 🌐 3. Exportar Dados para Repositório Externo

**Descrição:**  
Permitir salvar os dados extraídos em outro repositório (ex: público).

**Escopo:**
- Configurar repositório de destino
- Enviar dados via GitHub Actions utilizando token PAT
- Manter estrutura `/dados`

---

## 📊 4. Sistema de Correlação e Metas Customizáveis

**Descrição:**  
Permitir criação de análises cruzadas entre métricas e definição de metas personalizadas.

**Escopo:**
- Correlação entre métricas (ex: commits vs PRs, atividade vs deploys)
- Criação de métricas derivadas (ex: produtividade)

**Exemplos:**
- Meta: aumentar frequência de deploy semanal
- Correlação: PRs grandes vs taxa de falha