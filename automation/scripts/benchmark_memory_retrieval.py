#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_rag_lib import ollama_embed
from query_memory_rag import query_index


ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DEFAULT_INDEX = ROOT / "data" / "rag" / "hybrid-index.json"
DEFAULT_DATASET = ROOT / "benchmarks" / "golden_queries.json"
OUTPUT_DIR = ROOT / "data" / "benchmarks"
TRIAGE_DIR = OUTPUT_DIR / "triage"
HOME = Path.home()
LEGACY_PREFIXES = (
    "docs/knowledge-memory",
    "docs/ai-dev-optimization",
    "/Users/nyk/docs/knowledge-memory",
    "/Users/nyk/docs/ai-dev-optimization",
)


def canonicalize_result_path(path: str) -> str:
    p = path.strip()
    if not p:
        return p
    p = p.replace("\\", "/")
    p = p.lstrip("./")
    if p.startswith("/Users/nyk/docs/knowledge-memory/"):
        return p.replace("/Users/nyk/docs/knowledge-memory/", "control/knowledge/knowledge-memory/", 1)
    if p.startswith("/Users/nyk/docs/ai-dev-optimization/"):
        return p.replace("/Users/nyk/docs/ai-dev-optimization/", "control/automation/ai-dev-optimization/", 1)
    if p.startswith("docs/knowledge-memory/"):
        return p.replace("docs/knowledge-memory/", "control/knowledge/knowledge-memory/", 1)
    if p.startswith("docs/ai-dev-optimization/"):
        return p.replace("docs/ai-dev-optimization/", "control/automation/ai-dev-optimization/", 1)
    return p


def is_relevant(result_path: str, expected_paths: list[str]) -> bool:
    candidate = canonicalize_result_path(result_path)
    for expected in expected_paths:
        expected_norm = canonicalize_result_path(expected)
        if candidate == expected_norm:
            return True
        if candidate.startswith(expected_norm):
            return True
    return False


def matched_expected(result_path: str, expected_paths: list[str]) -> str | None:
    candidate = canonicalize_result_path(result_path)
    for expected in expected_paths:
        expected_norm = canonicalize_result_path(expected)
        if candidate == expected_norm:
            return expected_norm
        if candidate.startswith(expected_norm):
            return expected_norm
    return None


def reciprocal_rank(results: list[dict[str, Any]], expected_paths: list[str], k: int) -> float:
    for idx, item in enumerate(results[:k], start=1):
        if is_relevant(str(item.get("path", "")), expected_paths):
            return 1.0 / idx
    return 0.0


def dcg(relevance: list[int]) -> float:
    total = 0.0
    for i, rel in enumerate(relevance, start=1):
        if rel:
            total += rel / math.log2(i + 1)
    return total


def ndcg_at_k(results: list[dict[str, Any]], expected_paths: list[str], k: int) -> float:
    seen_expected: set[str] = set()
    rel: list[int] = []
    for item in results[:k]:
        match = matched_expected(str(item.get("path", "")), expected_paths)
        if match is None or match in seen_expected:
            rel.append(0)
            continue
        seen_expected.add(match)
        rel.append(1)
    ideal_count = min(k, len(expected_paths))
    ideal = [1] * ideal_count + [0] * max(0, k - ideal_count)
    denom = dcg(ideal)
    if denom <= 0:
        return 0.0
    return dcg(rel) / denom


def evaluate_case(case: dict[str, Any], payload: dict[str, Any], top_k: int, w_sparse: float, w_dense: float, w_lexical: float, ollama_timeout: float, fusion_mode: str = "rrf") -> dict[str, Any]:
    query = str(case.get("query", "")).strip()
    case_id = str(case.get("id", "unknown"))
    expected_paths = [str(x) for x in case.get("expected_paths", []) if isinstance(x, str)]
    if not query:
        return {"id": case_id, "error": "missing query"}
    if not expected_paths:
        return {"id": case_id, "error": "missing expected_paths"}

    results, meta = query_index(
        query=query,
        payload=payload,
        top_k=top_k,
        w_sparse=w_sparse,
        w_dense=w_dense,
        w_lexical=w_lexical,
        ollama_host_override="",
        ollama_model_override="",
        ollama_timeout_s=ollama_timeout,
        allow_sparse_fallback=True,
        fusion_mode=fusion_mode,
    )
    ranked_paths = [canonicalize_result_path(str(item.get("path", ""))) for item in results]
    matched: set[str] = set()
    for p in ranked_paths[:top_k]:
        expected = matched_expected(p, expected_paths)
        if expected is not None:
            matched.add(expected)
    first_hit_rank = next((i + 1 for i, p in enumerate(ranked_paths) if is_relevant(p, expected_paths)), None)

    precision = len(matched) / top_k if top_k else 0.0
    recall = len(matched) / len(expected_paths) if expected_paths else 0.0
    rr = reciprocal_rank(results, expected_paths, top_k)
    ndcg = ndcg_at_k(results, expected_paths, top_k)
    hit = 1.0 if first_hit_rank is not None else 0.0

    return {
        "id": case_id,
        "query": query,
        "expected_paths": expected_paths,
        "hit_at_k": hit,
        "mrr_at_k": rr,
        "ndcg_at_k": ndcg,
        "precision_at_k": precision,
        "recall_at_k": recall,
        "first_hit_rank": first_hit_rank,
        "weights": meta.get("weights", {}),
        "dense_warning": meta.get("dense_warning", ""),
        "results": results,
    }


def analyze_index_freshness(index_path: Path, payload: dict[str, Any], knowledge_root: Path) -> dict[str, Any]:
    built_at_raw = str(payload.get("built_at", "")).strip()
    built_at = None
    if built_at_raw:
        try:
            built_at = datetime.fromisoformat(built_at_raw.replace("Z", "+00:00"))
        except ValueError:
            built_at = None

    newest_mtime = None
    newest_path = ""
    # Freshness should compare against the source set actually indexed, not every markdown
    # file under knowledge_root (which can include benchmark artifacts written after a run).
    indexed_paths: set[str] = set()
    for chunk in payload.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        raw_path = str(chunk.get("path", "")).strip()
        if raw_path:
            indexed_paths.add(raw_path)

    for raw_path in sorted(indexed_paths):
        p = HOME / raw_path
        if not p.exists():
            continue
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if newest_mtime is None or mtime > newest_mtime:
            newest_mtime = mtime
            newest_path = str(p)

    index_mtime = datetime.fromtimestamp(index_path.stat().st_mtime, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)

    seconds_since_build = (now - built_at).total_seconds() if built_at is not None else None
    source_lag = 0.0
    if built_at is not None and newest_mtime is not None:
        # If > 0, source has newer files than current index.
        source_lag = max(0.0, (newest_mtime - built_at).total_seconds())

    return {
        "index_file_mtime_utc": index_mtime.isoformat().replace("+00:00", "Z"),
        "index_built_at_utc": built_at.isoformat().replace("+00:00", "Z") if built_at is not None else "",
        "seconds_since_build": seconds_since_build,
        "newest_source_mtime_utc": newest_mtime.isoformat().replace("+00:00", "Z") if newest_mtime is not None else "",
        "newest_source_path": newest_path,
        "source_to_index_lag_seconds": source_lag,
    }


def analyze_reference_integrity(case_results: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    total_checked = 0
    invalid = 0
    legacy = 0
    invalid_samples: list[str] = []
    legacy_samples: list[str] = []

    for case in case_results:
        if "error" in case:
            continue
        for item in case.get("results", [])[:top_k]:
            raw = str(item.get("path", ""))
            normalized = canonicalize_result_path(raw)
            total_checked += 1

            is_legacy = raw.startswith(LEGACY_PREFIXES) or normalized.startswith(("docs/knowledge-memory", "docs/ai-dev-optimization"))
            if is_legacy:
                legacy += 1
                if len(legacy_samples) < 10:
                    legacy_samples.append(raw)

            path_on_disk = HOME / normalized
            if not path_on_disk.exists():
                invalid += 1
                if len(invalid_samples) < 10:
                    invalid_samples.append(normalized)

    invalid_ratio = (invalid / total_checked) if total_checked else 0.0
    legacy_ratio = (legacy / total_checked) if total_checked else 0.0
    return {
        "checked_results": total_checked,
        "invalid_path_count": invalid,
        "invalid_path_ratio": invalid_ratio,
        "invalid_path_samples": invalid_samples,
        "legacy_path_count": legacy,
        "legacy_path_ratio": legacy_ratio,
        "legacy_path_samples": legacy_samples,
    }


def check_dense_capability(payload: dict[str, Any], timeout_s: float, max_latency_ms: float, min_dim: int) -> dict[str, Any]:
    ollama_cfg = payload.get("ollama", {}) if isinstance(payload, dict) else {}
    host = str(ollama_cfg.get("host", "http://127.0.0.1:11434")).strip() or "http://127.0.0.1:11434"
    model = str(ollama_cfg.get("model", "nomic-embed-text:latest")).strip() or "nomic-embed-text:latest"
    dense_enabled = bool(ollama_cfg.get("dense_enabled", False))
    dense_error = str(ollama_cfg.get("dense_error", "") or "")

    t0 = time.perf_counter()
    error = ""
    dim = 0
    ok = False
    try:
        vectors = ollama_embed(
            ["capability-health-probe"],
            host=host,
            model=model,
            timeout_s=max(1.0, min(timeout_s, 60.0)),
        )
        if vectors and isinstance(vectors[0], list):
            dim = len(vectors[0])
            ok = dim >= min_dim
        else:
            error = "empty embedding response"
    except Exception as exc:
        error = str(exc)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    if ok and latency_ms > max_latency_ms:
        ok = False
        error = f"embed latency {latency_ms:.2f}ms exceeded max {max_latency_ms:.2f}ms"

    return {
        "ok": ok,
        "host": host,
        "model": model,
        "latency_ms": latency_ms,
        "vector_dim": dim,
        "dense_enabled_from_index": dense_enabled,
        "dense_error_from_index": dense_error,
        "error": error,
    }


def build_failure_triage(case_results: list[dict[str, Any]], top_k: int, rank_warn_threshold: int) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for case in case_results:
        if "error" in case:
            issues.append(
                {
                    "id": case.get("id", "unknown"),
                    "type": "case_error",
                    "error": case.get("error", ""),
                }
            )
            continue

        first_hit_rank = case.get("first_hit_rank")
        is_failure = first_hit_rank is None
        is_weak = isinstance(first_hit_rank, int) and first_hit_rank > rank_warn_threshold
        if not is_failure and not is_weak:
            continue

        expected = [canonicalize_result_path(str(x)) for x in case.get("expected_paths", [])]
        top_results: list[dict[str, Any]] = []
        for item in case.get("results", [])[:top_k]:
            top_results.append(
                {
                    "path": canonicalize_result_path(str(item.get("path", ""))),
                    "score": float(item.get("score", 0.0)),
                    "lexical_overlap": float(item.get("lexical_score", 0.0)),
                }
            )

        missing_on_disk: list[str] = []
        for path in expected:
            if not (HOME / path).exists():
                missing_on_disk.append(path)

        issues.append(
            {
                "id": case.get("id", "unknown"),
                "query": case.get("query", ""),
                "type": "miss" if is_failure else "weak_rank",
                "first_hit_rank": first_hit_rank,
                "expected_paths": expected,
                "missing_expected_on_disk": missing_on_disk,
                "top_results": top_results,
                "guidance": "Tighten expected_paths, improve doc headings/chunking, or adjust lexical weight for exact-token queries.",
            }
        )

    return {
        "issue_count": len(issues),
        "rank_warn_threshold": rank_warn_threshold,
        "issues": issues,
    }


def write_triage_markdown(triage: dict[str, Any], path: Path) -> None:
    lines = [
        "# Retrieval Failure Triage",
        "",
        f"- Issues: `{triage.get('issue_count', 0)}`",
        f"- Rank warning threshold: `{triage.get('rank_warn_threshold', 0)}`",
        "",
    ]
    issues = triage.get("issues", [])
    if not isinstance(issues, list) or not issues:
        lines.append("- No triage issues. All cases met rank threshold.")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    for issue in issues:
        lines.append(f"## {issue.get('id', 'unknown')} ({issue.get('type', 'issue')})")
        if issue.get("query"):
            lines.append(f"- Query: `{issue.get('query')}`")
        if "first_hit_rank" in issue:
            lines.append(f"- first_hit_rank: `{issue.get('first_hit_rank')}`")
        expected_paths = issue.get("expected_paths", [])
        if isinstance(expected_paths, list) and expected_paths:
            lines.append("- Expected paths:")
            for p in expected_paths:
                lines.append(f"  - `{p}`")
        missing = issue.get("missing_expected_on_disk", [])
        if isinstance(missing, list) and missing:
            lines.append("- Missing expected on disk:")
            for p in missing:
                lines.append(f"  - `{p}`")
        top_results = issue.get("top_results", [])
        if isinstance(top_results, list) and top_results:
            lines.append("- Top results:")
            for item in top_results:
                lines.append(
                    f"  - `{item.get('path', '')}` score={float(item.get('score', 0.0)):.4f} lexical={float(item.get('lexical_overlap', 0.0)):.4f}"
                )
        if issue.get("guidance"):
            lines.append(f"- Guidance: {issue.get('guidance')}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate_gates(
    *,
    summary: dict[str, Any],
    freshness: dict[str, Any],
    integrity: dict[str, Any],
    min_hit_rate: float,
    min_mrr: float,
    min_ndcg: float,
    max_index_age_minutes: float,
    max_source_lag_minutes: float,
    max_invalid_path_ratio: float,
    max_legacy_path_ratio: float,
    capability: dict[str, Any],
    require_dense_capability: bool,
) -> dict[str, Any]:
    failures: list[str] = []

    hit_rate = float(summary.get("hit_rate_at_k", 0.0))
    mrr = float(summary.get("mrr_at_k", 0.0))
    ndcg = float(summary.get("ndcg_at_k", 0.0))
    if hit_rate < min_hit_rate:
        failures.append(f"hit_rate_at_k {hit_rate:.4f} < min_hit_rate {min_hit_rate:.4f}")
    if mrr < min_mrr:
        failures.append(f"mrr_at_k {mrr:.4f} < min_mrr {min_mrr:.4f}")
    if ndcg < min_ndcg:
        failures.append(f"ndcg_at_k {ndcg:.4f} < min_ndcg {min_ndcg:.4f}")

    seconds_since_build = freshness.get("seconds_since_build")
    if isinstance(seconds_since_build, (int, float)):
        build_age_minutes = seconds_since_build / 60.0
        if build_age_minutes > max_index_age_minutes:
            failures.append(
                f"index_age_minutes {build_age_minutes:.2f} > max_index_age_minutes {max_index_age_minutes:.2f}"
            )

    source_lag_seconds = float(freshness.get("source_to_index_lag_seconds", 0.0))
    source_lag_minutes = source_lag_seconds / 60.0
    if source_lag_minutes > max_source_lag_minutes:
        failures.append(
            f"source_to_index_lag_minutes {source_lag_minutes:.2f} > max_source_lag_minutes {max_source_lag_minutes:.2f}"
        )

    invalid_ratio = float(integrity.get("invalid_path_ratio", 0.0))
    legacy_ratio = float(integrity.get("legacy_path_ratio", 0.0))
    if invalid_ratio > max_invalid_path_ratio:
        failures.append(
            f"invalid_path_ratio {invalid_ratio:.4f} > max_invalid_path_ratio {max_invalid_path_ratio:.4f}"
        )
    if legacy_ratio > max_legacy_path_ratio:
        failures.append(
            f"legacy_path_ratio {legacy_ratio:.4f} > max_legacy_path_ratio {max_legacy_path_ratio:.4f}"
        )
    if require_dense_capability and not bool(capability.get("ok", False)):
        failures.append(f"dense_capability_check failed: {capability.get('error', 'unknown error')}")

    return {
        "ok": len(failures) == 0,
        "failures": failures,
    }


def aggregate_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    good = [c for c in cases if "error" not in c]
    if not good:
        return {}
    n = len(good)
    return {
        "cases": n,
        "hit_rate_at_k": sum(c["hit_at_k"] for c in good) / n,
        "mrr_at_k": sum(c["mrr_at_k"] for c in good) / n,
        "ndcg_at_k": sum(c["ndcg_at_k"] for c in good) / n,
        "precision_at_k": sum(c["precision_at_k"] for c in good) / n,
        "recall_at_k": sum(c["recall_at_k"] for c in good) / n,
    }


def _self_test() -> None:
    sample_results = [{"path": "docs/a.md"}, {"path": "docs/b.md"}]
    expected = ["docs/a.md"]
    assert reciprocal_rank(sample_results, expected, 5) == 1.0
    assert ndcg_at_k(sample_results, expected, 5) > 0
    assert canonicalize_result_path("docs/knowledge-memory/README.md").startswith("control/knowledge/knowledge-memory/")
    cap = check_dense_capability({"ollama": {"host": "http://127.0.0.1:11434", "model": "nomic-embed-text:latest"}}, timeout_s=0.1, max_latency_ms=999999.0, min_dim=1)
    assert isinstance(cap, dict)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local memory retrieval against golden queries.")
    parser.add_argument("--index", type=str, default=str(DEFAULT_INDEX))
    parser.add_argument("--dataset", type=str, default=str(DEFAULT_DATASET))
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--w-sparse", type=float, default=0.45)
    parser.add_argument("--w-dense", type=float, default=0.45)
    parser.add_argument("--w-lexical", type=float, default=0.10)
    parser.add_argument("--ollama-timeout", type=float, default=20.0)
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--enforce-gates", action="store_true", help="Exit non-zero when gate thresholds fail.")
    parser.add_argument("--min-hit-rate", type=float, default=0.55)
    parser.add_argument("--min-mrr", type=float, default=0.33)
    parser.add_argument("--min-ndcg", type=float, default=0.60)
    parser.add_argument("--max-index-age-minutes", type=float, default=180.0)
    parser.add_argument("--max-source-lag-minutes", type=float, default=20.0)
    parser.add_argument("--max-invalid-path-ratio", type=float, default=0.00)
    parser.add_argument("--max-legacy-path-ratio", type=float, default=0.00)
    parser.add_argument("--require-dense-capability", action="store_true", help="Fail gates if embed capability probe fails.")
    parser.add_argument("--max-embed-latency-ms", type=float, default=5000.0)
    parser.add_argument("--min-embed-dim", type=int, default=256)
    parser.add_argument("--triage-rank-warn-threshold", type=int, default=3)
    parser.add_argument("--fusion-mode", choices=["rrf", "linear"], default="rrf", help="Score fusion strategy (default: rrf).")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    index_path = Path(args.index)
    dataset_path = Path(args.dataset)
    if not index_path.exists():
        raise SystemExit(f"index file not found: {index_path}")
    if not dataset_path.exists():
        raise SystemExit(f"dataset file not found: {dataset_path}")

    payload = json.loads(index_path.read_text())
    dataset = json.loads(dataset_path.read_text())
    queries = dataset.get("queries", []) if isinstance(dataset, dict) else []
    if not isinstance(queries, list):
        raise SystemExit("dataset queries must be a list")

    case_results: list[dict[str, Any]] = []
    for case in queries:
        if not isinstance(case, dict):
            continue
        case_results.append(
            evaluate_case(
                case=case,
                payload=payload,
                top_k=args.top_k,
                w_sparse=args.w_sparse,
                w_dense=args.w_dense,
                w_lexical=args.w_lexical,
                ollama_timeout=args.ollama_timeout,
                fusion_mode=args.fusion_mode,
            )
        )

    summary = aggregate_metrics(case_results)
    freshness = analyze_index_freshness(index_path=index_path, payload=payload, knowledge_root=ROOT)
    integrity = analyze_reference_integrity(case_results=case_results, top_k=args.top_k)
    capability = check_dense_capability(
        payload=payload,
        timeout_s=args.ollama_timeout,
        max_latency_ms=args.max_embed_latency_ms,
        min_dim=max(1, args.min_embed_dim),
    )
    gates = evaluate_gates(
        summary=summary,
        freshness=freshness,
        integrity=integrity,
        min_hit_rate=args.min_hit_rate,
        min_mrr=args.min_mrr,
        min_ndcg=args.min_ndcg,
        max_index_age_minutes=args.max_index_age_minutes,
        max_source_lag_minutes=args.max_source_lag_minutes,
        max_invalid_path_ratio=args.max_invalid_path_ratio,
        max_legacy_path_ratio=args.max_legacy_path_ratio,
        capability=capability,
        require_dense_capability=bool(args.require_dense_capability),
    )
    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "index": str(index_path),
        "dataset": str(dataset_path),
        "top_k": args.top_k,
        "fusion_mode": args.fusion_mode,
        "weights": {"sparse": args.w_sparse, "dense": args.w_dense, "lexical": args.w_lexical},
        "summary": summary,
        "freshness": freshness,
        "reference_integrity": integrity,
        "capability_health": capability,
        "gates": {
            "thresholds": {
                "min_hit_rate": args.min_hit_rate,
                "min_mrr": args.min_mrr,
                "min_ndcg": args.min_ndcg,
                "max_index_age_minutes": args.max_index_age_minutes,
                "max_source_lag_minutes": args.max_source_lag_minutes,
                "max_invalid_path_ratio": args.max_invalid_path_ratio,
                "max_legacy_path_ratio": args.max_legacy_path_ratio,
                "require_dense_capability": bool(args.require_dense_capability),
                "max_embed_latency_ms": args.max_embed_latency_ms,
                "min_embed_dim": args.min_embed_dim,
            },
            "result": gates,
        },
        "cases": case_results,
    }

    if args.output:
        out_path = Path(args.output)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        tag = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = OUTPUT_DIR / f"benchmark-{tag}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    triage = build_failure_triage(
        case_results=case_results,
        top_k=args.top_k,
        rank_warn_threshold=max(1, args.triage_rank_warn_threshold),
    )
    TRIAGE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = out_path.stem.replace("benchmark-", "")
    triage_json_path = TRIAGE_DIR / f"triage-{stamp}.json"
    triage_md_path = TRIAGE_DIR / f"triage-{stamp}.md"
    triage_json_path.write_text(json.dumps(triage, indent=2) + "\n", encoding="utf-8")
    write_triage_markdown(triage, triage_md_path)
    report["triage"] = {
        "issue_count": triage.get("issue_count", 0),
        "triage_json": str(triage_json_path),
        "triage_md": str(triage_md_path),
    }

    out_path.write_text(json.dumps(report, indent=2))

    print(
        json.dumps(
            {
                "report": str(out_path),
                "summary": summary,
                "freshness": freshness,
                "reference_integrity": integrity,
                "capability_health": capability,
                "triage": report["triage"],
                "gate_ok": gates["ok"],
            },
            indent=2,
        )
    )
    if args.enforce_gates and not gates["ok"]:
        print("gate failures:")
        for failure in gates["failures"]:
            print(f"- {failure}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
