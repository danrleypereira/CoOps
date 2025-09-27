# GitHub Metrics - Medallion Architecture Pipeline

This project implements a comprehensive GitHub organization metrics collection and analysis system using a **Medallion Architecture** (Bronze → Silver → Gold) for data processing.

## 🏗️ Architecture Overview

### Data Layers

- **🥉 Bronze Layer**: Raw data extracted directly from GitHub API
- **🥈 Silver Layer**: Normalized and processed analytics-ready data  
- **🥇 Gold Layer**: Executive KPIs and aggregated metrics for dashboards

### Directory Structure

```
├── data/
│   ├── bronze/          # Raw GitHub API data
│   ├── silver/          # Processed analytics data
│   ├── gold/            # Executive KPIs and visualizations
│   ├── master_registry.json    # Complete file registry
│   └── data_catalog.json       # Data documentation
├── src/
│   ├── bronze/          # Raw data extraction scripts
│   ├── silver/          # Analytics processing scripts  
│   ├── gold/            # KPI aggregation scripts
│   ├── utils/           # Shared utilities
│   ├── bronze_extract.py       # Bronze orchestrator
│   ├── silver_process.py       # Silver orchestrator
│   └── registry_manager.py     # Data registry management
└── .github/workflows/   # GitHub Actions pipelines
```

## 🚀 Quick Start

### Manual Execution

1. **Extract Bronze Layer**:
   ```bash
   python src/bronze_extract.py --token $GITHUB_TOKEN --org unb-mds
   ```

2. **Process Silver Layer**:
   ```bash
   python src/silver_process.py --org unb-mds
   ```

3. **Generate Registry**:
   ```bash
   python src/registry_manager.py
   ```

### GitHub Actions (Automated)

The pipeline automatically runs:
- **Daily at 5 AM UTC** (cron schedule)
- **On push to main branch**
- **On pull request to main branch**  
- **Manual trigger** via workflow dispatch

## 📊 Data Products

### Bronze Layer (Raw Data)
- `repositories_filtered.json` - Active organization repositories
- `members_detailed.json` - Organization member profiles
- `issues_all.json` - All issues across repositories
- `prs_all.json` - All pull requests
- `commits_all.json` - All commits with metadata
- `issue_events_all.json` - Issue/PR events and comments

### Silver Layer (Analytics)
- `members_analytics.json` - Member maturity scores and classifications
- `contribution_metrics.json` - Comprehensive contribution statistics
- `collaboration_edges.json` - User collaboration network data
- `temporal_events.json` - Time-ordered activity timeline
- `activity_heatmap.json` - Hour/day activity patterns
- `cycle_times.json` - Issue/PR resolution time analysis

### Gold Layer (Executive KPIs)
- `executive_dashboard.json` - High-level organization metrics
- `performance_tiers.json` - Member performance categorization

## 🔄 Pipeline Workflow

```mermaid
graph LR
    A[GitHub API] --> B[Bronze Extract]
    B --> C[Silver Process] 
    C --> D[Gold Aggregate]
    
    B --> B1[Raw Data Files]
    C --> C1[Analytics Files]
    D --> D1[Executive KPIs]
    
    E[GitHub Actions] --> B
    F[Daily Cron] --> E
    G[Push/PR] --> E
```

### Sequenced Execution

1. **Bronze Extraction** (`bronze-extract.yaml`)
   - Validates organization
   - Extracts raw GitHub data
   - Commits bronze files
   - Triggers Silver processing

2. **Silver Processing** (`silver-process.yaml`)
   - Processes bronze data into analytics
   - Generates member, contribution, and collaboration metrics
   - Commits silver files
   - Triggers Gold aggregation

3. **Gold Aggregation** (`gold-aggregate.yaml`)
   - Creates executive dashboard KPIs
   - Generates performance tiers
   - Commits gold files
   - Completes pipeline

## 📋 Data Registry System

The system maintains comprehensive data lineage and cataloging:

- **Master Registry** (`data/master_registry.json`): Complete file inventory with metadata
- **Data Catalog** (`data/data_catalog.json`): Documentation and usage patterns
- **Layer Registries**: Individual layer file tracking

### Registry Features

- **File tracking**: All generated files with sizes and timestamps
- **Data lineage**: Input/output relationships between layers
- **Usage patterns**: Recommended file combinations for different use cases
- **Dependency mapping**: Required execution order for scripts

## 🛠️ Configuration

### Environment Variables

- `GITHUB_TOKEN`: GitHub Personal Access Token with org read permissions
- `GITHUB_REPOSITORY_OWNER`: Target organization name (auto-detected in Actions)

### Customization

1. **Repository Filtering**: Edit `src/utils/github_api.py` → `OrganizationConfig.repo_blacklist`
2. **Metrics**: Modify individual processor scripts in `src/silver/`
3. **KPIs**: Update `gold-aggregate.yaml` workflow for custom executive metrics

## 📈 Analytics Capabilities

### Member Analytics
- Maturity scoring based on account age, repos, followers
- New vs. established member classification
- Contribution pattern analysis

### Collaboration Networks  
- Cross-repository collaboration detection
- Network centrality and hub identification
- Team collaboration density metrics

### Temporal Analysis
- Activity heatmaps by hour/day
- Contribution trends over time
- Issue/PR cycle time analysis
- Burndown and throughput metrics

### Performance Metrics
- Top contributor identification
- Performance tier classification  
- Repository activity comparison
- Cross-cutting collaboration analysis

## 🔍 Data Quality & Monitoring

- **API Rate Limiting**: Automatic handling with backoff
- **Caching**: Local cache prevents redundant API calls
- **Error Handling**: Graceful failures with detailed logging
- **Data Validation**: Size and record count verification
- **Lineage Tracking**: Complete audit trail of data transformations

## 🎯 Use Cases

### Academic Research
- Software engineering collaboration patterns
- Developer community dynamics
- Open source contribution analysis
- Team productivity metrics

### Organization Management
- Member engagement tracking
- Project health monitoring
- Resource allocation insights
- Performance trend analysis

### Dashboard Applications
- Real-time metrics visualization
- Executive reporting
- Team performance dashboards
- Temporal trend analysis

## 🔄 Migration from Legacy System

The old single-script approach (`get-bronze-data.py`) has been replaced with this modular medallion architecture. Benefits include:

- **Separation of Concerns**: Dedicated scripts for each data layer
- **Incremental Processing**: Only reprocess changed data
- **Better Error Handling**: Isolated failures don't break entire pipeline  
- **Scalability**: Easy to add new metrics and data sources
- **Maintainability**: Modular design with clear dependencies

Legacy workflows are deprecated but will redirect to the new pipeline for compatibility.

## 🤝 Contributing

1. Fork the repository to your organization
2. Ensure your organization has sufficient GitHub API permissions
3. Test changes with manual script execution before PR
4. Follow the established data layer patterns for new metrics
5. Update documentation for new data products

## 📞 Support

For issues or questions:
- Check the data registry files for debugging information
- Review GitHub Actions logs for pipeline failures
- Consult the data catalog for usage patterns
- Examine individual layer outputs for data quality issues