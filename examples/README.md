# DataEngineX Examples

Ready-to-use example projects demonstrating DataEngineX features end-to-end.

## Available Examples

### MovieDEX

A movie recommendation engine showcasing:

- Data pipelines with CSV sources (movies, ratings, credits)
- Silver/Gold medallion architecture
- Genre analysis with SQL transforms
- ML experiments with scikit-learn
- AI agents (movie expert, data assistant)
- Ollama LLM integration with RAG

**Location:** `examples/movie-dex/`

**Quick start:**

```bash
cd examples/movie-dex
dex pipeline run load_movies
dex pipeline run process_ratings
dex pipeline run load_credits
dex pipeline run genre_analysis
```

### E-Commerce (ShopMetrics)

A full-stack e-commerce analytics platform demonstrating:

- Customer, product, and order data pipelines
- Data quality gates (completeness, uniqueness)
- Medallion architecture (silver/gold layers)
- Customer revenue and product performance analytics
- ML churn prediction
- Drift monitoring
- AI analytics assistant

**Location:** `examples/ecommerce/`

**Quick start:**

```bash
cd examples/ecommerce
python run_all.py
```

## Example Structure

Each example follows this structure:

```
example-name/
├── dex.yaml          # DataEngineX configuration
├── data/             # CSV data files
├── .dex/             # Runtime artifacts (lakehouse, tracking)
└── README.md         # (optional) Example-specific docs
```

## Using Examples as Starter Projects

These examples are designed to be:

1. **Ready to run** - All data included, configs validated
1. **Feature-complete** - Demonstrate data pipelines, ML, AI agents
1. **Easy to modify** - Clear, clean configuration files
1. **Learning resources** - Well-documented patterns to follow

To create your own project from an example:

```bash
cp -r examples/movie-dex my-project
cd my-project
# Edit dex.yaml with your data sources
# Add your CSV files to data/
dex pipeline list
```
