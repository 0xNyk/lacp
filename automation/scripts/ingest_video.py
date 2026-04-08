#!/usr/bin/env python3
"""Ingest video/audio content into the Obsidian knowledge brain.

Downloads audio from YouTube or other video URLs, transcribes locally with
mlx-whisper, extracts structured knowledge via a local ollama model, deduplicates
against the research registry, and writes novel insights as inbox notes.

Usage:
    python3 ingest_video.py "https://youtube.com/watch?v=..." [--apply]
    python3 ingest_video.py "https://youtube.com/watch?v=..." --model qwen3.5:35b-a3b
    python3 ingest_video.py "/path/to/local.mp4" --apply
    python3 ingest_video.py --transcript "/path/to/existing.txt" --title "Talk Title" --apply

Options:
    --apply             Actually write to Obsidian inbox (default: dry-run)
    --model MODEL       Ollama model for extraction (default: granite4)
    --whisper-model M   mlx-whisper model (default: mlx-community/whisper-large-v3-turbo)
    --language LANG     Audio language hint (default: auto-detect)
    --transcript FILE   Skip download+transcribe, use existing transcript file
    --title TITLE       Override auto-detected title
    --keep-audio        Don't delete temp audio after transcription
    --keep-transcript   Save raw transcript alongside the note
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))

# Paths
KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DATA_DIR = KNOWLEDGE_ROOT / "data" / "research"
REGISTRY_FILE = DATA_DIR / "registry.json"
INBOX_DIR = Path.home() / "obsidian" / "nyk" / "inbox"
TRANSCRIPT_DIR = KNOWLEDGE_ROOT / "data" / "transcripts"

# Tools
YT_DLP = "yt-dlp"
MLX_WHISPER = str(Path.home() / ".venvs" / "whisper" / "bin" / "mlx_whisper")
WHISPER_PYTHON = str(Path.home() / ".venvs" / "whisper" / "bin" / "python")
WHISPER_CPU_PYTHON = str(Path.home() / ".venvs" / "whisper-cpu" / "bin" / "python")
OLLAMA_HOST = "http://localhost:11434"
DEFAULT_EXTRACT_MODEL = "granite4"
DEFAULT_WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"

# Import shared pipeline utilities
from sync_research_knowledge import (  # noqa: E402
    DEFAULT_CATEGORY_RULES,
    classify_categories,
    load_taxonomy,
)


# ---------------------------------------------------------------------------
# Step 1: Download audio
# ---------------------------------------------------------------------------

def is_url(s: str) -> bool:
    """Check if string looks like a URL."""
    try:
        r = urlparse(s)
        return r.scheme in ("http", "https") and bool(r.netloc)
    except Exception:
        return False


def download_audio(url: str, output_dir: str) -> tuple[str, dict[str, Any]]:
    """Download audio from video URL using yt-dlp.

    Returns (audio_path, metadata_dict).
    """
    # First get metadata
    meta_cmd = [YT_DLP, "--dump-json", "--no-download", url]
    print(f"  Fetching metadata from {url}...")
    meta_result = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=60)
    metadata: dict[str, Any] = {}
    if meta_result.returncode == 0 and meta_result.stdout.strip():
        try:
            metadata = json.loads(meta_result.stdout)
        except json.JSONDecodeError:
            pass

    # Download audio
    output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
    dl_cmd = [
        YT_DLP,
        "-x",
        "--audio-format", "m4a",
        "--audio-quality", "0",
        "-o", output_template,
        "--no-playlist",
        url,
    ]
    print(f"  Downloading audio...")
    dl_result = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=1800)
    if dl_result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {dl_result.stderr[:500]}")

    # Find the downloaded file
    for f in Path(output_dir).iterdir():
        if f.suffix in (".m4a", ".mp3", ".wav", ".opus", ".ogg", ".webm"):
            return str(f), metadata

    raise RuntimeError(f"No audio file found in {output_dir} after download")


# ---------------------------------------------------------------------------
# Step 2: Transcribe with mlx-whisper
# ---------------------------------------------------------------------------

def python_has_module(python_bin: str, module_name: str) -> bool:
    if not Path(python_bin).exists():
        return False
    proc = subprocess.run(
        [
            python_bin,
            "-c",
            (
                "import importlib.util, sys; "
                f"raise SystemExit(0 if importlib.util.find_spec('{module_name}') else 1)"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return proc.returncode == 0


def transcribe_audio(
    audio_path: str,
    output_dir: str,
    whisper_model: str = DEFAULT_WHISPER_MODEL,
    language: str | None = None,
    backend: str = "auto",
) -> str:
    """Transcribe audio file with backend fallback. Returns transcript text."""
    errors: list[str] = []
    enable_mlx = os.environ.get("INGEST_ENABLE_MLX", "0") == "1"

    def read_txt_output() -> str:
        for f in Path(output_dir).iterdir():
            if f.suffix == ".txt":
                text = f.read_text(encoding="utf-8").strip()
                if text:
                    return text
        raise RuntimeError("No transcript output found")

    if backend in {"auto", "mlx"}:
        if enable_mlx:
            if sys.version_info >= (3, 12):
                errors.append("mlx backend refused on Python 3.12 (known unstable on this host)")
            elif not python_has_module(WHISPER_PYTHON, "mlx_whisper"):
                errors.append(f"mlx backend unavailable: mlx_whisper missing in {WHISPER_PYTHON}")
            else:
                cmd = [
                    MLX_WHISPER,
                    audio_path,
                    "--model", whisper_model,
                    "--output-format", "txt",
                    "--output-dir", output_dir,
                ]
                if language:
                    cmd.extend(["--language", language])
                print(f"  Transcribing with MLX ({whisper_model})...")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                if result.returncode == 0:
                    return read_txt_output()
                errors.append(f"mlx_whisper failed: {result.stderr[:500]}")
        else:
            errors.append("mlx backend disabled (set INGEST_ENABLE_MLX=1 to enable)")

    if backend in {"auto", "faster-whisper"}:
        if not python_has_module(WHISPER_CPU_PYTHON, "faster_whisper"):
            errors.append(f"faster-whisper missing in {WHISPER_CPU_PYTHON}")
        else:
            cmd = [
                WHISPER_CPU_PYTHON,
                "-c",
                (
                    "from faster_whisper import WhisperModel;"
                    "import sys, pathlib;"
                    f"model=WhisperModel('small', device='cpu', compute_type='int8');"
                    "segments,_=model.transcribe(sys.argv[1], language=None);"
                    "text='\\n'.join(s.text.strip() for s in segments if s.text.strip());"
                    "pathlib.Path(sys.argv[2]).write_text(text, encoding='utf-8')"
                ),
                audio_path,
                str(Path(output_dir) / "transcript.txt"),
            ]
            print("  Transcribing with faster-whisper (CPU fallback)...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5400)
            if result.returncode == 0:
                return read_txt_output()
            errors.append(f"faster-whisper failed: {result.stderr[:500]}")

    raise RuntimeError("; ".join(errors) if errors else "No transcription backend succeeded")


# ---------------------------------------------------------------------------
# Step 3: Extract knowledge via local LLM
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are a knowledge extraction system. Given a video transcript, extract structured knowledge.

Return ONLY valid JSON with this exact structure:
{
  "title": "Concise title for the content (max 80 chars)",
  "summary": "2-3 sentence summary of the key message",
  "key_insights": [
    "First key insight or claim (one sentence each)",
    "Second key insight",
    "Third key insight"
  ],
  "concepts": ["concept1", "concept2"],
  "entities": ["person or org mentioned"],
  "actionable_takeaways": ["Concrete takeaway 1", "Takeaway 2"],
  "topics": ["topic1", "topic2"]
}

Rules:
- Extract 3-7 key insights (the most important non-obvious claims or ideas)
- concepts = abstract ideas discussed (e.g. "retrieval augmented generation", "agent orchestration")
- entities = specific people, companies, projects, tools mentioned
- actionable_takeaways = things the viewer could DO based on this content
- topics = broad categories (e.g. "ai-agents", "quantitative-finance", "security")
- Do NOT include filler, timestamps, or transcript artifacts
- Focus on NOVEL information — things that add to understanding
- If the transcript is in a non-English language, still output JSON in English

TRANSCRIPT:
{transcript}"""


def extract_knowledge(
    transcript: str,
    model: str = DEFAULT_EXTRACT_MODEL,
) -> dict[str, Any]:
    """Extract structured knowledge from transcript using local ollama model."""
    # Truncate very long transcripts to fit context window
    max_chars = 28000  # ~7K tokens, leaves room for prompt + response
    if len(transcript) > max_chars:
        # Take first 60% and last 20% to capture intro + conclusion
        head = transcript[: int(max_chars * 0.6)]
        tail = transcript[-int(max_chars * 0.2) :]
        transcript = head + "\n\n[... middle section truncated ...]\n\n" + tail
        print(f"  Transcript truncated to ~{max_chars} chars for extraction")

    prompt = EXTRACTION_PROMPT.replace("{transcript}", transcript)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 2000,
        },
    }

    print(f"  Extracting knowledge with {model}...")
    import urllib.request

    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode())

    raw = body.get("response", "")

    # Parse JSON from response (handle markdown code fences)
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    else:
        # Try to find raw JSON object
        brace_start = raw.find("{")
        brace_end = raw.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            raw = raw[brace_start : brace_end + 1]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  WARNING: Could not parse LLM JSON output, using raw text")
        return {
            "title": "Video Knowledge Extract",
            "summary": raw[:500],
            "key_insights": [],
            "concepts": [],
            "entities": [],
            "actionable_takeaways": [],
            "topics": [],
        }


# ---------------------------------------------------------------------------
# Step 4: Dedup against registry
# ---------------------------------------------------------------------------

def check_dedup(summary: str, insights: list[str]) -> tuple[bool, list[str]]:
    """Check if this content is semantically duplicate of existing knowledge.

    Returns (is_duplicate, related_nodes).
    """
    try:
        from semantic_dedup import compute_embedding, cosine_similarity, find_semantic_duplicates
    except ImportError:
        return False, []

    if not REGISTRY_FILE.exists():
        return False, []

    registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    items = registry.get("items", {})
    if not items:
        return False, []

    # Check summary against registry
    combined_text = summary + " " + " ".join(insights[:3])
    dupes = find_semantic_duplicates(combined_text, items, threshold=0.85, top_k=1)
    if dupes:
        return True, [d[0] for d in dupes]

    # Find related (but not duplicate) nodes
    vec = compute_embedding(combined_text)
    if not vec:
        return False, []

    related = []
    for item_id, item in items.items():
        cached_vec = item.get("embedding")
        if not isinstance(cached_vec, list) or not cached_vec:
            continue
        sim = cosine_similarity(vec, cached_vec)
        if 0.60 <= sim < 0.85:
            related.append(item_id)
            if len(related) >= 5:
                break

    return False, related


# ---------------------------------------------------------------------------
# Step 5: Write Obsidian note
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60]


def render_note(
    url: str,
    title: str,
    metadata: dict[str, Any],
    knowledge: dict[str, Any],
    transcript: str,
    related_nodes: list[str],
    keep_transcript: bool = False,
) -> tuple[str, str]:
    """Render an Obsidian inbox note. Returns (filename, content)."""
    note_id = f"video-{hashlib.sha1(url.encode()).hexdigest()[:12]}"
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Classify into research categories
    combined_text = f"{title} {knowledge.get('summary', '')} {' '.join(knowledge.get('concepts', []))}"
    taxonomy = load_taxonomy()
    category_rules = taxonomy.get("rules", DEFAULT_CATEGORY_RULES)
    categories = classify_categories(
        combined_text,
        rules=category_rules,
        default_category="general-research",
        max_categories=4,
    )
    tags_str = ", ".join(categories[:4])

    # Video metadata
    channel = metadata.get("channel", metadata.get("uploader", ""))
    duration = metadata.get("duration", 0)
    duration_str = f"{duration // 60}m {duration % 60}s" if duration else ""
    upload_date = metadata.get("upload_date", "")
    if upload_date and len(upload_date) == 8:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

    k_title = knowledge.get("title", title)
    summary = knowledge.get("summary", "")
    insights = knowledge.get("key_insights", [])
    concepts = knowledge.get("concepts", [])
    entities = knowledge.get("entities", [])
    takeaways = knowledge.get("actionable_takeaways", [])

    lines = [
        "---",
        f"id: {note_id}",
        f"created: {today}",
        "type: research",
        "status: inbox",
        "source: video-ingest",
        f"tags: [{tags_str}]",
        f"description: Video knowledge from {channel or 'unknown'} — {k_title}",
        f"url: \"{url}\"",
        "---",
        "",
        f"# {k_title}",
        "",
        "## Source",
        f"- URL: {url}",
    ]
    if channel:
        lines.append(f"- Channel: {channel}")
    if duration_str:
        lines.append(f"- Duration: {duration_str}")
    if upload_date:
        lines.append(f"- Published: {upload_date}")

    if summary:
        lines.extend(["", "## Summary", "", summary])

    if insights:
        lines.extend(["", "## Key Insights", ""])
        for i, insight in enumerate(insights, 1):
            lines.append(f"{i}. {insight}")

    if concepts:
        lines.extend(["", "## Concepts", ""])
        # Use wikilinks for concepts
        lines.append(" | ".join(f"[[{c}]]" for c in concepts))

    if entities:
        lines.extend(["", "## Entities", ""])
        lines.append(", ".join(entities))

    if takeaways:
        lines.extend(["", "## Actionable Takeaways", ""])
        for t in takeaways:
            lines.append(f"- [ ] {t}")

    if related_nodes:
        lines.extend(["", "## Related Knowledge", ""])
        for node_id in related_nodes:
            lines.append(f"- [[{node_id}]]")

    if keep_transcript and transcript:
        lines.extend([
            "",
            "## Raw Transcript",
            "",
            "<details>",
            "<summary>Full transcript (click to expand)</summary>",
            "",
            transcript[:10000],
            "",
            "</details>",
        ])

    lines.append("")

    slug = slugify(k_title)
    filename = f"video-{slug}.md"
    return filename, "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest video into Obsidian knowledge brain")
    parser.add_argument("url", nargs="?", help="Video URL or local file path")
    parser.add_argument("--apply", action="store_true", help="Write to inbox (default: dry-run)")
    parser.add_argument("--model", default=DEFAULT_EXTRACT_MODEL, help=f"Ollama extraction model (default: {DEFAULT_EXTRACT_MODEL})")
    parser.add_argument("--whisper-model", default=DEFAULT_WHISPER_MODEL, help="mlx-whisper model (used when backend=mlx)")
    parser.add_argument("--language", help="Audio language hint")
    parser.add_argument("--backend", default=os.environ.get("INGEST_TRANSCRIBE_BACKEND", "auto"), choices=["auto", "mlx", "faster-whisper"], help="Transcription backend")
    parser.add_argument("--transcript", help="Use existing transcript file (skip download+transcribe)")
    parser.add_argument("--title", help="Override auto-detected title")
    parser.add_argument("--keep-audio", action="store_true", help="Keep temp audio file")
    parser.add_argument("--keep-transcript", action="store_true", help="Include raw transcript in note")
    args = parser.parse_args()

    if not args.url and not args.transcript:
        parser.error("Provide a URL/file path, or --transcript with an existing file")

    url = args.url or "local-transcript"
    metadata: dict[str, Any] = {}
    transcript = ""
    title = args.title or ""

    # Stage 1: Get transcript
    if args.transcript:
        print(f"[1/4] Using existing transcript: {args.transcript}")
        transcript = Path(args.transcript).read_text(encoding="utf-8").strip()
        if not title:
            title = Path(args.transcript).stem.replace("-", " ").replace("_", " ").title()
    else:
        with tempfile.TemporaryDirectory(prefix="brain-ingest-") as tmpdir:
            # Download if URL
            if is_url(url):
                print(f"[1/4] Downloading audio from {url}")
                audio_path, metadata = download_audio(url, tmpdir)
                title = title or metadata.get("title", "")
            else:
                # Local file
                print(f"[1/4] Using local file: {url}")
                audio_path = url

            # Transcribe
            print(f"[2/4] Transcribing audio...")
            transcript_dir = tmpdir
            transcript = transcribe_audio(audio_path, transcript_dir, args.whisper_model, args.language, args.backend)

            # Optionally save transcript
            if args.keep_audio and is_url(url):
                save_path = TRANSCRIPT_DIR / f"{Path(audio_path).stem}.m4a"
                save_path.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(audio_path, save_path)
                print(f"  Audio saved: {save_path}")

    if not transcript:
        print("ERROR: Empty transcript, nothing to process")
        sys.exit(1)

    word_count = len(transcript.split())
    print(f"  Transcript: {word_count} words ({len(transcript)} chars)")

    # Save raw transcript
    if args.keep_transcript or True:  # Always save transcripts for reference
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        slug = slugify(title or "untitled")
        t_path = TRANSCRIPT_DIR / f"{slug}.txt"
        t_path.write_text(transcript, encoding="utf-8")
        print(f"  Transcript saved: {t_path}")

    # Stage 2: Extract knowledge
    print(f"[3/4] Extracting knowledge with {args.model}...")
    knowledge = extract_knowledge(transcript, args.model)
    if not title:
        title = knowledge.get("title", "Video Knowledge Extract")

    # Print extraction results
    print(f"\n  Title: {knowledge.get('title', title)}")
    print(f"  Summary: {knowledge.get('summary', '')[:200]}")
    insights = knowledge.get("key_insights", [])
    print(f"  Insights: {len(insights)}")
    for i, ins in enumerate(insights[:5], 1):
        print(f"    {i}. {ins}")
    concepts = knowledge.get("concepts", [])
    if concepts:
        print(f"  Concepts: {', '.join(concepts[:8])}")

    # Stage 3: Dedup
    print(f"\n[4/4] Checking for duplicates...")
    is_dup, related = check_dedup(
        knowledge.get("summary", ""),
        knowledge.get("key_insights", []),
    )

    if is_dup:
        print(f"  DUPLICATE detected (similar to: {related[0]})")
        print(f"  Skipping note creation. Use --force to override.")
        return

    if related:
        print(f"  Related nodes: {', '.join(related[:5])}")
    else:
        print(f"  No close matches found — novel content")

    # Render note
    filename, content = render_note(
        url=url,
        title=title,
        metadata=metadata,
        knowledge=knowledge,
        transcript=transcript,
        related_nodes=related,
        keep_transcript=args.keep_transcript,
    )

    if args.apply:
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        note_path = INBOX_DIR / filename
        # Avoid overwriting
        if note_path.exists():
            base = note_path.stem
            note_path = INBOX_DIR / f"{base}-{datetime.now(UTC).strftime('%H%M%S')}.md"
        note_path.write_text(content, encoding="utf-8")
        print(f"\n  Note written: {note_path}")
    else:
        print(f"\n  [DRY RUN] Would write: {INBOX_DIR / filename}")
        print(f"  ---")
        # Show first 30 lines
        for line in content.split("\n")[:30]:
            print(f"  {line}")
        print(f"  ... ({len(content.split(chr(10)))} total lines)")
        print(f"\n  Re-run with --apply to write to inbox")


if __name__ == "__main__":
    main()
