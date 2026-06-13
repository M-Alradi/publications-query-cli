"""
Tests for query.py — verify that each intent dispatches to a SPARQL
query of the expected structure (SELECT / ASK / CONSTRUCT, expected
clauses) and that unknown intents fail cleanly with a usage banner.
"""

import subprocess
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import query as q 


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Args:
    """Simple stand-in for argparse.Namespace in unit tests."""

    def __init__(self, intent="", limit=None, venue=None, topic=None, paper=None):
        self.intent = intent
        self.limit = limit
        self.venue = venue
        self.topic = topic
        self.paper = paper


# ---------------------------------------------------------------------------
# Intent matching
# ---------------------------------------------------------------------------

def test_match_intent_list_authors_at():
    assert q.match_intent("list authors at NeurIPS") == "list authors at"


def test_match_intent_papers_per_topic():
    assert q.match_intent("papers per topic") == "papers per topic"


def test_match_intent_top_cited():
    assert q.match_intent("top 5 cited") == "top cited"
    assert q.match_intent("top cited") == "top cited"


def test_match_intent_has_doi():
    assert q.match_intent("does paper001 have a doi") == "has doi"


def test_match_intent_construct_graph():
    assert q.match_intent("paper author graph") == "paper author graph"
    assert q.match_intent("construct paper author graph") == "paper author graph"


def test_match_intent_unknown_returns_none():
    assert q.match_intent("dance the macarena") is None


# ---------------------------------------------------------------------------
# Query builders: SELECT - list authors at <venue>
# ---------------------------------------------------------------------------

def test_build_authors_at_venue_is_select():
    query, qtype = q.build_authors_at_venue(Args(venue="NeurIPS"))
    assert qtype == "SELECT"
    assert "SELECT ?author" in query
    assert ":publishedIn" in query
    assert ":authoredBy" in query
    assert '"NeurIPS"' in query


def test_build_authors_at_venue_default_venue():
    query, qtype = q.build_authors_at_venue(Args())
    assert '"NeurIPS"' in query


# ---------------------------------------------------------------------------
# Query builders: SELECT - papers per topic
# ---------------------------------------------------------------------------

def test_build_papers_per_topic_is_select_with_group_by():
    query, qtype = q.build_papers_per_topic(Args())
    assert qtype == "SELECT"
    assert "?topic" in query
    assert "COUNT(?paper)" in query
    assert "GROUP BY ?topic" in query


# ---------------------------------------------------------------------------
# Query builders: SELECT - top N cited
# ---------------------------------------------------------------------------

def test_build_top_cited_default_limit():
    query, qtype = q.build_top_cited(Args())
    assert qtype == "SELECT"
    assert ":citationCount" in query
    assert "ORDER BY DESC(?citationCount)" in query
    assert "LIMIT 5" in query


def test_build_top_cited_custom_limit():
    query, qtype = q.build_top_cited(Args(limit=10))
    assert "LIMIT 10" in query


# ---------------------------------------------------------------------------
# Query builders: ASK - has doi
# ---------------------------------------------------------------------------

def test_build_paper_has_doi_is_ask():
    query, qtype = q.build_paper_has_doi(Args(paper="paper001"))
    assert qtype == "ASK"
    assert query.strip().startswith("PREFIX") is False or "ASK WHERE" in query
    assert "ASK WHERE" in query
    assert ":paper001 :doi ?doi" in query


def test_build_paper_has_doi_default_paper():
    query, qtype = q.build_paper_has_doi(Args())
    assert ":paper001 :doi ?doi" in query


# ---------------------------------------------------------------------------
# Query builders: CONSTRUCT - paper author graph
# ---------------------------------------------------------------------------

def test_build_paper_author_graph_is_construct():
    query, qtype = q.build_paper_author_graph(Args(venue="NeurIPS"))
    assert qtype == "CONSTRUCT"
    assert "CONSTRUCT {" in query
    assert ":writtenBy" in query
    assert ":inVenue" in query
    assert '"NeurIPS"' in query


# ---------------------------------------------------------------------------
# CLI behavior: unknown intent exits non-zero with usage banner
# ---------------------------------------------------------------------------

def test_cli_unknown_intent_exits_nonzero():
    script = os.path.join(os.path.dirname(__file__), "..", "query.py")
    result = subprocess.run(
        [sys.executable, script, "dance the macarena"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "unrecognized intent" in combined.lower()
    assert "usage:" in combined.lower()


def test_cli_unknown_intent_lists_supported_intents():
    script = os.path.join(os.path.dirname(__file__), "..", "query.py")
    result = subprocess.run(
        [sys.executable, script, "do something weird"],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "list authors at" in combined
    assert "papers per topic" in combined
    assert "top n cited" in combined.lower()
    assert "has doi" in combined
    assert "paper author graph" in combined
