# Contribuindo para GitHub Metrics – Collaboration Dashboard

Obrigado por dedicar seu tempo para contribuir! Este projeto é licenciado sob **GPL-3.0-only (ou posterior)** e buscamos construir uma comunidade acolhedora, transparente e colaborativa.

> TL;DR
> 1. Faça um fork e crie uma branch a partir de `main` usando Conventional Commits no nome.  
> 2. Garanta que scripts rodam localmente (`bronze_extract`, `silver_process`, `registry_manager`).  
> 3. Adicione/ajuste testes (quando aplicável) e execute validações.  
> 4. Atualize documentação se o comportamento público mudar.  
> 5. Abra o PR seguindo o checklist.  
>
> Sempre respeite nosso [Código de Conduta](CODE_OF_CONDUCT.md).

---
## 📜 Licenciamento das Contribuições
Ao contribuir, você concorda que sua contribuição será licenciada sob a **GNU General Public License v3.0 ou posterior**. Se incluir arquivos novos de código, adicione no topo (quando aplicável):
```
# GitHub Metrics – Collaboration Dashboard
# Copyright (C) 2025 GitHub Metrics Contributors
# Licensed under the GNU General Public License v3.0 (or later). See LICENSE.
```
Para JSON/MD utilize comentários no PR descrevendo a autoria.

---
## 🧱 Arquitetura Rápida
- Bronze: extração da API do GitHub (dados crus)
- Silver: processamento e enriquecimento analítico
- Gold: KPIs executivos

Detalhes: veja `ARCHITECTURE.md`.

---
## 🔧 Ambiente de Desenvolvimento
Pré-requisitos sugeridos:
- Python 3.10+
- `pip install -r requirements.txt` (se existir) ou manual: `requests pandas numpy`
- GitHub Personal Access Token com permissões de leitura (org/repo)

Executando pipeline manual:
```bash
python3 src/bronze_extract.py --token $GITHUB_TOKEN --org unb-mds --cache
python3 src/silver_process.py --org unb-mds
python3 src/registry_manager.py
```

Para simular GitHub Actions localmente (opcional): consulte `desenvolvimento.md`.

---
## 🌿 Fluxo de Branches
- `main`: sempre estável.
- Branches de feature: `feat/minha-feature-analise-heatmap`
- Padrões:
  - `feat/` nova funcionalidade
  - `fix/` correção de bug
  - `docs/` documentação
  - `refactor/` melhoria interna sem mudar comportamento externo
  - `chore/` automação, configs, deps

---
## ✍️ Commits (Conventional Commits)
Formato: `<type>(escopo opcional): descrição curta`
Exemplos:
```
feat(bronze): adicionar cache para commits
fix(silver): corrigir cálculo de cycle time
docs: atualizar seção de execução local
```
> Descrição imperativa, <= 72 caracteres. Use corpo para detalhes.

---
## ✅ Checklist para Pull Requests
Antes de abrir o PR:
- [ ] Issue relacionada vinculada (`Fixes #123` ou `Closes #123`)
- [ ] Descrição clara do objetivo
- [ ] Scripts relevantes testados localmente
- [ ] Sem regressões aparentes em arquivos de dados críticos
- [ ] Documentação atualizada (`README`, `ARCHITECTURE`, etc.)
- [ ] Cobertura de casos edge (quando relevante)
- [ ] Commits seguem Conventional Commits
- [ ] Sem arquivos temporários (cache local, credenciais, etc.)

### Template sugerido no PR
```
### Contexto
(Explique o problema ou oportunidade)

### O que foi feito
- ...

### Como validar
Passos para reproduzir/verificar.

### Riscos / Observações
- ...

### Screenshots (se aplicável)
```

---
## 🧪 Testes e Validação
Ainda que o projeto seja orientado a scripts, incentiva-se:
- Testes unitários para utilitários críticos (ex.: normalização, agregações)
- Verificação de integridade de JSON gerados (schemas simples)
- Scripts de sanity check (ex.: tamanho > 0, chaves esperadas)

Sugestão de diretório futuro: `tests/`.

---
## 🗂️ Estrutura de Dados Sensíveis
Não commitar:
- Tokens
- Dumps privados
- Arquivos `.secrets`

Use `.gitignore` conforme necessário.

---
## 🐛 Reportando Bugs
Abrir issue usando template (se existir) com:
- Passos para reproduzir
- Comando(s) executado(s)
- Output relevante / stack trace
- Ambiente (OS, versão Python)

---
## 💡 Sugerindo Funcionalidades
Abra issue `feature request` descrevendo:
- Problema / motivação
- Exemplo de uso
- Métrica / dado necessário
- Possíveis impactos na arquitetura

---
## 🔐 Segurança
Vulnerabilidades: NÃO abra issue pública. Envie email para: `security-github-metrics@proton.me` (placeholder) com:
- Descrição da vulnerabilidade
- Passos de exploração
- Impacto
- Sugestão de mitigação

Veja mais em `SECURITY.md` (quando disponível).

---
## 🤝 Código de Conduta
Conforme [Código de Conduta](CODE_OF_CONDUCT.md). Ao participar você concorda em respeitá-lo.

---
## 📦 Releases
Planejado: versionamento SemVer pós-estabilização inicial.

---
## 🗣️ Discussões
Para dúvidas de arquitetura ou métricas abra uma issue `question`.

---
## 🙌 Reconhecimento
Contribuidores serão listados no futuro em seção de agradecimentos / `AUTHORS.md`.

Obrigado por ajudar a construir um ecossistema de colaboração saudável! 🎉
