# Data Services Agent — Project Spec & Use Cases

## Purpose
Generate parameterised, source-specific analysis scripts (R/dplyr for SAIL; PySpark for NHS England, VICORI, DataCan; ehrQL for OpenSAFELY) from health-data questions. **Never executes code**; emits one script per source + an audit manifest.

## Knowledge & Code Layout
- **Knowledge Vault** `/Knowledge Vault/sources/<name>.md` — authoritative tables, columns, codelists, house style, codegen env.
- **Data Engineering Service** `/Data Engineering Service/data_pipelines/<proj>/` — real pipelines (SAIL, VICORI, NHS E, OpenSAFELY). Follow their pointers (config, helpers, curated assets) for physical names.
- **Generated artifacts** `/Data Engineering Service/generated/` — one script per source.
- **Run manifests** `/Data Engineering Service/runs/YYYY-MM-DD_<slug>.yaml` — question, model, source, tables, artifact, limitations, trace pointer.
- **Audit traces** `<artifact>_trace.md` beside each generated script.

## Hard Rules
1. No execution, no invented tables/columns.
2. Existing-code-first: reuse pipeline helpers (SAIL: `R/utils.R`, `R/common_functions.R`; NHS E: `table_management.py` + curated assets; VICORI: `catalogue/vicori_config.py`, `functions/`, `project_curated_assets/`; OpenSAFELY: `ehrql_helpers/`, checked-in codelists).
3. Cohort resolution via source's documented pointer (SAIL → `cohort_mi` in `project_config.yml`; NHS E → curated MINAP/HES APC tables; etc.).
4. Write results idempotently to source write DB (SAIL → `SAILW1938V`; NHS E → per-project `table_directory.json` target).
5. Native artifact format: SAIL = `.Rmd`; NHS E = Databricks `.py` with `# COMMAND ----------`; OpenSAFELY = `.py` study definition.
6. Parameters in explicit USER SETTINGS block (cohort_def, start_date, end_date, output_path, sample_mode).
7. Lint gate: `tests/assert_frontmatter.py` must pass for every source markdown.

## Workflow
1. Identify source(s) → read Vault source file.
2. Follow project pointers to real table/column names.
3. Search pipeline/helpers for existing matching function; reuse or minimally wrap.
4. Write one parameterised script to `generated/`.
5. End script with idempotent write to write DB (+ optional CSV).
6. Reply: `generated_code_path | metadata summary | cohort definition | execution notes | limitations`.
7. Write run manifest + audit trace.

## Use Cases
| # | Question | Source(s) | Artifact Example |
|---|----------|-----------|------------------|
| 1 | SAIL prior-MI cohort with LSOA, 2020-2025 | SAIL | `generated/sail_prior_mi_cohort_2020-02-01_2025-02-01.Rmd` |
| 2 | NHS E MINAP MI admissions by ethnicity | NHS E | `generated/nhse_minap_mi_ethnicity.py` |
| 3 | VICORI curated covid cohort with date_of_birth asset | VICORI | `generated/vicori_covid_dob_2023-01-01_2023-12-31.py` |
| 4 | OpenSAFELY cardiovascular codelist + ehrQL study def | OpenSAFELY | `generated/opensafely_cvd_study_def.py` |
| 5 | Multi-source: MI incidence SAIL + NHS E comparison | SAIL, NHS E | Two scripts + combined manifest |
| 6 | Feasibility: count of heart-failure codes in SAIL | SAIL | `generated/sail_hf_feasibility.Rmd` (aggregate only) |

## Market Research & Positioning
**Target users**: BHF DSC analysts, NHS England, SAIL/VICORI researchers, OpenSAFELY collaborators. **Pain point**: 60-80% of project time on boilerplate cohort/codelist plumbing. **Differentiator**: Only agent enforcing *existing-code-first* reuse across all five UK health TREs with audit-grade provenance. **Competitors**: Generic SQL generators (no TRE awareness), manual templates (no reuse), vendor copilots (single-source).

## Resources Needed
| Category | Detail |
|----------|--------|
| **Technology** | MCP servers (SAIL, NHS E, VICORI, OpenSAFELY, HDR UK Gateway, GtR), Pylance, pytest/testthat, GitHub Actions CI |
| **Governance** | IG-compliant audit traces (ISO 27001), DSPT-aligned logging, per-source DPIA refs in Vault, DSC steering-group sign-off |
| **People** | 1 FTE maintainer, 0.5 FTE/TRE domain expert, 0.25 FTE IG/legal |
| **Compute** | Read-only TRE metadata/catalogue APIs; no patient-data egress |

## Internal / External
**Internal** to BHF DSC — core capability for DSC-funded projects. **External-facing** via DSC collaboration agreements: partners consume scripts under their own IG; agent never leaves DSC infrastructure.

## 3-Month Delivery Roadmap
| Month | Milestone | Success Metric |
|-------|-----------|----------------|
| 1 | Core engine + SAIL/NHS E parity — Vault sources complete, lint green, 5 use cases | 5/5 golden artifacts match manual |
| 2 | VICORI + OpenSAFELY parity — curated-asset reuse, ehrQL helpers, multi-source manifest | 3/3 VICORI + 3/3 OpenSAFELY pass |
| 3 | Hardening & adoption — CI/CD, DSPT pack, analyst workshop, 10 pilots | 10 pilots ship scripts unaided |

## Governance
This spec (`agents/data-services.md`) is the canonical contract. Knowledge stays in Vault; code stays in Data Engineering Service.