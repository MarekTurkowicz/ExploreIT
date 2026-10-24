# ExploreIT

A research project on web structure exploration. ExploreIT crawls websites, models them
as a link graph, stores page content and analyses how crawl parameters affect the results.

## Features
- Breadth-first and depth-first crawling within a subtree, a single server or the open web
- Link graph with structural statistics (depth, out/in-degree, pages per level)
- Content extraction (URL, title, description, keywords, body) to CSV and SQLite
- Comparison of datasets produced with different crawl settings
- Link graph drawn in the app (by level or force-directed), exported as interactive HTML
  or GEXF for Gephi
- Desktop application (Tkinter) and a command line for scripted experiments

## Requirements
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or plain `venv` + `pip`

## Installation
Both options create a standard virtual environment in `.venv/`.

```bash
# uv
uv sync

# or venv + pip
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e . --group dev        # pip >= 25.1
```

## Usage
Desktop application: set up a crawl, watch it run, explore the link graph, run
parameter experiments and compare content databases.
```bash
exploreit ui
```

Command line:
```bash
exploreit crawl https://example.com --strategy bfs --scope server --links hyperlinks \
    --max-depth 3 --max-pages 100 -o data/crawl.json
exploreit stats data/crawl.json
exploreit graph data/crawl.json --open --gexf   # interactive HTML graph, GEXF for Gephi
exploreit plots data/crawl.json                 # PNG charts: pages per level, links per page

# Every strategy × scope × link mode combination, a CSV summary and a comparison chart
exploreit experiment https://example.com --max-pages 50 -o data/experiments
exploreit summarize data/experiments

# Page content: title, meta description, meta keywords and body text
exploreit crawl https://example.com --scope web --max-depth 2 --content -o data/a.json
exploreit store data/a.json --field url --field keywords --separator ";" --sqlite
exploreit diff data/a.json data/b.json      # compare two content databases
exploreit --help
```

| Option | Values | Meaning |
|---|---|---|
| `--strategy` | `bfs`, `dfs` | breadth-first or depth-first traversal |
| `--scope` | `subtree`, `server`, `web` | stay under the start path, on the start host, or go anywhere |
| `--links` | `hyperlinks`, `images`, `all` | follow `<a>` links, also images, or every linked resource |

## Development
With `.venv` activated, the `uv run` prefix can be omitted.

```bash
uv run pytest                                  # tests
uv run ruff check . && uv run ruff format .    # lint and format
uv run mypy                                    # type checking
```

## Project layout
```
src/exploreit/   application package
tests/           test suite (runs offline)
data/            crawl output (not tracked)
```
