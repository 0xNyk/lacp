#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
BENCH_DIR = ROOT / "data" / "benchmarks"
THRESHOLDS_FILE = ROOT / "benchmarks" / "thresholds.env"
OUT_DIR = BENCH_DIR / "recalibration"

DEFAULTS = {
    "MEMORY_BENCH_MIN_HIT_RATE": 0.55,
    "MEMORY_BENCH_MIN_MRR": 0.33,
    "MEMORY_BENCH_MIN_NDCG": 0.60,
    "MEMORY_BENCH_MAX_INDEX_AGE_MINUTES": 180.0,
    "MEMORY_BENCH_MAX_SOURCE_LAG_MINUTES": 20.0,
    "MEMORY_BENCH_MAX_EMBED_LATENCY_MS": 5000.0,
    "MEMORY_BENCH_MIN_EMBED_DIM": 256.0,
    "MEMORY_BENCH_MAX_INVALID_PATH_RATIO": 0.0,
    "MEMORY_BENCH_MAX_LEGACY_PATH_RATIO": 0.0,
}

FLOORS = {
    "MEMORY_BENCH_MIN_HIT_RATE": 0.45,
    "MEMORY_BENCH_MIN_MRR": 0.25,
    "MEMORY_BENCH_MIN_NDCG": 0.50,
}

CEILINGS = {
    "MEMORY_BENCH_MAX_INDEX_AGE_MINUTES": 720.0,
    "MEMORY_BENCH_MAX_SOURCE_LAG_MINUTES": 180.0,
    "MEMORY_BENCH_MAX_EMBED_LATENCY_MS": 20000.0,
    "MEMORY_BENCH_MAX_INVALID_PATH_RATIO": 0.15,
    "MEMORY_BENCH_MAX_LEGACY_PATH_RATIO": 0.15,
}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _load_report(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary")
    generated_at = payload.get("generated_at")
    if not isinstance(summary, dict) or not isinstance(generated_at, str):
        return None
    return payload


def _collect_reports(bench_dir: Path, limit: int) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(bench_dir.glob("benchmark-*.json")):
        payload = _load_report(path)
        if payload is None:
            continue
        try:
            ts = _parse_time(str(payload.get("generated_at")))
        except Exception:
            continue
        reports.append({"path": str(path), "ts": ts, "payload": payload})
    reports.sort(key=lambda item: item["ts"])
    if limit > 0:
        reports = reports[-limit:]
    return reports


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    q = min(1.0, max(0.0, q))
    idx = q * (len(ordered) - 1)
    lo = int(idx)
    hi = min(len(ordered) - 1, lo + 1)
    frac = idx - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _load_existing_thresholds(path: Path) -> dict[str, float]:
    values = dict(DEFAULTS)
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if key in values:
            try:
                values[key] = float(raw)
            except ValueError:
                pass
    return values


def _format_thresholds_env(values: dict[str, float]) -> str:
    lines = [
        "# Memory retrieval benchmark thresholds.",
        "# Updated manually or by run_memory_threshold_recalibration.sh.",
        "",
    ]
    ordered_keys = [
        "MEMORY_BENCH_MIN_HIT_RATE",
        "MEMORY_BENCH_MIN_MRR",
        "MEMORY_BENCH_MIN_NDCG",
        "MEMORY_BENCH_MAX_INDEX_AGE_MINUTES",
        "MEMORY_BENCH_MAX_SOURCE_LAG_MINUTES",
        "MEMORY_BENCH_MAX_EMBED_LATENCY_MS",
        "MEMORY_BENCH_MIN_EMBED_DIM",
        "MEMORY_BENCH_MAX_INVALID_PATH_RATIO",
        "MEMORY_BENCH_MAX_LEGACY_PATH_RATIO",
    ]
    for key in ordered_keys:
        value = float(values.get(key, DEFAULTS[key]))
        if key in ("MEMORY_BENCH_MIN_EMBED_DIM", "MEMORY_BENCH_MAX_INDEX_AGE_MINUTES", "MEMORY_BENCH_MAX_SOURCE_LAG_MINUTES"):
            lines.append(f"{key}={int(round(value))}")
        elif key in ("MEMORY_BENCH_MAX_EMBED_LATENCY_MS",):
            lines.append(f"{key}={int(round(value))}")
        elif key.endswith("_RATIO"):
            lines.append(f"{key}={value:.4f}".rstrip("0").rstrip("."))
        else:
            lines.append(f"{key}={value:.2f}")
    return "\n".join(lines) + "\n"


def _extract_metric(report: dict[str, Any], path: list[str], default: float = 0.0) -> float:
    cur: Any = report
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    if isinstance(cur, (int, float)):
        return float(cur)
    return default


def _recommend_thresholds(reports: list[dict[str, Any]], current: dict[str, float]) -> dict[str, float]:
    if not reports:
        return dict(current)
    payloads = [r["payload"] for r in reports]

    hit_vals = [_extract_metric(p, ["summary", "hit_rate_at_k"]) for p in payloads]
    mrr_vals = [_extract_metric(p, ["summary", "mrr_at_k"]) for p in payloads]
    ndcg_vals = [_extract_metric(p, ["summary", "ndcg_at_k"]) for p in payloads]

    age_vals = [_extract_metric(p, ["freshness", "seconds_since_build"]) / 60.0 for p in payloads]
    lag_vals = [_extract_metric(p, ["freshness", "source_to_index_lag_seconds"]) / 60.0 for p in payloads]
    invalid_vals = [_extract_metric(p, ["reference_integrity", "invalid_path_ratio"]) for p in payloads]
    legacy_vals = [_extract_metric(p, ["reference_integrity", "legacy_path_ratio"]) for p in payloads]

    out = dict(current)
    out["MEMORY_BENCH_MIN_HIT_RATE"] = max(FLOORS["MEMORY_BENCH_MIN_HIT_RATE"], _quantile(hit_vals, 0.2))
    out["MEMORY_BENCH_MIN_MRR"] = max(FLOORS["MEMORY_BENCH_MIN_MRR"], _quantile(mrr_vals, 0.2))
    out["MEMORY_BENCH_MIN_NDCG"] = max(FLOORS["MEMORY_BENCH_MIN_NDCG"], _quantile(ndcg_vals, 0.2))

    out["MEMORY_BENCH_MAX_INDEX_AGE_MINUTES"] = min(
        CEILINGS["MEMORY_BENCH_MAX_INDEX_AGE_MINUTES"],
        max(DEFAULTS["MEMORY_BENCH_MAX_INDEX_AGE_MINUTES"], _quantile(age_vals, 0.95) * 1.2),
    )
    out["MEMORY_BENCH_MAX_SOURCE_LAG_MINUTES"] = min(
        CEILINGS["MEMORY_BENCH_MAX_SOURCE_LAG_MINUTES"],
        max(DEFAULTS["MEMORY_BENCH_MAX_SOURCE_LAG_MINUTES"], _quantile(lag_vals, 0.95) * 1.2),
    )
    out["MEMORY_BENCH_MAX_INVALID_PATH_RATIO"] = min(
        CEILINGS["MEMORY_BENCH_MAX_INVALID_PATH_RATIO"],
        max(0.0, _quantile(invalid_vals, 0.95) + 0.005),
    )
    out["MEMORY_BENCH_MAX_LEGACY_PATH_RATIO"] = min(
        CEILINGS["MEMORY_BENCH_MAX_LEGACY_PATH_RATIO"],
        max(0.0, _quantile(legacy_vals, 0.95) + 0.005),
    )
    return out


def _write_markdown(
    *,
    path: Path,
    reports: list[dict[str, Any]],
    current: dict[str, float],
    recommended: dict[str, float],
    applied: bool,
    thresholds_file: Path,
) -> None:
    lines = [
        "# Memory Threshold Recalibration",
        "",
        f"- Generated: `{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}`",
        f"- Reports analyzed: `{len(reports)}`",
        f"- Thresholds file: `{thresholds_file}`",
        f"- Applied: `{str(applied).lower()}`",
        "",
        "## Recommendations",
        "",
    ]
    for key in DEFAULTS:
        before = float(current.get(key, DEFAULTS[key]))
        after = float(recommended.get(key, before))
        delta = after - before
        lines.append(f"- `{key}`: current={before:.4f} recommended={after:.4f} delta={delta:+.4f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _self_test() -> None:
    vals = [1.0, 2.0, 3.0, 4.0]
    assert abs(_quantile(vals, 0.5) - 2.5) < 1e-9
    existing = _load_existing_thresholds(Path("/tmp/does-not-exist"))
    assert isinstance(existing, dict)
    assert "MEMORY_BENCH_MIN_MRR" in existing


def main() -> int:
    parser = argparse.ArgumentParser(description="Recalibrate memory benchmark gate thresholds from recent benchmark history.")
    parser.add_argument("--bench-dir", type=str, default=str(BENCH_DIR))
    parser.add_argument("--thresholds-file", type=str, default=str(THRESHOLDS_FILE))
    parser.add_argument("--limit", type=int, default=60, help="Number of latest benchmark reports to analyze.")
    parser.add_argument("--apply", action="store_true", help="Write recommended values into thresholds file.")
    parser.add_argument("--output-json", type=str, default="")
    parser.add_argument("--output-md", type=str, default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    bench_dir = Path(args.bench_dir)
    thresholds_file = Path(args.thresholds_file)
    reports = _collect_reports(bench_dir, limit=max(1, args.limit))
    current = _load_existing_thresholds(thresholds_file)
    recommended = _recommend_thresholds(reports, current)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_json = Path(args.output_json) if args.output_json else OUT_DIR / f"recalibration-{stamp}.json"
    out_md = Path(args.output_md) if args.output_md else OUT_DIR / f"recalibration-{stamp}.md"

    applied = False
    if args.apply:
        thresholds_file.parent.mkdir(parents=True, exist_ok=True)
        thresholds_file.write_text(_format_thresholds_env(recommended), encoding="utf-8")
        applied = True

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "bench_dir": str(bench_dir),
        "thresholds_file": str(thresholds_file),
        "reports_analyzed": len(reports),
        "applied": applied,
        "current": current,
        "recommended": recommended,
        "latest_reports": [r["path"] for r in reports[-10:]],
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_markdown(
        path=out_md,
        reports=reports,
        current=current,
        recommended=recommended,
        applied=applied,
        thresholds_file=thresholds_file,
    )

    print(
        json.dumps(
            {
                "ok": True,
                "reports_analyzed": len(reports),
                "applied": applied,
                "thresholds_file": str(thresholds_file),
                "output_json": str(out_json),
                "output_md": str(out_md),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
