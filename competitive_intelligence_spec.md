# Competitive Intelligence Platform: BHF Data Science Centre & HDRUK

## Project Specification (~480 words)

### Vision
Automated platform continuously monitoring UK health data research across BHF DSC, HDRUK, and SDEs to identify collaborations, funding trends, capability gaps, and strategic positioning.

### Core MCP Server Integration

| Server | Primary Intelligence Function |
|--------|------------------------------|
| **gatewayMCP** | Dataset discovery, custodian mapping, publication-dataset linkage, project tracking |
| **hdrsmcp** | SDE infrastructure mapping, project-institution alignment, service-project matching |
| **phenotypelibrarymcp** | Phenotype/concept coverage, codelist gaps, ontology alignment |
| **bhfdscdashboardmcp** | Dataset completeness/coverage benchmarking, data quality intelligence |
| **opensafelymcp** | ehrQL patterns, study designs, OpenSAFELY workspace intelligence |
| **gtr-ukri** | UKRI funding landscape, award outcomes, institutional capacity, collaboration networks |

### Data Architecture
- **Ingestion**: Scheduled MCP queries across 6 servers (daily/weekly)
- **Knowledge Graph**: Entities (datasets, projects, institutions, people, phenotypes, funding) with relationships
- **Analytics**: Trend detection, gap analysis, similarity scoring, predictive modeling
- **Delivery**: Dashboards, alerts, automated reports, API

### Key Intelligence Products
1. **Landscape Radar** — Real-time map of UK health data assets, custodians, access pathways
2. **Funding Intelligence** — UKRI award tracking with outcome attribution to datasets/SDEs
3. **Capability Gap Analysis** — Phenotype coverage vs. demand, SDE infrastructure readiness
4. **Collaboration Network** — Co-authorship, co-funding, shared dataset usage graphs
5. **Competitive Positioning** — BHF DSC/HDRUK benchmarking against international peers

---

## Use Cases

### UC1: Strategic Partnership Identification
**Actor**: BHF DSC Director | **Trigger**: Quarterly review  
**Flow**: gatewayMCP cardiovascular datasets → hdrsmcp SDE hosting → phenotypelibrarymcp complementary phenotypes → gtr-ukri collaboration ranking  
**Output**: Ranked partnership shortlist with data access pathways

### UC2: Funding Opportunity Detection
**Actor**: HDRUK Programme Manager | **Trigger**: UKRI call  
**Flow**: gtr-ukri historical awards → gatewayMCP consortia datasets → hdrsmcp SDE readiness → phenotypelibrarymcp phenotype coverage  
**Output**: Bid readiness scorecard with consortium recommendations

### UC3: Data Quality Benchmarking
**Actor**: SDE Operations Lead | **Trigger**: Monthly review  
**Flow**: bhfdscdashboardmcp completeness/coverage → gatewayMCP metadata standards → phenotypelibrarymcp codelist gaps → curation prioritization  
**Output**: Data quality dashboard with remediation priorities

### UC4: Phenotype Standardization
**Actor**: Phenotype Library Curator | **Trigger**: New disease area (e.g., long COVID)  
**Flow**: phenotypelibrarymcp existing concepts → gatewayMCP publication gaps → bhfdscdashboardmcp data dictionary validation → opensafelymcp ehrQL templates  
**Output**: Standardized phenotype package with implementation guides

### UC5: OpenSAFELY Methodology Transfer
**Actor**: Methods Researcher | **Trigger**: New analytical challenge  
**Flow**: opensafelymcp similar study designs → ehrQL variables → phenotypelibrarymcp concept validation → reusable templates  
**Output**: Methodology playbook with code snippets and validation

### UC6: Competitive Horizon Scanning
**Actor**: Executive Leadership | **Trigger**: Annual planning  
**Flow**: Aggregate all MCP signals → trend analysis (funding, publications, datasets, SDEs) → gtr-ukri international benchmarking → scenario modeling  
**Output**: Strategic foresight report with investment recommendations

---

## Market Research & Positioning
**Target users**: BHF DSC/HDRUK leadership, SDE directors, programme managers, phenotype curators, methods researchers. **Pain point**: Fragmented intelligence across 6+ portals; manual scanning takes weeks, misses cross-portal signals. **Differentiator**: Only platform fusing dataset metadata, funding outcomes, phenotype coverage, SDE infrastructure, OpenSAFELY methods into one knowledge graph with 24h refresh. **Competitors**: Manual reports (slow, siloed), generic BI (no health semantics), vendor dashboards (single-portal).

## Resources Needed
| Category | Detail |
|----------|--------|
| **Technology** | 6 MCP servers, Neo4j/GraphDB, Airflow/Dagster, React/Plotly, FastAPI, GitHub Actions CI/CD |
| **Governance** | DSPT-compliant handling, API ToS adherence, query audit logs, DSC/HDRUK steering oversight |
| **People** | 1 FTE platform eng, 0.5 FTE data eng, 0.5 FTE domain analyst, 0.25 FTE IG/legal, 0.25 FTE UX |
| **Compute** | Read-only MCP APIs; graph DB (≤10M nodes); batch + ad-hoc query capacity |

## Internal / External
**Internal** to BHF DSC & HDRUK — core strategic capability. **External-facing** via controlled APIs: SDE partners consume Landscape Radar/Funding Intelligence under data-sharing agreements; phenotype outputs published openly; no raw MCP credentials leave DSC/HDRUK infra.

## 3-Month Delivery Roadmap
| Month | Milestone | Success Metric |
|-------|-----------|----------------|
| 1 | Core ingestion + graph — 6 MCP connectors, entity schema v1, daily refresh, UC1/UC2 MVP | 5/5 UC1/UC2 test queries return ranked results |
| 2 | Analytics + dashboards — gap analysis, collab networks, UC3/4/5 dashboards, alerts | 3/3 dashboards auto-refresh <24h |
| 3 | Hardening & adoption — CI/CD, DSPT evidence, UC6 horizon scan, 5 pilots onboarded | 5 pilots self-serve weekly; UC6 report delivered |

---

## Success Metrics
- **Coverage**: >90% UK health data research landscape mapped
- **Latency**: Products updated within 24h of source changes
- **Accuracy**: >95% precision on partnership/funding predictions
- **Adoption**: Monthly active users across BHF DSC, HDRUK, SDEs
- **Impact**: Measurable increase in successful collaborations and funding awards