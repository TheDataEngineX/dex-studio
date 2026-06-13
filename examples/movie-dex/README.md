# MovieDEX

> End-to-end movie intelligence platform built on the **IMDB Non-Commercial Dataset**.
> Powers a full data engineering flow — from raw TSV ingest to ML-driven recommendations
> and AI agents — entirely on your local machine.

______________________________________________________________________

## What this project does

| Stage | What happens | Key outputs |
|---|---|---|
| **Ingest** | Download 5 IMDB TSV.gz files via `setup.py` | `data/raw/*.parquet` |
| **Bronze** | Null-filter, load raw IMDB into lakehouse | `bronze_titles`, `bronze_ratings`, `bronze_crew`, `bronze_names`, `bronze_principals` |
| **Silver** | Clean, type-cast, join ratings to titles, normalise genres | `silver_movies`, `silver_tv`, `silver_directors`, `silver_cast`, `silver_genres` |
| **Gold** | BI-ready aggregates + ML feature table | `gold_top_movies`, `gold_genre_trends`, `gold_director_stats`, `gold_actor_network`, `gold_movie_features` |
| **ML** | Rating prediction, content-based recommender, decade classifier | Tracked experiments in DEX Studio |
| **AI** | Three agents backed by the gold layer | `movie_recommender`, `data_analyst`, `casting_expert` |

______________________________________________________________________

## Dataset

**Source:** [IMDB Non-Commercial Datasets](https://developer.imdb.com/non-commercial-datasets/)
**Licence:** Non-commercial personal and research use only.

| File | Rows | Compressed |
|---|---|---|
| `title.basics.tsv.gz` | ~10 M | ~150 MB |
| `title.ratings.tsv.gz` | ~1.4 M | ~25 MB |
| `title.crew.tsv.gz` | ~10 M | ~150 MB |
| `name.basics.tsv.gz` | ~13 M | ~250 MB |
| `title.principals.tsv.gz` | ~60 M | ~700 MB |

Total download: **~1.3 GB** compressed → **~3 GB** as Parquet.

Quick mode (`--quick`) skips `title_principals` (~700 MB). All pipelines except
`silver_cast` and `gold_actor_network` run fine without it.

______________________________________________________________________

## Quick start

```bash
# 1. Install prerequisites
pip install dataenginex duckdb

# 2. Download IMDB data (quick mode — skips large principals file)
python setup.py --quick

# 3. Validate config
dex validate dex.yaml

# 4. Open in DEX Studio
# Point DEX Studio to this dex.yaml via the onboarding screen, then:
#   /data/pipelines → Run all bronze_* pipelines
#   /data/pipelines → Run all silver_* pipelines
#   /data/pipelines → Run all gold_* pipelines

# 5. Run an ML experiment
#   ML → Experiments → rating_predictor → Run

# 6. Chat with an agent
#   /ai/playground → movie_recommender
```

______________________________________________________________________

## Pipeline execution order

Bronze pipelines are independent and can run in parallel.
Silver pipelines depend on bronze. Gold pipelines depend on silver.

```
bronze_titles  ─┐
bronze_ratings  ─┼──→  silver_movies  ─┬──→ silver_genres  ──→ gold_genre_trends
bronze_crew     ─┼──→  silver_tv       │
bronze_names    ─┼──→  silver_directors─┤──→ gold_director_stats ──┐
                 │                      │                            │
bronze_principals┘──→  silver_cast ────┤──→ gold_actor_network     │
                                       │                            │
                                       └──→ gold_top_movies         │
                                       └──→ gold_movie_features ────┘
```

______________________________________________________________________

## ML experiments

### `rating_predictor`

Predicts IMDB rating from structural features — no text, no posters. Useful for
surfacing likely-good films before they accumulate many votes.

- **Target:** `target_rating` (continuous, 1–10)
- **Algorithm:** Random Forest Regressor
- **Features:** year, runtime, log(votes), genre one-hot flags (14 genres), director quality signal
- **Why it's interesting:** a newly-released film with 500 votes can have its eventual
  rating predicted within ±0.6 from genre + director history alone

### `content_recommender`

k-NN cosine similarity in genre + director feature space. Given a movie the user
liked, returns the k most similar by feature-space proximity.

- **Target:** `target_rating` (used for quality filtering of results)
- **Algorithm:** k-NN with cosine metric (k=20)
- **Use case:** "I liked The Prestige — what else should I watch?"

### `decade_classifier`

Classifies which decade a film is from using only genre + rating signals.
Reveals how genre tastes have evolved across 12 decades of cinema.

- **Target:** `decade` (1900s–2020s)
- **Algorithm:** Random Forest Classifier
- **Why it's interesting:** Horror peaked in the 1980s, Drama dominates in every era,
  Sci-Fi exploded post-1970s — the classifier learns this from data

______________________________________________________________________

## AI agents

### `movie_recommender`

Chat-based recommendations powered by `gold_top_movies` and `silver_movies`.
Can find hidden gems (high weighted_rating, low vote count), compare directors,
or suggest films similar to one the user already loves.

**Try:** *"Recommend 5 underrated crime films from the 1970s"*

### `data_analyst`

SQL-powered Q&A over the gold layer. Answers industry questions with exact numbers
and cites its SQL so you can extend or verify it.

**Try:** *"Which genre had the highest average rating in the 1990s?"*
**Try:** *"Show me the top 10 directors by average film quality with at least 5 films"*

### `casting_expert`

Traverses `silver_cast` and `silver_directors` to find people and connections.

**Try:** *"List every film where both Morgan Freeman and Tom Hanks appeared"*
**Try:** *"Show Christopher Nolan's full filmography ordered by IMDB rating"*

______________________________________________________________________

## Warehouse tables (gold layer)

| Table | Description | Key columns |
|---|---|---|
| `gold_top_movies` | All rated movies with Bayesian weighted rating | `weighted_rating`, `global_rank`, `decade_rank` |
| `gold_genre_trends` | Genre × decade popularity matrix | `popularity_index`, `avg_rating`, `movie_count` |
| `gold_director_stats` | Director career stats | `avg_rating`, `movies_directed`, `career_span_years` |
| `gold_actor_network` | Actor career stats | `avg_movie_rating`, `movies_appeared`, `total_audience_votes` |
| `gold_movie_features` | ML-ready feature table | 14 genre flags, normalised continuous features |

All tables queryable in the **SQL Console** and by AI agents.

______________________________________________________________________

## Drift monitoring

DEX monitors three gold-layer signals daily:

- **`target_rating`** — has the average quality of newly-rated films shifted?
- **`log_votes_norm`** — is audience engagement growing or shrinking?
- **`year_norm`** — are more old or new films entering the rated pool?

PSI threshold: **0.15** (flags if population shift index exceeds this).

______________________________________________________________________

## File layout

```
movie-dex/
├── dex.yaml          # full project config (sources, pipelines, ML, AI)
├── setup.py          # download + convert IMDB TSV → Parquet
├── README.md         # this file
└── data/
    └── raw/          # IMDB parquet files (created by setup.py)
        ├── title_basics.parquet
        ├── title_ratings.parquet
        ├── title_crew.parquet
        ├── name_basics.parquet
        └── title_principals.parquet
```
