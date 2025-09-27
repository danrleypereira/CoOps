# Política de Segurança

Agradecemos seu interesse em manter o projeto GitHub Metrics seguro. Esta política descreve como reportar vulnerabilidades e como tratamos incidentes de segurança.

## 📬 Como Reportar
NÃO abra issues públicas para vulnerabilidades. Envie um e-mail para:

`security-github-metrics@proton.me` (placeholder)

Inclua (se possível):
- Descrição clara da vulnerabilidade
- Passos para reproduzir
- Impacto potencial
- Escopo afetado (scripts, dados, endpoints externos)
- Sugestão de mitigação

Confirmaremos o recebimento em até 72h e enviaremos atualizações enquanto avaliamos.

## 🔐 Boas Práticas ao Reportar
- Utilize linguagem clara e objetiva
- Forneça provas (logs, PoC, outputs)
- Evite exploração além do mínimo necessário
- Não acesse ou modifique dados de terceiros

## ✅ Processo Interno
1. Triagem (classificação de severidade)
2. Confirmação e replicação
3. Correção (branch privada se necessário)
4. Release de patch
5. Divulgação coordenada (quando aplicável)

## 🗓️ Janela de Divulgação
Pedimos até 30 dias para corrigir vulnerabilidades de severidade média/alta antes de divulgação pública. Casos críticos podem ter prioridade imediata.

## 🔄 Versões Suportadas
Atualmente mantemos apenas o branch `main`. Futuras versões tagueadas seguirão política SemVer + suporte sobre a última minor release.

| Versão | Status |
|--------|--------|
| main   | Estável / Recebe patches |

## 🚫 Fora de Escopo (por enquanto)
- DoS de alto volume sem PoC controlado
- Dependências externas sem patch disponível upstream
- Credenciais comprometidas fora do controle do projeto
- Técnicas de engenharia social

## 🔐 Dependências
Recomenda-se varrer dependências com ferramentas como `pip-audit` periodicamente (aceitamos PRs automatizando isso).

## 🛡️ Dados e Privacidade
O projeto pode manipular dados públicos de repositórios e perfis GitHub. Não deve coletar ou armazenar informações privadas / sensíveis além do mínimo necessário (tokens locais do usuário não devem ser commitados).

## 🤝 Reconhecimento
Contribuidores de segurança podem ser listados futuramente em seção de agradecimentos caso desejem divulgação.

Obrigado por ajudar a proteger a comunidade e o ecossistema open source! 🛠️
