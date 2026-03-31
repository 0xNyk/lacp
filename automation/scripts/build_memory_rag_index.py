#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_rag_lib import (
    Chunk,
    build_sparse_vectors,
    chunk_text,
    collect_markdown_files,
    ollama_embed,
    ollama_models,
    ollama_version,
)


KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
INDEX_DIR = KNOWLEDGE_ROOT / "data" / "rag"
INDEX_FILE = INDEX_DIR / "hybrid-index.json"


def build_chunks(max_chars: int, overlap_chars: int) -> tuple[list[Path], list[Chunk]]:
    files = collect_markdown_files(KNOWLEDGE_ROOT)
    chunks: list[Chunk] = []
    for file_path in files:
        text = file_path.read_text(errors="ignore")
        chunks.extend(chunk_text(file_path, text, max_chars=max_chars, overlap_chars=overlap_chars))
    return files, chunks


def attach_dense_vectors(
    payload_chunks: list[dict[str, Any]],
    model: str,
    host: str,
    timeout_s: float,
    batch_size: int,
) -> None:
    texts = [chunk["text"] for chunk in payload_chunks]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(ollama_embed(batch, host=host, model=model, timeout_s=timeout_s))
    if len(vectors) != len(payload_chunks):
        raise ValueError(f"Embedding count mismatch: expected {len(payload_chunks)} got {len(vectors)}")
    for chunk, vec in zip(payload_chunks, vectors):
        chunk["dense_vector"] = vec


def build_index(
    backend: str,
    max_chars: int,
    overlap_chars: int,
    max_terms_per_chunk: int,
    ollama_host: str,
    ollama_model: str,
    ollama_timeout_s: float,
    batch_size: int,
    allow_sparse_fallback: bool,
) -> dict[str, Any]:
    files, chunks = build_chunks(max_chars=max_chars, overlap_chars=overlap_chars)
    idf, sparse_vectors = build_sparse_vectors(chunks, max_terms_per_chunk=max_terms_per_chunk)

    payload_chunks: list[dict[str, Any]] = []
    for chunk, sparse_vec in zip(chunks, sparse_vectors):
        payload_chunks.append(
            {
                "id": chunk.chunk_id,
                "path": str(Path(chunk.path).relative_to(Path.home())),
                "heading": chunk.heading,
                "text": chunk.text,
                "sparse_vector": sparse_vec,
            }
        )

    use_dense = backend in ("ollama", "hybrid")
    dense_enabled = False
    dense_error = ""
    version = ollama_version(ollama_host, timeout_s=min(ollama_timeout_s, 6.0))
    models = ollama_models(ollama_host, timeout_s=min(ollama_timeout_s, 6.0))

    if use_dense:
        try:
            attach_dense_vectors(
                payload_chunks,
                model=ollama_model,
                host=ollama_host,
                timeout_s=ollama_timeout_s,
                batch_size=batch_size,
            )
            dense_enabled = True
        except Exception as exc:
            dense_error = str(exc)
            if not allow_sparse_fallback:
                raise
            if backend == "ollama":
                # Dense-only requested, but we fallback to sparse for continuity.
                backend = "sparse"

    return {
        "schema_version": 2,
        "built_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "knowledge_root": str(KNOWLEDGE_ROOT),
        "backend_mode": backend,
        "chunking": {"max_chars": max_chars, "overlap_chars": overlap_chars},
        "chunk_count": len(payload_chunks),
        "doc_count": len(files),
        "idf": idf,
        "chunks": payload_chunks,
        "ollama": {
            "host": ollama_host,
            "model": ollama_model,
            "version": version,
            "models": models,
            "dense_enabled": dense_enabled,
            "dense_error": dense_error,
        },
    }


def _self_test() -> None:
    files, chunks = build_chunks(max_chars=120, overlap_chars=20)
    assert isinstance(files, list)
    assert isinstance(chunks, list)
    idf, vectors = build_sparse_vectors(chunks[:3], max_terms_per_chunk=12) if chunks else ({}, [])
    assert isinstance(idf, dict)
    assert isinstance(vectors, list)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local hybrid RAG index for knowledge-memory.")
    parser.add_argument("--backend", choices=["sparse", "hybrid", "ollama"], default="hybrid")
    parser.add_argument("--max-chars", type=int, default=900, help="Max chunk size in characters.")
    parser.add_argument("--overlap-chars", type=int, default=120, help="Overlap between chunks.")
    parser.add_argument("--max-terms-per-chunk", type=int, default=80, help="Sparse top weighted terms per chunk.")
    parser.add_argument("--ollama-host", type=str, default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-model", type=str, default="nomic-embed-text:latest")
    parser.add_argument("--ollama-timeout", type=float, default=30.0)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--allow-sparse-fallback", action="store_true", default=True)
    parser.add_argument("--strict-dense", action="store_true", help="Fail if dense embedding step fails.")
    parser.add_argument("--output", type=str, default=str(INDEX_FILE))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    allow_sparse_fallback = args.allow_sparse_fallback and not args.strict_dense
    payload = build_index(
        backend=args.backend,
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
        max_terms_per_chunk=args.max_terms_per_chunk,
        ollama_host=args.ollama_host,
        ollama_model=args.ollama_model,
        ollama_timeout_s=args.ollama_timeout,
        batch_size=args.batch_size,
        allow_sparse_fallback=allow_sparse_fallback,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    print(
        json.dumps(
            {
                "index_file": str(output_path),
                "backend_mode": payload["backend_mode"],
                "chunk_count": payload["chunk_count"],
                "doc_count": payload["doc_count"],
                "dense_enabled": payload.get("ollama", {}).get("dense_enabled"),
                "ollama_model": payload.get("ollama", {}).get("model"),
                "ollama_version": payload.get("ollama", {}).get("version"),
                "dense_error": payload.get("ollama", {}).get("dense_error", ""),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
