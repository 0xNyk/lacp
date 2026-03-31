#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    chunk_id: str
    path: str
    heading: str
    text: str


def normalize_host(host: str) -> str:
    host = host.strip()
    if not host.startswith("http://") and not host.startswith("https://"):
        host = "http://" + host
    return host.rstrip("/")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def chunk_text(path: Path, text: str, max_chars: int, overlap_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading = "root"
    paragraph_lines: list[str] = []
    segment_id = 0

    def flush_paragraph(raw: str, current_heading: str, segment_idx: int) -> int:
        segment_idx_local = segment_idx
        normalized = re.sub(r"\s+", " ", raw).strip()
        if not normalized:
            return segment_idx_local
        start = 0
        while start < len(normalized):
            end = min(len(normalized), start + max_chars)
            if end < len(normalized):
                cut = normalized.rfind(" ", start, end)
                if cut > start + int(max_chars * 0.65):
                    end = cut
            snippet = normalized[start:end].strip()
            if snippet:
                chunks.append(
                    Chunk(
                        chunk_id=f"{path.as_posix()}::{segment_idx_local}",
                        path=path.as_posix(),
                        heading=current_heading,
                        text=snippet,
                    )
                )
                segment_idx_local += 1
            if end >= len(normalized):
                break
            start = max(0, end - overlap_chars)
        return segment_idx_local

    for line in text.splitlines():
        heading_match = HEADING_RE.match(line)
        if heading_match:
            segment_id = flush_paragraph("\n".join(paragraph_lines), heading, segment_id)
            paragraph_lines = []
            heading = heading_match.group(2).strip()
            continue
        if not line.strip():
            segment_id = flush_paragraph("\n".join(paragraph_lines), heading, segment_id)
            paragraph_lines = []
            continue
        paragraph_lines.append(line)

    _ = flush_paragraph("\n".join(paragraph_lines), heading, segment_id)
    return chunks


def collect_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        if "/data/" in path.as_posix():
            continue
        files.append(path)
    return files


def normalize_dense_vector(vector: list[float]) -> list[float]:
    norm_sq = sum(v * v for v in vector)
    if norm_sq <= 0.0:
        return [0.0 for _ in vector]
    norm = math.sqrt(norm_sq)
    return [v / norm for v in vector]


def post_json(url: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"Unexpected response type from {url}: {type(obj)}")
    return obj


def get_json(url: str, timeout_s: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"Unexpected response type from {url}: {type(obj)}")
    return obj


def ollama_version(host: str, timeout_s: float = 5.0) -> str | None:
    host = normalize_host(host)
    try:
        obj = get_json(f"{host}/api/version", timeout_s=timeout_s)
    except Exception:
        return None
    version = obj.get("version")
    return version if isinstance(version, str) else None


def ollama_models(host: str, timeout_s: float = 5.0) -> list[str]:
    host = normalize_host(host)
    try:
        obj = get_json(f"{host}/api/tags", timeout_s=timeout_s)
    except Exception:
        return []
    models = obj.get("models")
    if not isinstance(models, list):
        return []
    out: list[str] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        name = model.get("name")
        if isinstance(name, str) and name:
            out.append(name)
    return out


def _extract_embeddings_from_response(obj: dict[str, Any], expected_count: int) -> list[list[float]] | None:
    embeddings = obj.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        parsed: list[list[float]] = []
        for emb in embeddings:
            if isinstance(emb, list) and emb and all(isinstance(x, (int, float)) for x in emb):
                parsed.append([float(x) for x in emb])
        if len(parsed) == expected_count:
            return [normalize_dense_vector(v) for v in parsed]

    embedding = obj.get("embedding")
    if expected_count == 1 and isinstance(embedding, list) and embedding and all(isinstance(x, (int, float)) for x in embedding):
        return [normalize_dense_vector([float(x) for x in embedding])]

    return None


def ollama_embed(texts: list[str], host: str, model: str, timeout_s: float = 30.0) -> list[list[float]]:
    if not texts:
        return []
    host = normalize_host(host)

    # Preferred endpoint (supports batched inputs on modern Ollama):
    try:
        obj = post_json(
            f"{host}/api/embed",
            {"model": model, "input": texts},
            timeout_s=timeout_s,
        )
        parsed = _extract_embeddings_from_response(obj, expected_count=len(texts))
        if parsed is not None:
            return parsed
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 404):
            raise
    except urllib.error.URLError:
        raise
    except TimeoutError:
        raise
    except Exception:
        # fall through to compatibility endpoint
        pass

    # Compatibility endpoint (older Ollama):
    vectors: list[list[float]] = []
    for text in texts:
        obj = post_json(
            f"{host}/api/embeddings",
            {"model": model, "prompt": text},
            timeout_s=timeout_s,
        )
        parsed = _extract_embeddings_from_response(obj, expected_count=1)
        if parsed is None:
            raise ValueError("Could not parse embedding from /api/embeddings response.")
        vectors.extend(parsed)
    return vectors


def build_sparse_vectors(
    chunks: list[Chunk],
    max_terms_per_chunk: int,
) -> tuple[dict[str, float], list[dict[str, float]]]:
    if not chunks:
        return {}, []

    df: Counter[str] = Counter()
    tokenized_chunks: list[list[str]] = []
    for chunk in chunks:
        tokens = tokenize(chunk.text)
        tokenized_chunks.append(tokens)
        df.update(set(tokens))

    total_chunks = len(chunks)
    idf: dict[str, float] = {
        term: math.log((total_chunks + 1) / (term_df + 1)) + 1.0 for term, term_df in df.items()
    }

    vectors: list[dict[str, float]] = []
    for tokens in tokenized_chunks:
        tf = Counter(tokens)
        vec: dict[str, float] = {}
        norm_sq = 0.0
        for term, count in tf.items():
            weight = float(count) * idf.get(term, 1.0)
            vec[term] = weight
            norm_sq += weight * weight

        norm = math.sqrt(norm_sq) if norm_sq > 0 else 1.0
        for term in list(vec.keys()):
            vec[term] = vec[term] / norm

        if len(vec) > max_terms_per_chunk:
            top_terms = sorted(vec.items(), key=lambda x: x[1], reverse=True)[:max_terms_per_chunk]
            vec = dict(top_terms)
        vectors.append(vec)

    return idf, vectors


def build_sparse_query_vector(query: str, idf: dict[str, float]) -> dict[str, float]:
    tokens = tokenize(query)
    if not tokens:
        return {}
    tf: dict[str, float] = {}
    for token in tokens:
        tf[token] = tf.get(token, 0.0) + 1.0
    vec: dict[str, float] = {}
    norm_sq = 0.0
    for token, count in tf.items():
        weight = count * idf.get(token, 1.0)
        vec[token] = weight
        norm_sq += weight * weight
    norm = math.sqrt(norm_sq) if norm_sq > 0 else 1.0
    for token in list(vec.keys()):
        vec[token] = vec[token] / norm
    return vec


def dot_sparse(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    total = 0.0
    for token, weight in left.items():
        total += weight * right.get(token, 0.0)
    return total


def dot_dense(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    n = min(len(left), len(right))
    total = 0.0
    for i in range(n):
        total += left[i] * right[i]
    return total


def lexical_overlap_score(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = set(tokenize(text))
    if not text_tokens:
        return 0.0
    return len(query_tokens.intersection(text_tokens)) / len(query_tokens)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, v) for v in weights.values())
    if total <= 0:
        return {k: 0.0 for k in weights}
    return {k: max(0.0, v) / total for k, v in weights.items()}


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[tuple[int, float]]],
    weights: dict[str, float],
    k: int = 60,
    window: int = 500,
) -> dict[int, float]:
    """Reciprocal Rank Fusion across multiple ranked lists.

    Each entry in ranked_lists maps a signal name (e.g. "sparse", "dense", "lexical")
    to a list of (chunk_index, raw_score) sorted descending by raw_score.
    Returns {chunk_index: fused_score}.

    RRF formula: score(d) = sum_over_signals( w_signal / (k + rank_in_signal) )
    where k=60 is standard (Cormack et al. 2009).

    window: only the top-N candidates per signal are considered. This prevents
    tail noise and ensures documents that appear in multiple top-N lists get
    naturally boosted. Default 100.

    When fewer than 3 signals are active, k is scaled down proportionally
    to avoid over-smoothing.
    """
    active_signals = sum(1 for name in ranked_lists if weights.get(name, 0.0) > 0 and ranked_lists[name])
    if active_signals < 3:
        k = max(20, k * active_signals // 3)

    fused: dict[int, float] = {}
    for signal_name, ranked in ranked_lists.items():
        w = weights.get(signal_name, 0.0)
        if w <= 0:
            continue
        for rank_pos, (chunk_idx, _raw_score) in enumerate(ranked[:window], start=1):
            fused[chunk_idx] = fused.get(chunk_idx, 0.0) + w / (k + rank_pos)
    return fused

