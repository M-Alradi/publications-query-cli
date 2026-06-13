# publications-query-cli

A small command-line tool that takes a fixed-vocabulary natural-language
intent and dispatches it to a matching SPARQL query against the
`publications` dataset served by Apache Jena Fuseki.

This is a tiny preview of a Week B integrated pipeline: a minimum-viable
natural-language → formal-query reduction. It is a **dispatcher**, not a
new query — the underlying SPARQL queries reuse the same dataset and
predicates as the Integration 9A repo.

## Setup

1. Start Fuseki:

   ```bash
   docker compose up -d
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Load the dataset into Fuseki:

   ```bash
   python load_dataset.py
   ```

   This waits for Fuseki's healthcheck, then POSTs `data/publications.ttl`
   into the `publications` dataset using HTTP Basic Auth
   (`admin` / `admin`, matching `docker-compose.yml`).

## Usage

```bash
python query.py "<intent phrase>" [options]
```

Examples:

```bash
$ python query.py "list authors at NeurIPS"
:author000
:author017
...

$ python query.py "papers per topic"
:topic_vision-transformers  8
:topic_language-models      6
...

$ python query.py "top 5 cited"
:paper063  485
:paper043  475
...

$ python query.py "does paper001 have a doi"
True

$ python query.py "construct paper author graph" --venue ACL
```

If the intent is not recognized, the tool prints an error and the usage
banner listing all supported intents, then exits with a non-zero status
code.

## Intent → SPARQL Mapping

| Intent phrase (examples)                | Query type  | SPARQL summary                                                                 | Options used        |
|------------------------------------------|-------------|---------------------------------------------------------------------------------|----------------------|
| `list authors at <VENUE>`                 | `SELECT`    | Selects distinct authors whose papers were `:publishedIn` a venue with the given `rdfs:label`. | `--venue`           |
| `papers per topic`                        | `SELECT`    | Groups papers by `:topic` and counts them, ordered descending by count.        | —                    |
| `top N cited` / `top cited`               | `SELECT`    | Selects papers and their `:citationCount`, ordered descending, limited to N.    | `--limit` (or `N` parsed from the phrase, e.g. "top 5 cited") |
| `does <PAPER> have a doi` / `has doi`     | `ASK`       | Returns `true`/`false` for whether the given paper has a `:doi` triple.        | `--paper`            |
| `construct paper author graph`            | `CONSTRUCT` | Builds a small graph of `:writtenBy` (paper → author) and `:inVenue` (paper → venue) triples for a given venue. | `--venue`            |

## Design Notes

- **Argument parsing**: built with `argparse`. The single positional
  argument `intent` carries the natural-language phrase; optional flags
  (`--venue`, `--limit`, `--paper`, `--topic`) supply parameters that the
  fixed-vocabulary phrase alone may not specify precisely.
- **Intent matching** (`match_intent`): performs simple substring/prefix
  checks against a small fixed vocabulary (`list authors at`,
  `papers per topic`, `top ... cited`, `has doi` / `doi`,
  `paper author graph` / `construct`). This keeps the NL→query mapping
  transparent and testable without requiring an LLM at runtime.
- **Query builders**: each intent maps to a dedicated function returning
  `(sparql_string, query_type)`. Keeping builders separate from dispatch
  logic makes each query independently testable and documents the exact
  SPARQL shape per intent.
- **Output formatting**: `SELECT` results are printed as
  whitespace-separated columns with full URIs shortened to `:localName`
  form; `ASK` prints `True`/`False`; `CONSTRUCT` prints one line per
  triple.
- **Error handling**: an unrecognized intent prints a clear error message
  plus the full `argparse` help text (which enumerates all supported
  intents) and exits with status code `2`. A SPARQL endpoint connection
  failure exits with status code `1`.
- **Testing**: `tests/test_dispatcher.py` verifies, for each intent,
  that `match_intent` resolves correctly and that each builder function
  produces a query of the expected type (`SELECT` / `ASK` / `CONSTRUCT`)
  containing the expected clauses (e.g. `GROUP BY`, `LIMIT`,
  `ASK WHERE`, `CONSTRUCT {`). It also verifies via subprocess that an
  unknown intent exits non-zero and prints both an error message and the
  usage banner. Tests do not require a running Fuseki instance.

## Files

```
publications-query-cli/
├── query.py                  # dispatcher CLI
├── load_dataset.py           # one-time loader: POSTs publications.ttl into Fuseki
├── tests/
│   └── test_dispatcher.py    # pytest suite
├── data/
│   └── publications.ttl      # dataset (reused from integration)
├── docker-compose.yml        # Fuseki service (reused from integration)
├── requirements.txt
└── README.md
```