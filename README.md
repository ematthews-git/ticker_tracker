# Ticker Tracker

A Python pipeline that collects stock ticker mentions from Reddit, analyses sentiment, and stores results in PostgreSQL. Also available is a price fetcher using yfinance, and a CLI to visualise the data.

Useful for tracking which tickers are trending across finance subreddits and spotting anomalous mention/sentiment activity.

## Features

- **Data collection**: Fetches recent posts and comments from configurable subreddits (e.g. r/pennystocks, r/Daytrading) and scans for ticker symbols.
- **Sentiment**: Uses VADER to score sentiment per post; aggregates by ticker and subreddit.
- **Price data**: Optional hourly collection of OHLCV for active tickers via yfinance.
- **CLI tools**: Interactive menus to run collection, view popular tickers, and graph mention trends.

## Tech stack

- **Python 3.8+**
- **Reddit**: PRAW
- **Database**: PostgreSQL (psycopg2)
- **Data / analysis**: pandas, numpy, VADER
- **Prices**: yfinance
- **Viz**: matplotlib
- **Scheduling**: schedule

## Setup

1. **Clone and install** (from project root):

   ```bash
   cd ticker_tracker
   python -m venv .venv
   source .venv/bin/activate   # or: .venv\Scripts\activate on Windows
   pip install -e .
   ```

2. **Environment variables**

   Create a `.env` file in the project root (see `.env.example`):

   ```env
   REDDIT_CLIENT_ID=your_reddit_client_id
   REDDIT_CLIENT_SECRET=your_reddit_client_secret
   REDDIT_USER_AGENT=your_user_agent_string
   DATABASE_URL=postgresql://user:password@host:port/dbname
   ```


3. **Database**

   Create your PostgreSQL database, then create tables by running (from project root):

   ```bash
   PYTHONPATH=src python -m storage.setup_db
   ```

4. **Valid tickers**

   A valid_tickers.json file is included in src/. It was last updated December 2025.

## Usage

Run from the **project root** so `.env` and `valid_tickers.json` are found.

- **Mention collector** (hourly at :00, or run once):

  ```bash
  ticker-tracker
  ```

- **Price collector** (hourly OHLCV for active tickers, also has backfilling options):

  ```bash
  ticker-prices
  ```

- **Data viewer / visualiser** (graphs, popular tickers, hot tickers):

  ```bash
  ticker-visualiser
  ```

## Project layout

```
src/
  app.py                 # Main scheduler: hourly Reddit mention collection
  config.py              # Env and config (subreddits, paths, DB URL)
  models.py              # Dataclasses: Post, MentionDataPoint, TickerStats, etc.
  reddit/                # PRAW client, ticker mention scanner
  storage/               # DB manager, schema (setup_db)
  analysis/              # Sentiment and mention analysis
  market/                # Price fetching (yfinance) and storage
  user_interaction/      # CLI runner and visualiser
  utils/
tests/
  test_*.py              # Unit tests (scanner, sentiment, DB, Reddit client, etc.)
run_tests.py             # Test runner (run from project root)
```

## Running tests

From the project root:

```bash
python run_tests.py
```

## License

MIT (or add your preferred license).
