"""
MovieDEX Edge Case & Search Quality Testing
Tests Phase 3 (edge cases) and Phase 4 (search quality) against parquet data.
"""

import duckdb
import pandas as pd

pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 60)

con = duckdb.connect()
SILVER = "/home/jay/workspace/DataEngineX/dex-studio/examples/movie-dex/.dex/lakehouse/silver"
GOLD = "/home/jay/workspace/DataEngineX/dex-studio/examples/movie-dex/.dex/lakehouse/gold"

SM = f"'{SILVER}/silver_movies.parquet'"
SD = f"'{SILVER}/silver_directors.parquet'"
SG = f"'{SILVER}/silver_genres.parquet'"
STV = f"'{SILVER}/silver_tv.parquet'"
GTM = f"'{GOLD}/gold_top_movies.parquet'"
GMF = f"'{GOLD}/gold_movie_features.parquet'"
GGT = f"'{GOLD}/gold_genre_trends.parquet'"
GDS = f"'{GOLD}/gold_director_stats.parquet'"


def q(sql):
    return con.sql(sql).fetchdf()


def heading(n, title):
    print(f"\n{'=' * 80}")
    print(f"  {n}. {title}")
    print(f"{'=' * 80}")


# ===================================================================
# PHASE 3: EDGE CASE TESTING
# ===================================================================

heading(3.1, "Movies without ratings (NULL imdb_rating in silver_movies)")

df = q(f"SELECT count(*) as cnt FROM {SM} WHERE imdb_rating IS NULL")
null_ratings = df["cnt"][0]
total = q(f"SELECT count(*) as cnt FROM {SM}")["cnt"][0]
print(
    f"  Movies with NULL imdb_rating: {null_ratings:,} / {total:,} ({100 * null_ratings / total:.1f}%)"
)

examples = q(
    f"SELECT movie_id, title, release_year, runtime_min, genres FROM {SM} WHERE imdb_rating IS NULL LIMIT 10"
)
print("  Examples:")
for _, r in examples.iterrows():
    print(
        f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['runtime_min']}min | {r['genres']}"
    )

# Check if NULL-rating movies appear in gold tables
in_gold_top = q(f"""
    SELECT count(*) as cnt FROM {GTM} g
    WHERE g.movie_id IN (SELECT movie_id FROM {SM} WHERE imdb_rating IS NULL)
""")["cnt"][0]
in_gold_feat = q(f"""
    SELECT count(*) as cnt FROM {GMF} g
    WHERE g.movie_id IN (SELECT movie_id FROM {SM} WHERE imdb_rating IS NULL)
""")["cnt"][0]
print(f"  NULL-rating movies in gold_top_movies: {in_gold_top:,}")
print(f"  NULL-rating movies in gold_movie_features: {in_gold_feat:,}")

if in_gold_top > 0:
    print("  Examples in gold_top_movies:")
    ex2 = q(f"""
        SELECT g.movie_id, g.title, g.release_year, g.imdb_rating, g.weighted_rating, g.global_rank
        FROM {GTM} g
        WHERE g.movie_id IN (SELECT movie_id FROM {SM} WHERE imdb_rating IS NULL)
        LIMIT 10
    """)
    for _, r in ex2.iterrows():
        print(
            f"    {r['movie_id']:12s} | {r['title']:<50s} | yr={r['release_year']} | imdb={r['imdb_rating']} | weighted={r['weighted_rating']} | rank={r['global_rank']}"
        )


heading(3.2, "Movies with 0 votes")

df = q(f"SELECT count(*) as cnt FROM {SM} WHERE vote_count = 0")
zero_votes = df["cnt"][0]
print(f"  Movies with vote_count = 0: {zero_votes:,} ({100 * zero_votes / total:.1f}%)")
df2 = q(f"SELECT count(*) as cnt FROM {SM} WHERE vote_count IS NULL")
null_votes = df2["cnt"][0]
print(f"  Movies with NULL vote_count: {null_votes:,}")

examples = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, vote_count, runtime_min
    FROM {SM} WHERE vote_count = 0 ORDER BY release_year LIMIT 10
""")
print("  Examples (earliest):")
for _, r in examples.iterrows():
    print(
        f"    {r['movie_id']} | {r['title']:<50s} | {r['release_year']} | rating={r['imdb_rating']} | votes={r['vote_count']}"
    )

# What about movies with both NULL rating AND 0 votes?
both_null = q(f"""
    SELECT count(*) as cnt FROM {SM}
    WHERE imdb_rating IS NULL AND (vote_count = 0 OR vote_count IS NULL)
""")["cnt"][0]
print(f"  Movies with NULL rating AND 0/null votes: {both_null:,}")

# How does gold_top_movies handle 0-vote movies?
gold_zero = q(f"""
    SELECT count(*) as cnt FROM {GTM} g
    WHERE g.movie_id IN (SELECT movie_id FROM {SM} WHERE vote_count = 0)
""")["cnt"][0]
print(f"  0-vote movies in gold_top_movies: {gold_zero:,}")
if gold_zero > 0:
    ex2 = q(f"""
        SELECT g.movie_id, g.title, g.release_year, g.imdb_rating, g.vote_count, g.weighted_rating
        FROM {GTM} g
        WHERE g.movie_id IN (SELECT movie_id FROM {SM} WHERE vote_count = 0)
        LIMIT 5
    """)
    print("  Examples in gold:")
    for _, r in ex2.iterrows():
        print(
            f"    {r['movie_id']} | {r['title']:<50s} | yr={r['release_year']} | imdb={r['imdb_rating']} | votes={r['vote_count']} | weighted={r['weighted_rating']}"
        )


heading(3.3, "Extremely short movies (runtime < 10 min)")

df = q(f"SELECT count(*) as cnt FROM {SM} WHERE runtime_min < 10")
short = df["cnt"][0]
print(f"  Movies with runtime < 10 min: {short:,} ({100 * short / total:.1f}%)")

examples = q(f"""
    SELECT movie_id, title, release_year, runtime_min, imdb_rating, genres
    FROM {SM} WHERE runtime_min < 10 ORDER BY runtime_min LIMIT 15
""")
print("  Examples:")
for _, r in examples.iterrows():
    print(
        f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['runtime_min']:>4d}min | {r['imdb_rating']} | {str(r['genres'])[:30]}"
    )

# Do they appear in gold_top_movies?
in_gold = q(f"""
    SELECT count(*) as cnt FROM {GTM}
    WHERE movie_id IN (SELECT movie_id FROM {SM} WHERE runtime_min < 10)
""")["cnt"][0]
print(f"  Short movies in gold_top_movies: {in_gold:,}")

if in_gold > 0:
    ex2 = q(f"""
        SELECT movie_id, title, release_year, runtime_min, imdb_rating, weighted_rating, global_rank
        FROM {GTM}
        WHERE movie_id IN (SELECT movie_id FROM {SM} WHERE runtime_min < 10)
        ORDER BY global_rank LIMIT 10
    """)
    print("  Top-ranked short movies in gold:")
    for _, r in ex2.iterrows():
        print(
            f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['runtime_min']}min | imdb={r['imdb_rating']} | weighted={r['weighted_rating']} | rank={r['global_rank']}"
        )


heading(3.4, "Extremely long movies (runtime > 500 min)")

df = q(f"SELECT count(*) as cnt FROM {SM} WHERE runtime_min > 500")
long_cnt = df["cnt"][0]
print(f"  Movies with runtime > 500 min: {long_cnt:,} ({100 * long_cnt / total:.3f}%)")
df2 = q(f"SELECT count(*) as cnt FROM {SM} WHERE runtime_min IS NULL")
null_runtime = df2["cnt"][0]
print(f"  Movies with NULL runtime: {null_runtime:,} ({100 * null_runtime / total:.1f}%)")

examples = q(f"""
    SELECT movie_id, title, release_year, runtime_min, imdb_rating, genres
    FROM {SM} WHERE runtime_min > 500 ORDER BY runtime_min DESC LIMIT 15
""")
print("  Longest movies:")
for _, r in examples.iterrows():
    print(
        f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['runtime_min']:>4d}min | {r['imdb_rating']}"
    )

# Check max runtime
max_rt = q(f"SELECT max(runtime_min) as max_rt FROM {SM}")["max_rt"][0]
print(f"  Max runtime: {max_rt} min ({max_rt / 60:.1f} hours)")


heading(3.5, "Movies with no genres")

no_genres_silver = q(f"""
    SELECT count(*) as cnt FROM {SM}
    WHERE genres IS NULL OR TRIM(genres) = ''
""")["cnt"][0]
print(
    f"  Movies with NULL/empty genres in silver: {no_genres_silver:,} ({100 * no_genres_silver / total:.2f}%)"
)

examples = q(f"""
    SELECT movie_id, title, release_year, runtime_min, imdb_rating, genres
    FROM {SM} WHERE genres IS NULL OR TRIM(genres) = ''
    LIMIT 10
""")
print("  Examples:")
for _, r in examples.iterrows():
    print(f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | '{r['genres']}'")

# Are they in gold_tables?
in_gold = q(f"""
    SELECT count(*) as cnt FROM {GTM}
    WHERE movie_id IN (SELECT movie_id FROM {SM} WHERE genres IS NULL OR TRIM(genres) = '')
""")["cnt"][0]
print(f"  Genre-less movies in gold_top_movies: {in_gold:,}")


heading(3.6, "Future movies (release_year > 2025)")

df = q(f"SELECT count(*) as cnt FROM {SM} WHERE release_year > 2025")
future = df["cnt"][0]
print(f"  Future movies (year > 2025): {future:,}")

if future > 0:
    examples = q(f"""
        SELECT movie_id, title, release_year, imdb_rating, genres
        FROM {SM} WHERE release_year > 2025 ORDER BY release_year LIMIT 15
    """)
    for _, r in examples.iterrows():
        print(
            f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']} | {str(r['genres'])[:30]}"
        )

# Check gold tables
in_gold = q(f"""
    SELECT count(*) as cnt FROM {GTM} WHERE release_year > 2025
""")["cnt"][0]
print(f"  Future movies in gold_top_movies: {in_gold:,}")

# What's the max year?
max_yr = q(f"SELECT max(release_year) as my FROM {SM}")["my"][0]
min_yr = q(f"SELECT min(release_year) as my FROM {SM}")["my"][0]
print(f"  Year range in silver_movies: {min_yr} - {max_yr}")


heading(3.7, "Old movies (before 1900)")

df = q(f"SELECT count(*) as cnt FROM {SM} WHERE release_year < 1900 AND release_year IS NOT NULL")
old = df["cnt"][0]
print(f"  Movies before 1900: {old:,} ({100 * old / total:.3f}%)")

if old > 0:
    examples = q(f"""
        SELECT movie_id, title, release_year, runtime_min, imdb_rating, genres
        FROM {SM} WHERE release_year < 1900 ORDER BY release_year LIMIT 10
    """)
    print("  Oldest movies:")
    for _, r in examples.iterrows():
        print(
            f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['runtime_min']}min | {r['imdb_rating']}"
        )

df2 = q(f"SELECT count(*) as cnt FROM {SM} WHERE release_year IS NULL")
null_yr = df2["cnt"][0]
print(f"  NULL release_year: {null_yr:,}")


heading(3.8, "Single-genre vs multi-genre distribution")

df = q(f"""
    SELECT
        genres,
        CASE
            WHEN genres IS NULL OR TRIM(genres) = '' THEN 'no genres'
            WHEN LENGTH(genres) - LENGTH(REPLACE(genres, ',', '')) = 0 THEN '1 genre'
            WHEN LENGTH(genres) - LENGTH(REPLACE(genres, ',', '')) = 1 THEN '2 genres'
            WHEN LENGTH(genres) - LENGTH(REPLACE(genres, ',', '')) = 2 THEN '3 genres'
            ELSE '4+ genres'
        END as genre_count_label,
        count(*) as cnt
    FROM {SM}
    GROUP BY genres, genre_count_label
    ORDER BY cnt DESC
""")
# Aggregate properly
df2 = q(f"""
    SELECT
        CASE
            WHEN genres IS NULL OR TRIM(genres) = '' THEN 'no genres'
            WHEN LENGTH(genres) - LENGTH(REPLACE(genres, ',', '')) = 0 THEN '1 genre'
            WHEN LENGTH(genres) - LENGTH(REPLACE(genres, ',', '')) = 1 THEN '2 genres'
            WHEN LENGTH(genres) - LENGTH(REPLACE(genres, ',', '')) = 2 THEN '3 genres'
            ELSE '4+ genres'
        END as genre_count_label,
        count(*) as cnt
    FROM {SM}
    GROUP BY genre_count_label
    ORDER BY cnt DESC
""")
print("  Genre count distribution:")
for _, r in df2.iterrows():
    pct = 100 * r["cnt"] / total
    print(f"    {r['genre_count_label']:15s}: {r['cnt']:>8,d} ({pct:5.1f}%)")

# Top 10 most common single genres
single_genres = q(f"""
    SELECT genre, count(*) as cnt
    FROM {SG}
    GROUP BY genre
    ORDER BY cnt DESC
    LIMIT 10
""")
print("\n  Most common genres (silver_genres):")
for _, r in single_genres.iterrows():
    print(f"    {r['genre']:20s}: {r['cnt']:>8,d}")


heading(3.9, "Missing directors in gold_top_movies")

df = q(f"""
    SELECT
        count(*) as total,
        sum(CASE WHEN director_name IS NULL THEN 1 ELSE 0 END) as null_director,
        sum(CASE WHEN director_name = '' THEN 1 ELSE 0 END) as empty_director
    FROM {GTM}
""")
null_dir = df["null_director"][0]
empty_dir = df["empty_director"][0]
gtm_total = df["total"][0]
print(f"  gold_top_movies total: {gtm_total:,}")
print(f"  NULL director_name: {null_dir:,} ({100 * null_dir / gtm_total:.1f}%)")
print(f"  Empty director_name: {empty_dir:,} ({100 * empty_dir / gtm_total:.1f}%)")

if null_dir > 0:
    examples = q(f"""
        SELECT movie_id, title, release_year, imdb_rating, director_name, director_id, global_rank
        FROM {GTM}
        WHERE director_name IS NULL
        ORDER BY global_rank
        LIMIT 10
    """)
    print("  Top-ranked movies with NULL director:")
    for _, r in examples.iterrows():
        print(
            f"    {r['movie_id']:12s} | {r['title']:<50s} | rank={r['global_rank']} | dir='{r['director_name']}'"
        )


heading(3.10, "Duplicate movie_ids across tables")

# In silver_movies
dup_silver = q(f"""
    SELECT movie_id, count(*) as cnt FROM {SM}
    GROUP BY movie_id HAVING count(*) > 1
    ORDER BY cnt DESC
""")
print(f"  Duplicate movie_ids in silver_movies: {len(dup_silver):,}")
if len(dup_silver) > 0:
    print("  Top duplicates:")
    for _, r in dup_silver.head(10).iterrows():
        print(f"    {r['movie_id']:12s}: {r['cnt']}x")

# In gold_top_movies
dup_gold = q(f"""
    SELECT movie_id, count(*) as cnt FROM {GTM}
    GROUP BY movie_id HAVING count(*) > 1
    ORDER BY cnt DESC
""")
print(f"  Duplicate movie_ids in gold_top_movies: {len(dup_gold):,}")

# Cross-table: movie_ids in gold but not in silver
gold_not_silver = q(f"""
    SELECT count(*) as cnt FROM {GTM}
    WHERE movie_id NOT IN (SELECT movie_id FROM {SM})
""")["cnt"][0]
print(f"  gold_top_movies movie_ids NOT in silver_movies: {gold_not_silver:,}")

silver_not_gold = q(f"""
    SELECT count(*) as cnt FROM {SM}
    WHERE movie_id NOT IN (SELECT movie_id FROM {GTM})
""")["cnt"][0]
print(f"  silver_movies movie_ids NOT in gold_top_movies: {silver_not_gold:,}")

# Check if gold_movie_features has the same movie_ids as gold_top_movies
feat_not_top = q(f"""
    SELECT count(*) as cnt FROM {GMF}
    WHERE movie_id NOT IN (SELECT movie_id FROM {GTM})
""")["cnt"][0]
top_not_feat = q(f"""
    SELECT count(*) as cnt FROM {GTM}
    WHERE movie_id NOT IN (SELECT movie_id FROM {GMF})
""")["cnt"][0]
print(f"  gold_movie_features IDs not in gold_top_movies: {feat_not_top:,}")
print(f"  gold_top_movies IDs not in gold_movie_features: {top_not_feat:,}")


heading(3.11, "Rating outliers (absurdly high or low)")

# High
high = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, vote_count
    FROM {SM}
    WHERE imdb_rating IS NOT NULL
    ORDER BY imdb_rating DESC
    LIMIT 20
""")
print("  Highest rated movies (silver):")
for _, r in high.iterrows():
    print(
        f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']:5.1f} | {r['vote_count']:>8,d} votes"
    )

# Low (non-zero votes)
low = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, vote_count
    FROM {SM}
    WHERE imdb_rating IS NOT NULL AND vote_count > 0
    ORDER BY imdb_rating
    LIMIT 20
""")
print("\n  Lowest rated movies with votes (silver):")
for _, r in low.iterrows():
    print(
        f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']:5.1f} | {r['vote_count']:>8,d} votes"
    )

# Rating distribution bucketed
rating_dist = q(f"""
    SELECT
        CASE
            WHEN imdb_rating IS NULL THEN 'NULL'
            WHEN imdb_rating < 1.0 THEN '< 1.0'
            WHEN imdb_rating < 2.0 THEN '1.0-1.9'
            WHEN imdb_rating < 3.0 THEN '2.0-2.9'
            WHEN imdb_rating < 4.0 THEN '3.0-3.9'
            WHEN imdb_rating < 5.0 THEN '4.0-4.9'
            WHEN imdb_rating < 6.0 THEN '5.0-5.9'
            WHEN imdb_rating < 7.0 THEN '6.0-6.9'
            WHEN imdb_rating < 8.0 THEN '7.0-7.9'
            WHEN imdb_rating < 9.0 THEN '8.0-8.9'
            ELSE '9.0+'
        END as rating_bucket,
        count(*) as cnt
    FROM {SM}
    GROUP BY rating_bucket
    ORDER BY cnt DESC
""")
print("\n  Rating distribution:")
for _, r in rating_dist.iterrows():
    pct = 100 * r["cnt"] / total
    print(f"    {r['rating_bucket']:10s}: {r['cnt']:>8,d} ({pct:5.1f}%)")


heading(3.12, "TV shows misclassified as movies")

# The silver_movies table doesn't have a titleType column. Check if there are
# entries that look like TV shows (series naming patterns, or check silver_tv)
common_tv_titles = q(f"""
    SELECT m.movie_id, m.title, m.release_year
    FROM {SM} m
    INNER JOIN {STV} t ON LOWER(TRIM(m.title)) = LOWER(TRIM(t.title))
    LIMIT 20
""")
print(
    f"  Movies in silver_movies that also appear by title in silver_tv: {len(common_tv_titles):,}"
)
if len(common_tv_titles) > 0:
    print("  Examples:")
    for _, r in common_tv_titles.iterrows():
        print(f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']}")

# ALL movies in gold_top_movies vs silver_tv by title
gold_tv_overlap = q(f"""
    SELECT count(*) as cnt FROM {GTM} g
    WHERE LOWER(TRIM(g.title)) IN (SELECT LOWER(TRIM(title)) FROM {STV})
""")["cnt"][0]
print(f"\n  gold_top_movies entries with matching title in silver_tv: {gold_tv_overlap:,}")

# Check for specific TV-like patterns in silver_movies titles
tv_patterns = q(f"""
    SELECT movie_id, title, release_year, imdb_rating
    FROM {SM}
    WHERE
        title ILIKE '%(TV%' OR
        title ILIKE '%(Video%' OR
        title ILIKE '%- %' OR
        title ILIKE '%episode%' OR
        title ILIKE '%season%'
    ORDER BY release_year
    LIMIT 20
""")
print("\n  Movies with TV-like title patterns:")
for _, r in tv_patterns.iterrows():
    print(f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']}")

tv_pattern_count = q(f"""
    SELECT count(*) as cnt FROM {SM}
    WHERE
        title ILIKE '%(TV%' OR
        title ILIKE '%(Video%' OR
        title ILIKE '%- %' OR
        title ILIKE '%episode%' OR
        title ILIKE '%season%'
""")["cnt"][0]
print(f"  Total with TV-like patterns: {tv_pattern_count:,}")

# Check gold_top_movies for the same
gold_tv_patterns = q(f"""
    SELECT count(*) as cnt FROM {GTM}
    WHERE
        title ILIKE '%(TV%' OR
        title ILIKE '%(Video%' OR
        title ILIKE '%- %' OR
        title ILIKE '%episode%' OR
        title ILIKE '%season%'
""")["cnt"][0]
print(f"  gold_top_movies with TV-like patterns: {gold_tv_patterns:,}")


# ===================================================================
# PHASE 4: SEARCH TESTING
# ===================================================================

heading(4.1, "Exact title search: 'The Matrix'")

# In silver_movies
results = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, vote_count
    FROM {SM}
    WHERE LOWER(TRIM(title)) = 'the matrix'
    ORDER BY release_year
""")
print(f"  Exact 'The Matrix' in silver_movies: {len(results):,} results")
for _, r in results.iterrows():
    print(
        f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']} | {r['vote_count']:,} votes"
    )

# In gold_top_movies
results_gold = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, weighted_rating, global_rank
    FROM {GTM}
    WHERE LOWER(TRIM(title)) = 'the matrix'
    ORDER BY global_rank
""")
print(f"  Exact 'The Matrix' in gold_top_movies: {len(results_gold):,} results")
for _, r in results_gold.iterrows():
    print(
        f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | imdb={r['imdb_rating']} | weighted={r['weighted_rating']} | rank={r['global_rank']}"
    )


heading(4.2, "Fuzzy title search: 'matrx' (misspelled)")

results = q(f"""
    SELECT movie_id, title, release_year, imdb_rating
    FROM {SM}
    WHERE LOWER(TRIM(title)) LIKE '%matrx%'
    ORDER BY release_year
""")
print(f"  Fuzzy 'matrx': {len(results):,} results (IMDb SQL has NO fuzzy matching)")
for _, r in results.iterrows():
    print(f"    {r['movie_id']} | {r['title']:<50s} | {r['release_year']}")

# Also check a common misspelling
for typo in ["matrx", "the matrx", "matix", "the matix", "shwashank", "shawshnak"]:
    cnt = q(f"""
        SELECT count(*) as cnt FROM {SM}
        WHERE LOWER(TRIM(title)) LIKE '%{typo}%'
    """)["cnt"][0]
    if cnt > 0:
        print(f"  '{typo}' matches: {cnt}")
        ex = q(
            f"SELECT title, release_year FROM {SM} WHERE LOWER(TRIM(title)) LIKE '%{typo}%' LIMIT 3"
        )
        for _, r in ex.iterrows():
            print(f"    -> {r['title']} ({r['release_year']})")


heading(4.3, "Partial match: 'Matrix'")

results = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, vote_count
    FROM {SM}
    WHERE LOWER(TRIM(title)) LIKE '%matrix%'
    ORDER BY release_year
""")
print(f"  Partial 'Matrix': {len(results):,} results")
for _, r in results.head(15).iterrows():
    print(
        f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']} | {r['vote_count']:,}"
    )

# Now check gold_top_movies
results_gold = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, global_rank
    FROM {GTM}
    WHERE LOWER(TRIM(title)) LIKE '%matrix%'
    ORDER BY global_rank
""")
print(f"\n  Partial 'Matrix' in gold_top_movies: {len(results_gold):,} results")
for _, r in results_gold.head(10).iterrows():
    print(
        f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']} | rank={r['global_rank']}"
    )


heading(4.4, "Acronym search: 'LOTR'")

for acronym in ["lotr", "star wars", "sw"]:
    results = q(f"""
        SELECT movie_id, title, release_year, imdb_rating
        FROM {SM}
        WHERE LOWER(TRIM(title)) LIKE '%{acronym}%'
        ORDER BY release_year
    """)
    print(f"  '{acronym}' -> {len(results):,} results")
    if len(results) > 0:
        for _, r in results.head(5).iterrows():
            print(f"    {r['title']:<50s} | {r['release_year']}")
    else:
        print("    (no results - acronyms don't work directly)")

# Check if "Lord of the Rings" is findable
lotr = q(f"""
    SELECT movie_id, title, release_year, imdb_rating
    FROM {SM}
    WHERE LOWER(TRIM(title)) LIKE '%lord%rings%' OR LOWER(TRIM(title)) LIKE '%lord of the rings%'
    ORDER BY release_year
""")
print(f"\n  'Lord of the Rings' search: {len(lotr):,} results")
for _, r in lotr.iterrows():
    print(f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']}")


heading(4.5, "Actor-based search: 'Tom Hanks movies'")

# Silver_directors only has directors, so let's check what actors info exists.
# IMDb titles have actors in a separate table. Let's see if there's any actor data.
# For now, simulate via SQL: find movies directed by Tom Hanks and see what's possible.

tom_hanks_directed = q(f"""
    SELECT m.movie_id, m.title, m.release_year, m.imdb_rating
    FROM {SM} m
    INNER JOIN {SD} d ON m.movie_id = d.movie_id
    WHERE LOWER(TRIM(d.director_name)) LIKE '%tom hanks%'
    ORDER BY m.release_year
""")
print(f"  Movies directed by Tom Hanks: {len(tom_hanks_directed)}")
for _, r in tom_hanks_directed.iterrows():
    print(f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']}")

# Actor data check - silver_movies has no actor info, so actor search isn't possible.
print(
    "\n  NOTE: silver_movies has NO actor column. Actor-based search is NOT possible with current schema."
)
print("  The data pipeline would need a silver_actors or bronze_actors table for this.")


heading(4.6, "Genre + Year filter: 'sci-fi movies 1990s'")

results = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, vote_count, genres
    FROM {SM}
    WHERE
        release_year >= 1990 AND release_year <= 1999
        AND LOWER(TRIM(genres)) LIKE '%sci-fi%'
        AND imdb_rating IS NOT NULL
    ORDER BY imdb_rating DESC
""")
print(f"  Sci-fi movies from 1990s: {len(results):,} results")
print("  Top 15 by rating:")
for _, r in results.head(15).iterrows():
    print(
        f"    {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']} | {r['vote_count']:,} votes"
    )

# Same in gold_top_movies
results_gold = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, global_rank, genres
    FROM {GTM}
    WHERE release_year >= 1990 AND release_year <= 1999
    AND LOWER(TRIM(genres)) LIKE '%sci-fi%'
    ORDER BY global_rank
""")
print(f"\n  Gold top (ranked): {len(results_gold):,}")
for _, r in results_gold.head(10).iterrows():
    print(
        f"    r#{r['global_rank']:>5d} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']}"
    )


heading(4.7, "Runtime filter: 'movies under 90 minutes'")

results = q(f"""
    SELECT movie_id, title, release_year, runtime_min, imdb_rating, vote_count, genres
    FROM {SM}
    WHERE runtime_min < 90 AND runtime_min > 0
    AND imdb_rating IS NOT NULL
    ORDER BY imdb_rating DESC
""")
print(f"  Movies under 90 min: {len(results):,} results")
print("  Top 15 by rating:")
for _, r in results.head(15).iterrows():
    print(
        f"    {r['title']:<50s} | {r['release_year']} | {r['runtime_min']}min | {r['imdb_rating']} | {r['vote_count']:,}"
    )

# What about very short but highly rated?
short_high = q(f"""
    SELECT movie_id, title, release_year, runtime_min, imdb_rating, vote_count
    FROM {SM}
    WHERE runtime_min < 30 AND imdb_rating > 8.0
    ORDER BY imdb_rating DESC
""")
print(f"\n  Highly rated (>8.0) under 30 min: {len(short_high):,}")
for _, r in short_high.head(10).iterrows():
    print(
        f"    {r['title']:<50s} | {r['runtime_min']}min | {r['imdb_rating']} | {r['vote_count']:,}"
    )


heading(4.8, "Genre + Rating: 'best horror movies'")

results = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, vote_count, genres
    FROM {SM}
    WHERE LOWER(TRIM(genres)) LIKE '%horror%'
    AND imdb_rating IS NOT NULL
    ORDER BY imdb_rating DESC
""")
print(f"  Horror movies (by rating desc): {len(results):,}")
print("  Top 15:")
for _, r in results.head(15).iterrows():
    print(
        f"    {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']} | {r['vote_count']:,} votes | {str(r['genres'])[:40]}"
    )

# Weighted by votes for better quality
results_weighted = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, vote_count, genres
    FROM {SM}
    WHERE LOWER(TRIM(genres)) LIKE '%horror%'
    AND imdb_rating IS NOT NULL AND vote_count > 10000
    ORDER BY imdb_rating DESC
""")
print(f"\n  Horror movies (rating desc, >10K votes): {len(results_weighted):,}")
for _, r in results_weighted.head(10).iterrows():
    print(
        f"    {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']} | {r['vote_count']:,} votes"
    )

# In gold_top_movies
results_gold = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, global_rank, genres
    FROM {GTM}
    WHERE LOWER(TRIM(genres)) LIKE '%horror%'
    ORDER BY global_rank
""")
print(f"\n  Horror in gold_top_movies: {len(results_gold):,}")
for _, r in results_gold.head(10).iterrows():
    print(
        f"    r#{r['global_rank']:>5d} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']}"
    )


heading(4.9, "Multi-word title: 'Lord of the Rings'")

# Exact match
exact = q(f"""
    SELECT movie_id, title, release_year, imdb_rating
    FROM {SM}
    WHERE LOWER(TRIM(title)) = 'the lord of the rings'
""")
print(f"  Exact 'The Lord of the Rings': {len(exact):,} results")
for _, r in exact.iterrows():
    print(f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']}")

# Partial match
partial = q(f"""
    SELECT movie_id, title, release_year, imdb_rating
    FROM {SM}
    WHERE LOWER(TRIM(title)) LIKE '%lord of the rings%'
    ORDER BY release_year
""")
print(f"  Partial '%lord of the rings%': {len(partial):,} results")
for _, r in partial.iterrows():
    print(f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']}")

# Gold top
partial_gold = q(f"""
    SELECT movie_id, title, release_year, imdb_rating, global_rank
    FROM {GTM}
    WHERE LOWER(TRIM(title)) LIKE '%lord of the rings%'
    ORDER BY global_rank
""")
print(f"\n  In gold_top_movies: {len(partial_gold):,}")
for _, r in partial_gold.iterrows():
    print(
        f"    r#{r['global_rank']:>5d} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']}"
    )

# Check if "Fellowship of the Ring" also appears as separate search
fellowship = q(f"""
    SELECT movie_id, title, release_year, imdb_rating
    FROM {SM}
    WHERE LOWER(TRIM(title)) LIKE '%fellowship%'
""")
print(f"\n  'Fellowship' search: {len(fellowship):,} results")
for _, r in fellowship.iterrows():
    print(f"    {r['movie_id']:12s} | {r['title']:<50s} | {r['release_year']} | {r['imdb_rating']}")


# ===================================================================
# SUMMARY
# ===================================================================
print(f"\n{'=' * 80}")
print("  SUMMARY OF FINDINGS")
print(f"{'=' * 80}")

null_rating_gold_in_top = q(f"""
    SELECT count(*) as cnt FROM {GTM}
    WHERE movie_id IN (SELECT movie_id FROM {SM} WHERE imdb_rating IS NULL)
""")["cnt"][0]

print(f"""
  EDGE CASES:
    Movies with NULL ratings:          {null_ratings:>8,d} / {total:,} ({100 * null_ratings / total:.1f}%)
    NULL-ratings in gold_top_movies:   {null_rating_gold_in_top:>8,d}
    Movies with 0 votes:               {zero_votes:>8,d} ({100 * zero_votes / total:.1f}%)
    Runtime < 10 min:                  {short:>8,d} ({100 * short / total:.1f}%)
    Runtime > 500 min:                 {long_cnt:>8,d} ({100 * long_cnt / total:.3f}%)
    NULL runtime:                      {null_runtime:>8,d}
    Movies with no genres:             {no_genres_silver:>8,d} ({100 * no_genres_silver / total:.2f}%)
    Future movies (>2025):              {future:>8,d}
    Movies before 1900:                {old:>8,d}
    NULL release_year:                 {null_yr:>8,d}
    NULL directors in gold_top_movies: {null_dir:>8,d} ({100 * null_dir / gtm_total:.1f}%)
    Duplicate IDs in silver_movies:    {len(dup_silver):>8,d}
    Duplicate IDs in gold_top_movies:  {len(dup_gold):>8,d}
    TV-like patterns in silver:        {tv_pattern_count:>8,d}
    TV-like patterns in gold_top:      {gold_tv_patterns:>8,d}
""")
