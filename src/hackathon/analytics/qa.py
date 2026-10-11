"""Retrieval-augmented Q&A: answers are grounded in KPI results, assumptions and the data model.

Retrieval is a small pure-Python BM25 over text chunks, filtered to the asking team. The LLM never
writes SQL; it only sees retrieved chunks, so every answer is traceable to a KPI table.
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from hackathon.analytics.rag_status import Metric

DEFAULT_MODEL = "gemini-3.5-flash"

KPI_TEAMS = {
    "kpi_01": ("Finance",),
    "kpi_08": ("Finance",),
    "stretch_margin_risk": ("Finance", "Supply Chain"),
    "kpi_02": ("Marketing",),
    "kpi_02b": ("Marketing",),
    "kpi_03": ("Marketing",),
    "kpi_04": ("Marketing",),
    "kpi_07": ("Marketing",),
    "kpi_05": ("Supply Chain",),
    "kpi_06": ("Supply Chain",),
}
ROWS_PER_CHUNK = 8

SYSTEM_PROMPT = (
    "You are a data analyst assistant for the {team} team of an e-commerce company. Answer ONLY "
    "from the numbered context chunks. Cite the chunk ids you used like [3]. If the context does "
    "not contain the answer, say you do not have that data instead of guessing. Keep answers short "
    "and quote figures exactly as given."
)


@dataclass(frozen=True)
class Chunk:
    id: int
    teams: tuple[str, ...]  # empty = visible to every team
    source: str
    text: str


def _fmt_row(row: dict[str, Any]) -> str:
    return "; ".join(f"{k}={v}" for k, v in row.items() if v is not None)


def build_corpus(
    kpis: dict[str, list[dict[str, Any]]],
    scorecards: dict[str, list[Metric]],
    data_model_text: str = "",
    notes: dict[str, str] | None = None,
) -> list[Chunk]:
    chunks: list[Chunk] = []

    def add(teams: tuple[str, ...], source: str, text: str) -> None:
        chunks.append(Chunk(len(chunks) + 1, teams, source, text))

    for team, metrics in scorecards.items():
        for m in metrics:
            value = "n/a" if m.value is None else f"{m.value}{m.unit}"
            add(
                (team,),
                f"scorecard:{m.key}",
                f"RAG status metric '{m.label}' for {team}: value {value}, status {m.status} "
                f"(G=green, A=amber, R=red). Rule: {m.rule}. Derived from KPI {m.source_kpi}.",
            )

    for name, rows in kpis.items():
        teams = KPI_TEAMS.get(name, ())
        note = (notes or {}).get(name, "")
        if note:
            add(teams, f"definition:{name}", f"Definition of {name}:\n{note[:1800]}")
        if name == "kpi_08":
            counts = Counter((r.get("order_status"), r.get("reconciliation_status")) for r in rows)
            add(
                teams,
                f"kpi:{name}",
                f"KPI {name} payment reconciliation: {len(rows)} orders; counts by "
                "(order_status, reconciliation_status): "
                + ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=str)),
            )
            continue
        for start in range(0, len(rows), ROWS_PER_CHUNK):
            body = "\n".join(_fmt_row(r) for r in rows[start : start + ROWS_PER_CHUNK])
            add(
                teams,
                f"kpi:{name}",
                f"KPI {name} rows {start + 1}-{start + ROWS_PER_CHUNK}:\n{body}",
            )

    for part in re.split(r"\n(?=#{1,3} )", data_model_text):
        if part.strip():
            add((), "docs:data_model", part.strip()[:1500])
    return chunks


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))


def retrieve(chunks: list[Chunk], question: str, team: str, k: int = 6) -> list[Chunk]:
    """BM25 over the chunks visible to `team`; returns the top-k with a positive score."""
    visible = [c for c in chunks if not c.teams or team in c.teams]
    docs = [_tokens(c.text + " " + c.source) for c in visible]
    if not docs:
        return []
    avg_len = sum(len(d) for d in docs) / len(docs) or 1.0
    df = Counter(t for d in docs for t in set(d))
    n = len(docs)
    query = set(_tokens(question))
    k1, b = 1.5, 0.75
    scored = []
    for chunk, doc in zip(visible, docs, strict=True):
        tf = Counter(doc)
        score = 0.0
        for term in query:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(doc) / avg_len))
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: (-pair[0], pair[1].id))
    return [c for _, c in scored[:k]]


@dataclass(frozen=True)
class Answer:
    text: str
    sources: list[Chunk]


def answer_question(
    question: str,
    team: str,
    chunks: list[Chunk],
    client=None,
    model: str = DEFAULT_MODEL,
    k: int = 6,
) -> Answer:
    hits = retrieve(chunks, question, team, k)
    if not hits:
        return Answer("I do not have data relevant to that question.", [])
    context = "\n\n".join(f"[{c.id}] ({c.source})\n{c.text}" for c in hits)
    prompt = f"Context:\n{context}\n\nQuestion: {question}"
    system = SYSTEM_PROMPT.format(team=team)
    if client is None:
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Q&A needs the app extra: pip install -e '.[app]'") from exc
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY in .env to use the Q&A tab")
        client = genai.Client(api_key=api_key, http_options={"timeout": 60000})
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"system_instruction": system, "max_output_tokens": 800, "temperature": 0.2},
    )
    return Answer((response.text or "").strip(), hits)
