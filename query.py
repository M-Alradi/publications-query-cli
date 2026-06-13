"""
query.py - A natural-language intent dispatcher for SPARQL queries
against the publications dataset hosted on a local Fuseki server.

Usage:
    python query.py "<intent phrase>" [--limit N] [--venue VENUE] [--topic TOPIC] [--paper PAPER]

Run `python query.py --help` to see all supported intents.
"""

import argparse
import sys
import requests

FUSEKI_ENDPOINT = "http://localhost:3030/publications/query"

PREFIX = """
PREFIX :     <http://aispire.example.org/publications/>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
"""


# ---------------------------------------------------------------------------
# SPARQL query builders
#
# Each builder returns a tuple: (query_string, query_type)
# query_type is one of: "SELECT", "ASK", "CONSTRUCT"
# ---------------------------------------------------------------------------

def build_authors_at_venue(args):
    venue = args.venue or "NeurIPS"
    query = PREFIX + f"""
SELECT ?author WHERE {{
    ?paper :publishedIn ?v ;
           :authoredBy ?author .
    ?v rdfs:label "{venue}" .
}}
ORDER BY ?author
"""
    return query, "SELECT"


def build_papers_per_topic(args):
    query = PREFIX + """
SELECT ?topic (COUNT(?paper) AS ?count) WHERE {
    ?paper :topic ?topic .
}
GROUP BY ?topic
ORDER BY DESC(?count)
"""
    return query, "SELECT"


def build_top_cited(args):
    limit = args.limit or 5
    query = PREFIX + f"""
SELECT ?paper ?citationCount WHERE {{
    ?paper :citationCount ?citationCount .
}}
ORDER BY DESC(?citationCount)
LIMIT {limit}
"""
    return query, "SELECT"


def build_paper_has_doi(args):
    paper = args.paper or "paper001"
    query = PREFIX + f"""
ASK WHERE {{
    :{paper} :doi ?doi .
}}
"""
    return query, "ASK"


def build_paper_author_graph(args):
    venue = args.venue or "NeurIPS"
    query = PREFIX + f"""
CONSTRUCT {{
    ?paper :writtenBy ?author .
    ?paper :inVenue ?v .
}} WHERE {{
    ?paper :publishedIn ?v ;
           :authoredBy ?author .
    ?v rdfs:label "{venue}" .
}}
"""
    return query, "CONSTRUCT"


# ---------------------------------------------------------------------------
# Intent registry
#
# Maps a fixed natural-language intent phrase to its builder function.
# ---------------------------------------------------------------------------

INTENTS = {
    "list authors at": build_authors_at_venue,
    "papers per topic": build_papers_per_topic,
    "top cited": build_top_cited,
    "has doi": build_paper_has_doi,
    "paper author graph": build_paper_author_graph,
}


def match_intent(intent_text):
    """
    Match free-text intent against the fixed vocabulary.

    Matching is prefix/substring based on the canonical intent keys,
    allowing phrases like "list authors at NeurIPS" or "top 5 cited".
    """
    text = intent_text.strip().lower()

    if text.startswith("list authors at"):
        return "list authors at"
    if "papers per topic" in text:
        return "papers per topic"
    if "top" in text and "cited" in text:
        return "top cited"
    if "has doi" in text or "doi" in text:
        return "has doi"
    if "paper author graph" in text or "construct" in text:
        return "paper author graph"

    return None


# ---------------------------------------------------------------------------
# Execution and output formatting
# ---------------------------------------------------------------------------

def run_query(query, query_type):
    """Send the SPARQL query to Fuseki and return the raw JSON response."""
    response = requests.post(
        FUSEKI_ENDPOINT,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def format_results(result_json, query_type):
    """Render SPARQL results in a simple, script-friendly text format."""
    lines = []

    if query_type == "ASK":
        lines.append(str(result_json.get("boolean", False)))
        return lines

    bindings = result_json.get("results", {}).get("bindings", [])

    if query_type == "CONSTRUCT":
        # CONSTRUCT results arrive as triples under "results" -> "bindings"
        # when requested via application/sparql-results+json, but Fuseki
        # typically returns CONSTRUCT as RDF (e.g. Turtle/JSON-LD).
        # Here result_json is expected to be a list of triple dicts.
        for triple in result_json:
            s = triple.get("subject", "")
            p = triple.get("predicate", "")
            o = triple.get("object", "")
            lines.append(f"{s} {p} {o}")
        return lines

    # SELECT
    for binding in bindings:
        values = []
        for var in result_json.get("head", {}).get("vars", []):
            cell = binding.get(var, {}).get("value", "")
            # Shorten full URIs to the local-name form (":xxx")
            if cell.startswith("http://aispire.example.org/publications/"):
                cell = ":" + cell.rsplit("/", 1)[-1]
            values.append(str(cell))
        lines.append("  ".join(values))

    return lines


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Dispatch a fixed-vocabulary natural-language intent to a "
            "matching SPARQL query against the publications dataset."
        ),
        epilog=(
            "Supported intents:\n"
            "  list authors at <VENUE>   - SELECT authors who published at VENUE\n"
            "  papers per topic          - SELECT count of papers grouped by topic\n"
            "  top N cited               - SELECT the N most-cited papers\n"
            "  has doi <PAPER>           - ASK whether PAPER has a DOI\n"
            "  paper author graph        - CONSTRUCT a writtenBy/inVenue graph\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "intent",
        help='Natural-language intent, e.g. "list authors at NeurIPS"',
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit for 'top cited' (default: 5)",
    )
    parser.add_argument(
        "--venue", type=str, default=None,
        help="Venue label, e.g. NeurIPS (used by venue-related intents)",
    )
    parser.add_argument(
        "--topic", type=str, default=None,
        help="Topic local name (reserved for future intents)",
    )
    parser.add_argument(
        "--paper", type=str, default=None,
        help="Paper local name, e.g. paper001 (used by 'has doi')",
    )
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    intent_key = match_intent(args.intent)

    if intent_key is None:
        sys.stderr.write(
            f"Error: unrecognized intent '{args.intent}'.\n\n"
        )
        parser.print_help(sys.stderr)
        return 2

    # Allow "top 5 cited" to set --limit automatically if not given
    if intent_key == "top cited" and args.limit is None:
        for token in args.intent.split():
            if token.isdigit():
                args.limit = int(token)
                break

    builder = INTENTS[intent_key]
    query, query_type = builder(args)

    try:
        result_json = run_query(query, query_type)
    except requests.exceptions.RequestException as exc:
        sys.stderr.write(f"Error: could not reach SPARQL endpoint: {exc}\n")
        return 1

    for line in format_results(result_json, query_type):
        print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
