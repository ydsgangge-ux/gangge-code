"""Shadow Git — automatic checkpoint & rollback for AI file modifications.

Before each AI task execution, creates a git checkpoint.
If the AI produces broken code, user can one-click rollback.

Usage:
    from gangge.layer4_tools.shadow_git import ShadowGit

    sg = ShadowGit(workspace="/path/to/project")
    sg.checkpoint("before: implement login feature")
    # ... AI modifies files ...
    sg.checkpoint("after: login feature done")
    # List checkpoints
    checkpoints = sg.list_checkpoints()
    # Rollback to a checkpoint
    sg.rollback("before: implement login feature")
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CHECKPOINT_PREFIX = "gangge-checkpoint"


class ShadowGit:
    """Manages automatic git checkpoints for AI-driven file modifications."""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self._git_dir = Path(workspace) / ".git"
        self._initialized = False

    def is_available(self) -> bool:
        return self._git_dir.exists()

    def ensure_init(self) -> bool:
        if self.is_available():
            self._initialized = True
            return True
        try:
            self._run(["git", "init"], check=True)
            self._run(["git", "config", "user.email", "gangge@ai"], check=True)
            self._run(["git", "config", "user.name", "Gangge Code"], check=True)
            self._gitignore_essentials()
            self._run(["git", "add", "-A"], check=True)
            self._run(["git", "commit", "-m", "gangge: initial checkpoint", "--allow-empty"], check=True)
            self._initialized = True
            return True
        except Exception as e:
            logger.warning(f"ShadowGit init failed: {e}")
            return False

    def _gitignore_essentials(self):
        gi_path = Path(self.workspace) / ".gitignore"
        lines = set()
        if gi_path.exists():
            lines = set(gi_path.read_text(encoding="utf-8", errors="replace").splitlines())
        essentials = {
            "__pycache__/", "*.pyc", ".env", "node_modules/",
            ".venv/", "venv/", "dist/", "build/", ".idea/", ".vscode/",
        }
        additions = essentials - lines
        if additions:
            with open(gi_path, "a", encoding="utf-8") as f:
                if lines and not any(l.strip() == "" for l in lines):
                    f.write("\n")
                for line in sorted(additions):
                    f.write(line + "\n")

    def checkpoint(self, label: str = "") -> str | None:
        if not self.is_available() and not self.ensure_init():
            return None
        try:
            self._run(["git", "add", "-A"])
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            short_label = label[:60].replace("\n", " ") if label else "auto"
            msg = f"{CHECKPOINT_PREFIX}: {ts} {short_label}"
            result = self._run(["git", "commit", "-m", msg, "--allow-empty"])
            if result.returncode == 0:
                hash_result = self._run(["git", "rev-parse", "--short", "HEAD"])
                short_hash = hash_result.stdout.strip()
                logger.info(f"Checkpoint created: {short_hash} {msg}")
                return short_hash
            return None
        except Exception as e:
            logger.warning(f"Checkpoint failed: {e}")
            return None

    def list_checkpoints(self, limit: int = 20) -> list[dict[str, str]]:
        if not self.is_available():
            return []
        try:
            result = self._run(
                ["git", "log", f"--max-count={limit}", "--pretty=format:%h|%ai|%s"],
            )
            checkpoints = []
            for line in result.stdout.strip().splitlines():
                if "|" not in line:
                    continue
                parts = line.split("|", 2)
                if len(parts) < 3:
                    continue
                short_hash, date, msg = parts
                is_ours = msg.startswith(CHECKPOINT_PREFIX) or msg.startswith("gangge:")
                checkpoints.append({
                    "hash": short_hash,
                    "date": date,
                    "message": msg,
                    "is_checkpoint": is_ours,
                })
            return checkpoints
        except Exception:
            return []

    def rollback(self, ref: str = "HEAD~1") -> bool:
        if not self.is_available():
            return False
        try:
            if ref in ("HEAD~1", "HEAD~2", "HEAD~3"):
                pass
            elif len(ref) >= 7:
                pass
            else:
                ref = f"HEAD~{ref}"
            self._run(["git", "reset", "--hard", ref], check=True)
            self._run(["git", "clean", "-fd"], check=False)
            logger.info(f"Rolled back to {ref}")
            return True
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    def diff_since(self, ref: str = "HEAD~1") -> str:
        if not self.is_available():
            return ""
        try:
            result = self._run(["git", "diff", ref])
            return result.stdout
        except Exception:
            return ""

    def status(self) -> dict[str, Any]:
        if not self.is_available():
            return {"available": False}
        try:
            branch_result = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
            branch = branch_result.stdout.strip()
            status_result = self._run(["git", "status", "--short"])
            changed = [l for l in status_result.stdout.strip().splitlines() if l.strip()]
            return {
                "available": True,
                "branch": branch,
                "changed_files": len(changed),
                "changed_details": changed[:20],
            }
        except Exception:
            return {"available": False}

    def _run(self, cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            cwd=self.workspace,
            capture_output=True,
            text=True,
            timeout=30,
            check=check,
        )
