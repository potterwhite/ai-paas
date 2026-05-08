#!/usr/bin/env python3
"""
Wiki Batch Ingest Tool — scheduled batch processing with time-window support.

Usage:
    python3 scripts/wiki_batch.py run --vault-path /path [--window HH:MM-HH:MM ...]
    python3 scripts/wiki_batch.py status --vault-path /path
    python3 scripts/wiki_batch.py reset --vault-path /path
"""

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

TZ = timezone(timedelta(hours=8))
RAG_BASE_URL = "http://localhost:8081"
RAG_API_KEY = "sk-rag-default"
STATE_FILE = "batch_state.json"


def _set_rag_url(url: str):
    global RAG_BASE_URL
    RAG_BASE_URL = url

# Directories to exclude from scanning
EXCLUDE_DIRS = {"_wiki", "_schema", ".obsidian", ".trash", "atta"}


def _now() -> datetime:
    return datetime.now(TZ)


def _today_str() -> str:
    return _now().strftime("%Y-%m-%d")


def _state_path(vault_path: Path) -> Path:
    return vault_path / "_wiki" / STATE_FILE


def _load_state(vault_path: Path) -> dict:
    p = _state_path(vault_path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state(vault_path: Path, state: dict) -> None:
    p = _state_path(vault_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _scan_vault(vault_path: Path) -> list[str]:
    """Scan vault for all .md files, excluding special dirs."""
    results = []
    for md_file in vault_path.rglob("*.md"):
        rel = md_file.relative_to(vault_path)
        parts = rel.parts
        if any(part in EXCLUDE_DIRS for part in parts):
            continue
        results.append(str(rel))
    results.sort()
    return results


def _parse_window(window_str: str) -> tuple[int, int]:
    """Parse 'HH:MM-HH:MM' into (start_minutes, end_minutes)."""
    parts = window_str.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid window format: {window_str}. Expected HH:MM-HH:MM")
    sh, sm = parts[0].split(":")
    eh, em = parts[1].split(":")
    return int(sh) * 60 + int(sm), int(eh) * 60 + int(em)


def _is_in_window(windows: list[tuple[int, int]]) -> bool:
    """Check if current time is within any of the time windows."""
    if not windows:
        return True  # No windows = always run
    now = _now()
    current_min = now.hour * 60 + now.minute
    for start, end in windows:
        if start <= end:
            # Same day window (e.g., 02:00-06:00)
            if start <= current_min < end:
                return True
        else:
            # Overnight window (e.g., 22:00-06:00)
            if current_min >= start or current_min < end:
                return True
    return False


def _seconds_until_next_window(windows: list[tuple[int, int]]) -> int:
    """Calculate seconds until the next time window opens."""
    if not windows:
        return 0
    now = _now()
    current_min = now.hour * 60 + now.minute
    min_wait = 24 * 60  # 24 hours in minutes

    for start, end in windows:
        if start > current_min:
            wait = start - current_min
        else:
            # Window starts tomorrow
            wait = (24 * 60 - current_min) + start
        min_wait = min(min_wait, wait)

    return min_wait * 60


def _ingest_one(source_path: str) -> dict:
    """Call RAG ingest API for a single document."""
    url = f"{RAG_BASE_URL}/v1/wiki/ingest"
    data = json.dumps({"source_path": source_path}).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {RAG_API_KEY}")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError) as e:
        return {"error": str(e)}


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_status(args):
    """Show batch ingest progress."""
    vault_path = Path(args.vault_path).resolve()
    state = _load_state(vault_path)

    if not state:
        print("No batch state found. Run 'wiki-batch run' first.")
        return

    total = state.get("total", 0)
    processed = state.get("processed", 0)
    succeeded = state.get("succeeded", 0)
    failed = state.get("failed", 0)
    remaining = total - processed
    pct = (processed / total * 100) if total > 0 else 0

    print(f"Wiki Batch Ingest Progress")
    print(f"{'=' * 40}")
    print(f"  Total:      {total}")
    print(f"  Processed:  {processed} ({pct:.1f}%)")
    print(f"  Succeeded:  {succeeded}")
    print(f"  Failed:     {failed}")
    print(f"  Remaining:  {remaining}")
    print(f"  Last run:   {state.get('last_run', 'N/A')}")

    if state.get("failed_docs"):
        print(f"\nFailed documents:")
        for fd in state["failed_docs"][:10]:
            print(f"  ✗ {fd['path']}: {fd.get('error', 'unknown')[:60]}")
        if len(state["failed_docs"]) > 10:
            print(f"  ... and {len(state['failed_docs']) - 10} more")


def cmd_reset(args):
    """Reset batch state."""
    vault_path = Path(args.vault_path).resolve()
    p = _state_path(vault_path)
    if p.exists():
        p.unlink()
        print(f"Batch state reset: {p}")
    else:
        print("No batch state to reset.")


def cmd_run(args):
    """Run batch ingest with optional time-window scheduling."""
    vault_path = Path(args.vault_path).resolve()

    if not vault_path.exists():
        print(f"Error: vault path does not exist: {vault_path}")
        sys.exit(1)

    # Parse time windows
    windows = []
    for w in args.window:
        windows.append(_parse_window(w))

    # Restore read-only mode on exit if requested (for background mode)
    if args.restore_read_only:
        import atexit
        def _restore_ro():
            try:
                url = f"{RAG_BASE_URL}/v1/wiki/config"
                data = json.dumps({"read_only": True}).encode("utf-8")
                req = Request(url, data=data, method="POST")
                req.add_header("Authorization", f"Bearer {RAG_API_KEY}")
                req.add_header("Content-Type", "application/json")
                urlopen(req, timeout=10)
                print("[*] Restored wiki read-only mode.")
            except Exception:
                pass
        atexit.register(_restore_ro)

    # Load or create state
    state = _load_state(vault_path)
    completed = set(state.get("completed", []))
    failed_docs = state.get("failed_docs", [])

    # Scan vault
    all_docs = _scan_vault(vault_path)
    remaining = [d for d in all_docs if d not in completed]

    if not remaining:
        print(f"All {len(all_docs)} documents already processed.")
        return

    # Initialize state
    state["total"] = len(all_docs)
    state["processed"] = len(completed)
    state["succeeded"] = len(completed)
    state["failed"] = len(failed_docs)
    state["completed"] = list(completed)
    state["failed_docs"] = failed_docs

    print(f"Wiki Batch Ingest")
    print(f"  Vault:     {vault_path}")
    print(f"  Total:     {len(all_docs)}")
    print(f"  Remaining: {len(remaining)}")
    if windows:
        print(f"  Windows:   {', '.join(args.window)}")
    else:
        print(f"  Windows:   none (running continuously)")
    print()

    # Handle graceful shutdown
    stop = False

    def _signal_handler(sig, frame):
        nonlocal stop
        stop = True
        print("\n[!] Stopping after current document completes...")

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Process loop
    for i, doc_path in enumerate(remaining):
        if stop:
            print("[!] Interrupted. Progress saved.")
            break

        # Check time window
        if windows and not _is_in_window(windows):
            wait_sec = _seconds_until_next_window(windows)
            wait_min = wait_sec // 60
            print(f"[~] Outside time window. Waiting {wait_min} minutes...")
            # Sleep in small chunks so we can respond to signals
            end_time = time.time() + wait_sec
            while time.time() < end_time and not stop:
                time.sleep(min(30, end_time - time.time()))
            if stop:
                break

        # Ingest
        progress = f"[{i + 1}/{len(remaining)}]"
        print(f"{progress} Ingesting: {doc_path} ... ", end="", flush=True)

        result = _ingest_one(doc_path)

        if "error" in result:
            print(f"FAILED: {result['error'][:60]}")
            failed_docs.append({"path": doc_path, "error": result["error"]})
            state["failed"] = len(failed_docs)
            state["failed_docs"] = failed_docs
        else:
            pages = result.get("pages_written", [])
            print(f"OK ({len(pages)} pages)")
            completed.add(doc_path)
            state["succeeded"] = len(completed)

        state["processed"] = len(completed) + len(failed_docs)
        state["completed"] = list(completed)
        state["last_run"] = _now().isoformat()
        _save_state(vault_path, state)

    # Final summary
    print(f"\n{'=' * 40}")
    print(f"Done. Processed: {state['processed']}/{state['total']}")
    print(f"  Succeeded: {state['succeeded']}")
    print(f"  Failed:    {state['failed']}")
    _save_state(vault_path, state)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Wiki Batch Ingest Tool — scheduled batch processing"
    )
    parser.add_argument("command", choices=["run", "status", "reset"],
                        help="Command to execute")
    parser.add_argument("--vault-path", required=True,
                        help="Path to the Obsidian vault")
    parser.add_argument("--window", action="append", default=[],
                        help="Time window HH:MM-HH:MM (can specify multiple)")
    parser.add_argument("--rag-url", default=RAG_BASE_URL,
                        help=f"RAG service URL (default: {RAG_BASE_URL})")
    parser.add_argument("--restore-read-only", action="store_true",
                        help="Restore WIKI_READ_ONLY=true on exit (for background mode)")

    args = parser.parse_args()

    # Override RAG URL if specified
    if args.rag_url != RAG_BASE_URL:
        _set_rag_url(args.rag_url)

    if args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "reset":
        cmd_reset(args)


if __name__ == "__main__":
    main()
