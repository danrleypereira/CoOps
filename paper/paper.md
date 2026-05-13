---
title: 'CoOps: An open-source full-stack dashboard for monitoring collaboration in GitHub-based academic software factories'
tags:
  - Python
  - TypeScript
  - software engineering education
  - GitHub
  - software metrics
  - data visualization
  - medallion architecture
authors:
  - name: Danrley Willyan da Silva Pereira
    orcid: 0009-0006-4982-3800
    corresponding: true
    affiliation: 1
  - name: Carla Silva Rocha Aguiar
    orcid: 0000-0003-3102-5166
    affiliation: 2
  - name: Kerlla de Souza Luz
    orcid: 0000-0002-2262-2324
    affiliation: 1
affiliations:
  - name: Centro Universitário do Distrito Federal (UDF), Brasília, Brazil
    index: 1
  - name: Universidade de Brasília (UnB), Brasília, Brazil
    index: 2
date: 12 May 2026
bibliography: paper.bib
---

# Summary

`CoOps` is an open-source full-stack dashboard for continuously monitoring
collaboration in **GitHub-based academic software factories** — educational
programs in which students develop real software under industry-grade
practices and tooling. The platform combines **technical metrics** (commits,
pull requests, issues, code churn, lead time) and **collaboration metrics**
(review participation, author–reviewer networks, contribution distribution,
ramp-up cadence) across thirteen interactive D3.js pages, with optional
natural-language summaries from Google Gemini that explain individual
contribution patterns. Data flows through a **Medallion Architecture**
[@databricks2022medallion] — Bronze (raw GitHub API events), Silver (typed
dim/fact tables with lineage), Gold (executive KPIs ready for the dashboard)
— and is refreshed daily by GitHub Actions, then published through GitHub
Pages. The serverless deployment removes per-institution infrastructure costs
and makes adoption low-effort. `CoOps` was co-developed with Prof. Carla
Rocha (UnB) and currently runs in production at two universities, including
the end-of-semester student evaluation workflow at UnB's *Métodos de
Desenvolvimento de Software* course. \autoref{fig:home} shows the dashboard
landing page.

![Landing page of the CoOps dashboard showing the organization
overview.\label{fig:home}](figures/pagina-inicial.png){width=85%}

# Statement of need

GitHub-native panels such as Insights and Pulse [@github-insights] focus on
repository-scoped activity counts; they do not surface organization-level
collaboration structure, ramp-up cadence per member, or formative indicators
suitable for academic assessment. Academic software factories, in turn,
inherit a long-standing call for metrics aligned with pedagogical milestones
rather than industrial KPIs alone [@dos2021experiencia; @kitchenham2010s;
@barbosaIndicadoresConjunto2016]. Faculty supervising such programs need to
distinguish "integrator" students with many cross-repo links from
"specialists" focused on one stack [@hamer2021using], and to interpret early
weekly slopes as predictors of end-of-semester engagement, but they typically
lack a free, reproducible, organization-scoped tool that aggregates these
signals.

`CoOps` fills this gap. It is targeted at three audiences:

1. **Faculty and teaching assistants** running GitHub-based courses or
   capstone projects, who need a single dashboard to grade contributions and
   spot disengagement early.
2. **Coordinators of academic software factories** who must track multiple
   teams and repositories simultaneously and require shared, auditable
   indicators.
3. **Software engineering education researchers** who study collaboration in
   educational settings and want a reusable pipeline that does not depend on
   institutional infrastructure.

The platform's GPL-3.0 license [@osi-gpl3] and zero-infrastructure deployment
make adoption viable for institutions in low-resource settings, an explicit
design constraint inherited from interviews with Brazilian university software
factories during requirements elicitation.

# State of the field

Several tools touch parts of the problem space, but none combines the four
properties — organization scope, collaboration emphasis, lineage-preserving
pipeline, and zero-infrastructure deployment — that `CoOps` targets.

- **GitHub Insights and the Pulse panel** [@github-insights] expose
  repository-scoped activity counts and stop short of cross-repo aggregation,
  collaboration network structure, or pedagogical narrative.
- **GHTorrent** [@gousios2013ghtorent] and **GHArchive** [@grigorik2012gharchive]
  provide raw, queryable GitHub event streams. They are excellent research
  data sources but do not ship a dashboard, an opinionated KPI set, or per-
  member explanations.
- **Open Source Insights / deps.dev** [@google2023depsdev] focuses on
  dependency graphs and security advisories rather than authorial behavior.
- **OpenSSF Scorecard** [@openssf2023scorecard] evaluates the security posture
  of a repository, not the productivity or collaboration patterns of its
  contributors.
- **ScrumWatch** [@vega2022scrumwatch] provides Scrum-specific KPIs (sprint
  velocity, story completion); it neither models collaboration networks nor
  integrates a narrative AI layer, and it is not designed for the
  organization-of-courses scope.
- **CodeFeedr** [@hebig2020codefeedr] proposes a pipeline framework for
  software-engineering data analysis but is not an end-user dashboard for
  faculty.

`CoOps` differentiates by binding the Medallion lineage [@databricks2022medallion]
to a curated KPI set drawn from the educational metrics literature
[@hamer2021using; @ozkan2019agile; @temitope2020software], adding a graceful-
degradation AI explanation layer, and by being deployable end-to-end at zero
recurring cost via GitHub Actions and GitHub Pages.

# Software design

The system is split into a Python backend that runs as scheduled GitHub
Actions and a React 19 + TypeScript + D3.js frontend served as static
artifacts from GitHub Pages (\autoref{fig:arch}). The Medallion architecture
is visible in three numbered orchestrators under `src/`:

- **Bronze** (`src/bronze_extract.py`) drives seven extractors — repositories,
  members, issues, commits, pull requests, events, repository structure —
  that write append-only JSON under `data/bronze/<org>/`. A registry tracks
  provenance, timestamps, and rate-limit state.
- **Silver** (`src/silver_process.py`) runs six analytic modules: member
  analytics, contribution metrics, collaboration edges, temporal events,
  activity heatmaps, and cycle times. Outputs are normalized
  dimension/fact tables with explicit lineage columns.
- **Gold** (`src/gold_aggregate.py`, `src/gold_process.py`) computes
  organization-level KPIs and contribution tiers consumed directly by the
  dashboard.

\autoref{fig:dag} shows the full data-product DAG. An early architectural
trade-off shaped the project: an initial GraphQL-based bronze extractor was
replaced with a REST + batched-pagination implementation when GraphQL rate
limits made daily organization-wide refreshes infeasible. The migration cut
extraction time from roughly three hours to under one minute on a
70-repository organization, enabling the daily CI cadence we ship.

The optional AI module (`src/gemini_ai/`) calls Google Gemini to summarize a
member's commits, PRs, and issue activity in natural language. The module is
opt-in via the `GEMINI_API_KEY` environment variable, applies prompt-injection
guards to user-controlled fields, and degrades gracefully: every page renders
correctly when the key is absent. The frontend (\autoref{fig:network}) is
built on D3.js force-directed layouts and reactive React components, with
state lifted to TanStack Query for cache control.

![Topology: serverless deployment via GitHub Actions and GitHub
Pages.\label{fig:arch}](figures/arquitetura-geral.png){width=80%}

![Data-product DAG of the Medallion
pipeline.\label{fig:dag}](figures/dag-medalhao.png){width=85%}

![Collaboration network: D3.js force-directed graph of author–reviewer
interactions.\label{fig:network}](figures/rede-de-colaboracao.png){width=80%}

Backend test coverage stands at 88 % and frontend at 94 %, both enforced in
CI (`.github/workflows/python-unit-tests.yaml`,
`.github/workflows/python-integration-tests.yaml`, and `dashboard/vitest.config.ts`).

# Research impact

`CoOps` is in production at two universities. At **UnB**, the dashboard
analyzes the `unb-mds` organization (70+ repositories) and was used by Prof.
Carla Rocha to evaluate student contributions at the end of the 2025/2
semester of the MDS course (<https://unb-mds.github.io/2025-2-Squad-01/>). At
**UDF**, it monitors the `LabTechUDF` organization
(<https://labtechudf.github.io/CoOps/>). The pedagogical use at UnB — real
grading decisions in a real course — validates the design choices made
jointly with Prof. Rocha during the co-development cycle
[@bjerregaard2021lessons; @jarvela2018collaboration]. \autoref{fig:heatmap}
illustrates one of the artifacts faculty consult during evaluation.

![Activity heatmap: temporal contribution patterns by day and
hour.\label{fig:heatmap}](figures/heatmap.png){width=80%}

# AI usage disclosure

Two distinct categories of AI are relevant to `CoOps` and we separate them
here. *Runtime AI (a feature of the software, not an authoring tool):* the
platform optionally invokes Google Gemini to generate natural-language
summaries of member contributions; the integration is opt-in, degrades
gracefully when the key is absent, and never replaces the underlying
quantitative data. *Authoring AI (tools used by the human authors):* during
development, the authors used GitHub Copilot for code completion and Copilot
Review for pull-request feedback (visible in the commit history as
"Fix Copilot review findings…"); Anthropic Claude was used as a writing and
refactoring assistant during preparation of this manuscript and scaffolding
parts of the software. All AI-suggested code and prose were reviewed,
edited, and validated by the human authors, who take full responsibility for
the final content.

# Acknowledgements

We thank the LAPPIS/UnB research group for the interviews that grounded the
KPI design and the LabTech/UDF team for hosting the software-factory
experiments. We also acknowledge Pedro Druck (UnB) for code contributions to
the UnB instance of the dashboard. This work was supported by the
**PIBIT 2025–2026** scholarship program of the Centro Universitário do
Distrito Federal.

# References
