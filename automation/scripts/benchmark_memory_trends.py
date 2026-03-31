#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
BENCH_DIR = ROOT / "data" / "benchmarks"
OUT_DIR = ROOT / "data" / "benchmarks" / "trends"

METRICS = [
    "hit_rate_at_k",
    "mrr_at_k",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
]
DEFAULT_MAX_INDEX_AGE_MINUTES = 180.0
DEFAULT_MAX_SOURCE_LAG_MINUTES = 20.0
DEFAULT_MAX_INVALID_PATH_RATIO = 0.0
DEFAULT_MAX_LEGACY_PATH_RATIO = 0.0
DEFAULT_ALERT_STREAK = 2


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


def _metric_value(summary: dict[str, Any], metric: str) -> float:
    value = summary.get(metric)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _build_trend(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not reports:
        return {"count": 0, "metrics": {}, "history": []}

    latest = reports[-1]
    previous = reports[-2] if len(reports) > 1 else None

    metric_out: dict[str, Any] = {}
    for metric in METRICS:
        series = [_metric_value(r["payload"].get("summary", {}), metric) for r in reports]
        latest_val = series[-1]
        prev_val = series[-2] if len(series) > 1 else latest_val
        delta = latest_val - prev_val
        avg = sum(series) / len(series)
        metric_out[metric] = {
            "latest": round(latest_val, 6),
            "previous": round(prev_val, 6),
            "delta": round(delta, 6),
            "average": round(avg, 6),
            "samples": len(series),
        }

    history = [
        {
            "generated_at": r["payload"].get("generated_at"),
            "path": r["path"],
            "summary": r["payload"].get("summary", {}),
        }
        for r in reports
    ]

    return {
        "count": len(reports),
        "latest": {"generated_at": latest["payload"].get("generated_at"), "path": latest["path"]},
        "previous": (
            {"generated_at": previous["payload"].get("generated_at"), "path": previous["path"]}
            if previous
            else None
        ),
        "metrics": metric_out,
        "history": history,
    }


def _extract_slo_entry(report: dict[str, Any]) -> dict[str, Any]:
    payload = report.get("payload", {})
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    freshness = payload.get("freshness", {}) if isinstance(payload, dict) else {}
    integrity = payload.get("reference_integrity", {}) if isinstance(payload, dict) else {}
    gates = payload.get("gates", {}) if isinstance(payload, dict) else {}
    thresholds = gates.get("thresholds", {}) if isinstance(gates, dict) else {}

    index_age_minutes = 0.0
    seconds_since_build = freshness.get("seconds_since_build")
    if isinstance(seconds_since_build, (int, float)):
        index_age_minutes = float(seconds_since_build) / 60.0

    source_lag_minutes = float(freshness.get("source_to_index_lag_seconds", 0.0)) / 60.0
    invalid_ratio = float(integrity.get("invalid_path_ratio", 0.0))
    legacy_ratio = float(integrity.get("legacy_path_ratio", 0.0))

    max_index_age_minutes = float(thresholds.get("max_index_age_minutes", DEFAULT_MAX_INDEX_AGE_MINUTES))
    max_source_lag_minutes = float(thresholds.get("max_source_lag_minutes", DEFAULT_MAX_SOURCE_LAG_MINUTES))
    max_invalid_path_ratio = float(thresholds.get("max_invalid_path_ratio", DEFAULT_MAX_INVALID_PATH_RATIO))
    max_legacy_path_ratio = float(thresholds.get("max_legacy_path_ratio", DEFAULT_MAX_LEGACY_PATH_RATIO))

    breached = {
        "index_age": index_age_minutes > max_index_age_minutes,
        "source_lag": source_lag_minutes > max_source_lag_minutes,
        "invalid_paths": invalid_ratio > max_invalid_path_ratio,
        "legacy_paths": legacy_ratio > max_legacy_path_ratio,
    }

    return {
        "generated_at": payload.get("generated_at"),
        "path": report.get("path"),
        "index_age_minutes": round(index_age_minutes, 3),
        "source_lag_minutes": round(source_lag_minutes, 3),
        "invalid_path_ratio": round(invalid_ratio, 6),
        "legacy_path_ratio": round(legacy_ratio, 6),
        "thresholds": {
            "max_index_age_minutes": max_index_age_minutes,
            "max_source_lag_minutes": max_source_lag_minutes,
            "max_invalid_path_ratio": max_invalid_path_ratio,
            "max_legacy_path_ratio": max_legacy_path_ratio,
        },
        "breached": breached,
        "gate_ok": bool((gates.get("result", {}) if isinstance(gates, dict) else {}).get("ok", False)),
        "summary": {
            "hit_rate_at_k": float(summary.get("hit_rate_at_k", 0.0)),
            "mrr_at_k": float(summary.get("mrr_at_k", 0.0)),
            "ndcg_at_k": float(summary.get("ndcg_at_k", 0.0)),
        },
    }


def _compute_streak(entries: list[dict[str, Any]], key: str) -> int:
    streak = 0
    for entry in reversed(entries):
        breached = entry.get("breached", {})
        if isinstance(breached, dict) and bool(breached.get(key, False)):
            streak += 1
            continue
        break
    return streak


def _build_freshness_alerts(reports: list[dict[str, Any]], alert_streak: int) -> dict[str, Any]:
    if not reports:
        return {"status": "no-data", "alert_streak_threshold": alert_streak, "alerts": [], "latest": {}}
    entries = [_extract_slo_entry(r) for r in reports]
    latest = entries[-1]

    alerts: list[dict[str, Any]] = []
    for key in ("index_age", "source_lag", "invalid_paths", "legacy_paths"):
        streak = _compute_streak(entries, key)
        if streak >= max(1, alert_streak):
            alerts.append({"type": key, "streak": streak, "latest_breached": True})

    status = "alert" if alerts else "ok"
    return {
        "status": status,
        "alert_streak_threshold": alert_streak,
        "alerts": alerts,
        "latest": latest,
        "recent": entries[-7:],
    }


def _status(delta: float) -> str:
    if delta >= 0.01:
        return "improved"
    if delta <= -0.01:
        return "regressed"
    return "stable"


def _write_markdown(trend: dict[str, Any], md_path: Path) -> None:
    lines = [
        "# Memory Retrieval Benchmark Trends",
        "",
        f"Generated: {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}",
        f"Samples: {trend.get('count', 0)}",
        "",
        "## Metric Deltas (latest vs previous)",
        "",
    ]

    metrics = trend.get("metrics", {})
    if not isinstance(metrics, dict) or not metrics:
        lines.append("- No benchmark data available.")
    else:
        for metric in METRICS:
            info = metrics.get(metric, {})
            if not isinstance(info, dict):
                continue
            latest = float(info.get("latest", 0.0))
            previous = float(info.get("previous", 0.0))
            delta = float(info.get("delta", 0.0))
            lines.append(
                f"- `{metric}`: latest={latest:.4f}, previous={previous:.4f}, delta={delta:+.4f} ({_status(delta)})"
            )

    lines.extend(["", "## Latest Benchmark", ""])
    latest = trend.get("latest")
    if isinstance(latest, dict):
        lines.append(f"- `{latest.get('generated_at', '')}`")
        lines.append(f"- `{latest.get('path', '')}`")

    lines.extend(["", "## Freshness SLO Alerts", ""])
    freshness = trend.get("freshness_alerts", {})
    if not isinstance(freshness, dict) or freshness.get("status") == "no-data":
        lines.append("- No freshness data available.")
    else:
        lines.append(f"- Status: `{freshness.get('status', 'unknown')}`")
        lines.append(f"- Alert streak threshold: `{freshness.get('alert_streak_threshold', 0)}`")
        latest_f = freshness.get("latest", {})
        if isinstance(latest_f, dict):
            lines.append(f"- Latest index_age_minutes: `{float(latest_f.get('index_age_minutes', 0.0)):.2f}`")
            lines.append(f"- Latest source_lag_minutes: `{float(latest_f.get('source_lag_minutes', 0.0)):.2f}`")
            lines.append(f"- Latest invalid_path_ratio: `{float(latest_f.get('invalid_path_ratio', 0.0)):.4f}`")
            lines.append(f"- Latest legacy_path_ratio: `{float(latest_f.get('legacy_path_ratio', 0.0)):.4f}`")
        alerts = freshness.get("alerts", [])
        if isinstance(alerts, list) and alerts:
            lines.append("- Active alerts:")
            for alert in alerts:
                lines.append(f"  - `{alert.get('type', 'unknown')}` streak=`{int(alert.get('streak', 0))}`")
        else:
            lines.append("- Active alerts: none")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _self_test() -> None:
    now = datetime.now(timezone.utc)
    reports = [
        {
            "path": "a",
            "ts": now,
            "payload": {
                "generated_at": now.isoformat().replace("+00:00", "Z"),
                "summary": {
                    "hit_rate_at_k": 0.6,
                    "mrr_at_k": 0.4,
                    "ndcg_at_k": 0.7,
                    "precision_at_k": 0.2,
                    "recall_at_k": 0.5,
                },
            },
        }
    ]
    trend = _build_trend(reports)
    assert trend["count"] == 1
    assert "metrics" in trend


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate weekly trend report from memory retrieval benchmarks.")
    parser.add_argument("--bench-dir", type=str, default=str(BENCH_DIR))
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output-json", type=str, default="")
    parser.add_argument("--output-md", type=str, default="")
    parser.add_argument("--alert-streak", type=int, default=DEFAULT_ALERT_STREAK)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    bench_dir = Path(args.bench_dir)
    reports = _collect_reports(bench_dir, limit=args.limit)
    trend = _build_trend(reports)
    trend["freshness_alerts"] = _build_freshness_alerts(reports, alert_streak=max(1, args.alert_streak))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = Path(args.output_json) if args.output_json else OUT_DIR / f"trend-{stamp}.json"
    md_path = Path(args.output_md) if args.output_md else OUT_DIR / f"trend-{stamp}.md"

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "bench_dir": str(bench_dir),
        "trend": trend,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_markdown(trend, md_path)

    print(
        json.dumps(
            {
                "ok": True,
                "reports_scanned": trend.get("count", 0),
                "trend_json": str(json_path),
                "trend_md": str(md_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
