#!/usr/bin/env python3
"""Record voice from microphone, transcribe, append to today's Obsidian daily note.

MLX safety:
    This script defaults to MLX-disabled mode to avoid frequent macOS Metal crashes
    seen on this machine. To force-enable MLX transcription, set:
      VOICE_ENABLE_MLX=1
    For known-unstable runtimes, also set:
      VOICE_ALLOW_UNSTABLE_MLX=1

Fallback backend:
    When MLX is disabled/unavailable, this script can auto-fallback to CPU
    transcription with faster-whisper from ~/.venvs/whisper-cpu.

Usage:
    # Record until Ctrl+C, then transcribe and append
    python3 voice_daily_note.py

    # Record for 60 seconds max
    python3 voice_daily_note.py --duration 60

    # Transcribe an existing audio file
    python3 voice_daily_note.py --file /path/to/audio.wav

    # Dry-run (transcribe but don't write)
    python3 voice_daily_note.py --dry-run

    # Use a different whisper model
    python3 voice_daily_note.py --whisper-model mlx-community/whisper-large-v3
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Paths
DAILY_DIR = Path.home() / "obsidian" / "nyk" / "00-home" / "daily"
AUDIO_ARCHIVE = Path.home() / "control" / "knowledge" / "knowledge-memory" / "data" / "voice"
MLX_WHISPER = str(Path.home() / ".venvs" / "whisper" / "bin" / "mlx_whisper")
WHISPER_PYTHON = str(Path.home() / ".venvs" / "whisper" / "bin" / "python3")
WHISPER311_PYTHON = str(Path.home() / ".venvs" / "whisper311" / "bin" / "python3")
WHISPER_CPU_PYTHON = str(Path.home() / ".venvs" / "whisper-cpu" / "bin" / "python3")
DEFAULT_WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_CPU_MODEL = "small"

DAILY_TEMPLATE = """\
---
created: {date}
type: daily
tags: [daily]
---

# {date} {weekday}

## Focus

What am I working on today?

-

## Capture

Quick notes, ideas, links — process later via [[atlas/index|inbox workflow]].

-

## Voice Notes

> Transcribed voice memos from today.

## Agent Daily

> See today's agent capture: [[knowledge/memory/daily/{date}]]

## Promote

Notes worth keeping beyond today — move to `inbox/` for classification.

- [ ]
"""

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def resolve_whisper_python() -> str:
    """Resolve transcription interpreter, preferring a stable Python 3.11 venv."""
    # Explicit override wins.
    override = os.environ.get("VOICE_WHISPER_PYTHON", "").strip()
    if override and Path(override).exists():
        return override

    # Prefer 3.11 whisper venv when available to avoid known 3.12+ MLX crashes.
    if Path(WHISPER311_PYTHON).exists():
        return WHISPER311_PYTHON

    return WHISPER_PYTHON


def get_python_minor(python_bin: str) -> str:
    """Return '<major>.<minor>' for interpreter, or empty string on failure."""
    proc = subprocess.run(
        [python_bin, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def python_has_module(python_bin: str, module: str) -> bool:
    """Check whether a python interpreter can import a module (without using it)."""
    if not Path(python_bin).exists():
        return False
    proc = subprocess.run(
        [python_bin, "-c", f"import importlib.util; raise SystemExit(0 if importlib.util.find_spec('{module}') else 1)"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode == 0


def get_today() -> tuple[str, str]:
    """Return (YYYY-MM-DD, weekday abbreviation)."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d"), WEEKDAYS[now.weekday()]


def ensure_daily_note(date: str, weekday: str) -> Path:
    """Create today's daily note from template if it doesn't exist."""
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    path = DAILY_DIR / f"{date}.md"
    if not path.exists():
        path.write_text(DAILY_TEMPLATE.format(date=date, weekday=weekday))
        print(f"Created daily note: {path}")
    return path


def ensure_voice_section(path: Path) -> None:
    """Add a Voice Notes section if the daily note doesn't have one."""
    content = path.read_text()
    if "## Voice Notes" not in content:
        # Insert before Agent Daily or at the end
        if "## Agent Daily" in content:
            content = content.replace(
                "## Agent Daily",
                "## Voice Notes\n\n> Transcribed voice memos from today.\n\n## Agent Daily",
            )
        else:
            content += "\n## Voice Notes\n\n> Transcribed voice memos from today.\n"
        path.write_text(content)


def record_audio(output_path: str, duration: int | None = None) -> bool:
    """Record audio from the default microphone using ffmpeg.

    Returns True if recording succeeded, False otherwise.
    """
    cmd = [
        "ffmpeg", "-y",
        "-f", "avfoundation",
        "-i", ":0",          # default audio input device
        "-ac", "1",           # mono
        "-ar", "16000",       # 16kHz (whisper native sample rate)
        "-acodec", "pcm_s16le",
        output_path,
    ]
    if duration:
        cmd.insert(-1, "-t")
        cmd.insert(-1, str(duration))

    print(f"Recording... {'Press Ctrl+C to stop.' if not duration else f'Max {duration}s.'}")
    print("Speak now.\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    # Forward SIGINT to ffmpeg so it flushes cleanly
    original_sigint = signal.getsignal(signal.SIGINT)

    def handle_sigint(signum, frame):
        proc.send_signal(signal.SIGINT)

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        _, stderr = proc.communicate()
    finally:
        signal.signal(signal.SIGINT, original_sigint)

    # ffmpeg returns 255 on SIGINT but the file is valid
    if proc.returncode not in (0, 255):
        print(f"Recording failed: {stderr.decode()[-500:]}", file=sys.stderr)
        return False

    # Check file has content
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        print("Recording too short or empty.", file=sys.stderr)
        return False

    size_kb = os.path.getsize(output_path) / 1024
    print(f"Recorded {size_kb:.0f} KB audio.\n")
    return True


def transcribe_with_mlx(audio_path: str, model: str = DEFAULT_WHISPER_MODEL) -> str:
    """Transcribe audio using mlx-whisper."""
    whisper_python = resolve_whisper_python()
    py_minor = get_python_minor(whisper_python)

    # Guardrail: Python 3.12 + MLX can crash on some macOS/Metal setups.
    if py_minor == "3.12" and os.environ.get("VOICE_ALLOW_UNSTABLE_MLX", "") != "1":
        raise RuntimeError(
            "Refusing unstable mlx_whisper runtime on Python 3.12.\n"
            "Set VOICE_ALLOW_UNSTABLE_MLX=1 to force, or install/use non-MLX fallback backend."
        )

    if not python_has_module(whisper_python, "mlx_whisper"):
        raise RuntimeError(
            f"mlx_whisper is not installed in interpreter: {whisper_python}"
        )

    print(f"Transcribing with {model}...")

    # Use the whisper venv's python to import and run mlx_whisper
    # mlx_whisper prints "Detected language: ..." to stdout, so we use a
    # unique marker to delimit our JSON output from its noise.
    marker = "__VOICE_RESULT__"
    script = f"""
import mlx_whisper, json, sys
result = mlx_whisper.transcribe(
    "{audio_path}",
    path_or_hf_repo="{model}",
    verbose=False,
)
text = result.get("text", "").strip()
print("{marker}")
print(json.dumps({{"text": text}}))
"""
    proc = subprocess.run(
        [whisper_python, "-c", script],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"mlx_whisper failed (exit {proc.returncode}): {proc.stderr[-400:]}")

    stdout = proc.stdout
    if marker not in stdout:
        raise RuntimeError(
            f"mlx_whisper returned no result marker. stdout={stdout[-300:]} stderr={proc.stderr[-300:]}"
        )

    import json
    json_str = stdout.split(marker, 1)[1].strip()
    result = json.loads(json_str)
    text = result["text"]
    words = len(text.split())
    print(f"Transcribed {words} words.\n")
    return text


def transcribe_with_faster_whisper(audio_path: str, model: str = DEFAULT_CPU_MODEL) -> str:
    """Transcribe audio using faster-whisper on CPU."""
    python_bin = os.environ.get("VOICE_FASTER_WHISPER_PYTHON", WHISPER_CPU_PYTHON).strip() or WHISPER_CPU_PYTHON
    if not Path(python_bin).exists():
        raise RuntimeError(
            f"CPU fallback python not found: {python_bin}. Install faster-whisper in ~/.venvs/whisper-cpu."
        )
    if not python_has_module(python_bin, "faster_whisper"):
        raise RuntimeError(
            f"faster_whisper module not found in: {python_bin}"
        )

    print(f"Transcribing with faster-whisper ({model}, cpu/int8)...")
    marker = "__VOICE_RESULT__"
    script = f"""
import json
from faster_whisper import WhisperModel

model = WhisperModel("{model}", device="cpu", compute_type="int8")
segments, info = model.transcribe("{audio_path}", beam_size=1, vad_filter=True)
text = " ".join(s.text.strip() for s in segments).strip()
print("{marker}")
print(json.dumps({{"text": text, "language": getattr(info, "language", None)}}))
"""
    proc = subprocess.run(
        [python_bin, "-c", script],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"faster-whisper failed (exit {proc.returncode}): {proc.stderr[-500:]}")
    if marker not in proc.stdout:
        raise RuntimeError(
            f"faster-whisper returned no result marker. stdout={proc.stdout[-300:]} stderr={proc.stderr[-300:]}"
        )

    import json
    result = json.loads(proc.stdout.split(marker, 1)[1].strip())
    text = result.get("text", "").strip()
    words = len(text.split())
    print(f"Transcribed {words} words.\n")
    return text


def transcribe(audio_path: str, model: str = DEFAULT_WHISPER_MODEL, backend: str = "auto") -> str:
    """Transcribe audio using configured backend with safe fallback."""
    backend = backend.strip().lower()
    if backend not in {"auto", "mlx", "faster-whisper"}:
        print(f"Invalid backend: {backend}. Use auto|mlx|faster-whisper.", file=sys.stderr)
        sys.exit(2)

    errors: list[str] = []

    if backend in {"auto", "mlx"}:
        if os.environ.get("VOICE_ENABLE_MLX", "") == "1":
            try:
                return transcribe_with_mlx(audio_path, model)
            except Exception as exc:
                errors.append(f"mlx backend failed: {exc}")
                if backend == "mlx":
                    print("\n".join(errors), file=sys.stderr)
                    sys.exit(1)
        else:
            msg = "mlx backend disabled (set VOICE_ENABLE_MLX=1 to enable)"
            if backend == "mlx":
                print(msg, file=sys.stderr)
                sys.exit(2)
            errors.append(msg)

    if backend in {"auto", "faster-whisper"}:
        try:
            return transcribe_with_faster_whisper(audio_path, DEFAULT_CPU_MODEL)
        except Exception as exc:
            errors.append(f"faster-whisper backend failed: {exc}")

    print("Transcription unavailable:\n- " + "\n- ".join(errors), file=sys.stderr)
    sys.exit(1)


def append_to_daily(daily_path: Path, transcript: str, audio_path: str | None = None) -> None:
    """Append a timestamped voice entry to the daily note's Voice Notes section."""
    now = datetime.now()
    timestamp = now.strftime("%H:%M")

    entry = f"\n### {timestamp}\n\n{transcript}\n"

    if audio_path:
        entry += f"\n_Audio: `{audio_path}`_\n"

    content = daily_path.read_text()

    # Find the Voice Notes section and append after the blockquote
    if "## Voice Notes" in content:
        # Find the next ## heading after Voice Notes
        parts = content.split("## Voice Notes", 1)
        after_voice = parts[1]

        # Find the next section
        next_section_idx = after_voice.find("\n## ", 1)
        if next_section_idx > 0:
            # Insert before next section
            before_next = after_voice[:next_section_idx]
            rest = after_voice[next_section_idx:]
            content = parts[0] + "## Voice Notes" + before_next + entry + rest
        else:
            # Voice Notes is the last section
            content = parts[0] + "## Voice Notes" + after_voice + entry
    else:
        content += f"\n## Voice Notes\n{entry}"

    daily_path.write_text(content)
    print(f"Appended to {daily_path}")


def archive_audio(audio_path: str, date: str) -> str | None:
    """Copy audio to archive directory. Returns archive path."""
    AUDIO_ARCHIVE.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    dest = AUDIO_ARCHIVE / f"{date}-{timestamp}.wav"
    import shutil
    shutil.copy2(audio_path, dest)
    return str(dest)


def main():
    parser = argparse.ArgumentParser(description="Voice → daily note pipeline")
    parser.add_argument("--duration", "-d", type=int, help="Max recording duration in seconds")
    parser.add_argument("--file", "-f", help="Transcribe existing audio file instead of recording")
    parser.add_argument("--dry-run", action="store_true", help="Transcribe but don't write to daily note")
    parser.add_argument("--whisper-model", default=DEFAULT_WHISPER_MODEL, help="mlx-whisper model (used when backend=mlx)")
    parser.add_argument("--backend", default=os.environ.get("VOICE_TRANSCRIBE_BACKEND", "auto"), choices=["auto", "mlx", "faster-whisper"], help="Transcription backend")
    parser.add_argument("--keep-audio", action="store_true", help="Archive the audio file")
    args = parser.parse_args()

    date, weekday = get_today()
    daily_path = ensure_daily_note(date, weekday)
    ensure_voice_section(daily_path)

    if args.file:
        audio_path = args.file
        if not os.path.exists(audio_path):
            print(f"File not found: {audio_path}", file=sys.stderr)
            sys.exit(1)
    else:
        # Record from microphone
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        audio_path = tmp.name

        if not record_audio(audio_path, args.duration):
            os.unlink(audio_path)
            sys.exit(1)

    # Transcribe
    transcript = transcribe(audio_path, args.whisper_model, args.backend)

    if not transcript.strip():
        print("Empty transcript — nothing to add.")
        sys.exit(0)

    print(f"--- Transcript ---\n{transcript}\n------------------\n")

    if args.dry_run:
        print("[dry-run] Would append to:", daily_path)
        return

    # Archive audio if requested
    archive_path = None
    if args.keep_audio:
        archive_path = archive_audio(audio_path, date)
        print(f"Audio archived: {archive_path}")

    # Append to daily note
    append_to_daily(daily_path, transcript, archive_path)

    # Cleanup temp file
    if not args.file and not args.keep_audio:
        os.unlink(audio_path)

    print("Done.")


if __name__ == "__main__":
    main()
