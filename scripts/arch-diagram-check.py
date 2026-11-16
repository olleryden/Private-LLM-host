#!/usr/bin/env python3
"""Claude Code hook: keep the README architecture diagram current at commit time.

Modes (argv[1]):
  prompt  UserPromptSubmit hook. When the prompt mentions a commit, inject the
          list of architecture-relevant changes and the refresh procedure.
  commit  PreToolUse hook for `git commit`. If architecture-relevant files
          changed but the exported diagram did not, ask the user before the
          commit proceeds (never a hard block).
  status  Print the drift report for humans.

Baseline: the last commit that changed the exported SVG; before the SVG is
first committed, the revision pinned in the newest diagram candidate.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[1])
SVG = ".archify/pllm-architecture.svg"
WATCH = (
    "scripts/", "control/", "ARCHITECTURE.md", "KONG.md", "CONTROL.md",
    "PHONE_CHAT.md", "PHONE_CONTROL.md", "pLLM Control.desktop",
)
IGNORE = {"scripts/arch-diagram-check.py", "scripts/export-diagram-svg.mjs"}
COMMIT_WORDS = re.compile(r"\bcommit", re.IGNORECASE)

PROCEDURE = (
    "Architecture-diagram procedure (owner request, INSTRUCTIONS.md): before proposing or "
    "making this commit, decide whether these changes alter the system architecture "
    "(services, ports, request paths, trust boundaries, lifecycle). If they do:\n"
    "1. Copy the newest .archify/architecture-pllm-*/candidate.json into a new "
    ".archify/architecture-pllm-<YYYYMMDD-HHMMSS>/ folder, update components, connections, "
    "cards and sources, and pin meta.repository.revision to `git rev-parse HEAD` "
    "(cite only files committed at HEAD; if a new component exists only in uncommitted "
    "files, commit the code first and refresh the diagram in a follow-up commit).\n"
    "2. Run the archify skill's finalize with --repo-root and --quality showcase.\n"
    "3. node scripts/export-diagram-svg.mjs <new html> .archify/pllm-architecture.svg svg\n"
    "4. Update README.md \"Architecture\": date, interactive-HTML link, one-line service table.\n"
    "If the changes are not architectural, say so briefly and continue."
)


def git(*args: str) -> tuple[int, str]:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return result.returncode, result.stdout


def baseline() -> str | None:
    code, out = git("log", "-1", "--format=%H", "--", SVG)
    if code == 0 and out.strip():
        return out.strip()
    candidates = sorted(ROOT.glob(".archify/architecture-pllm-*/candidate.json"))
    for candidate in reversed(candidates):
        try:
            return json.loads(candidate.read_text())["meta"]["repository"]["revision"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def report() -> tuple[str | None, list[str], bool]:
    base = baseline()
    changed: set[str] = set()
    if base:
        code, out = git("diff", "--name-only", base)
        if code != 0:
            base = None
        changed |= set(out.splitlines())
    changed |= set(git("ls-files", "--others", "--exclude-standard")[1].splitlines())
    changed.discard("")
    arch = sorted(p for p in changed if p.startswith(WATCH) and p not in IGNORE)
    return base, arch, SVG in changed


def describe(base: str | None, arch: list[str], svg_updated: bool) -> str:
    since = f"since {base[:7]}" if base else "(no diagram baseline found)"
    if not arch and base:
        return f"Architecture diagram check: no architecture-relevant changes {since}; README diagram is current."
    files = "\n".join(f"- {p}" for p in arch) or "- (unknown: baseline missing)"
    state = "The exported SVG has already been updated in this working tree." if svg_updated else \
        "The exported SVG has NOT been updated."
    return f"Architecture diagram check: architecture-relevant changes {since}:\n{files}\n{state}\n\n{PROCEDURE}"


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        payload = json.load(sys.stdin) if mode != "status" else {}
    except ValueError:
        payload = {}
    if mode == "prompt" and not COMMIT_WORDS.search(str(payload.get("prompt", ""))):
        return 0
    base, arch, svg_updated = report()
    text = describe(base, arch, svg_updated)
    if mode == "prompt":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))
    elif mode == "commit":
        if (arch or not base) and not svg_updated:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "Architecture-relevant files changed but the README diagram was not refreshed. "
                    "Commit anyway? (Run the diagram procedure first if the architecture changed.)\n" + text,
            }}))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
