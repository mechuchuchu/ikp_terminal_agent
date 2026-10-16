"""Run model-requested shell commands in a disposable Docker container."""

import os
import shutil
import subprocess
import uuid
from pathlib import Path


IMAGE = "ikp-terminal-agent:latest"


class DockerTerminal:
    def __init__(self, workspace: Path, timeout_seconds: int = 30):
        self.engine = os.environ.get("CONTAINER_ENGINE", "docker")
        self.workspace = workspace.resolve()
        self.timeout_seconds = timeout_seconds
        self.name = f"ikp-agent-{uuid.uuid4().hex[:12]}"
        self.started = False

    def _run_engine(self, args, timeout=60):
        return subprocess.run(
            [self.engine, *args],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def start(self):
        if not shutil.which(self.engine):
            raise RuntimeError(
                f"Container engine '{self.engine}' not found. Install Docker or set "
                "CONTAINER_ENGINE to a compatible executable such as podman."
            )
        self.workspace.mkdir(parents=True, exist_ok=True)
        # The container uses UID 10001. This task-only directory is its sole writable mount.
        self.workspace.chmod(0o777)
        result = self._run_engine(
            [
                "run", "--detach", "--rm", "--name", self.name,
                "--network", "bridge",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=64",
                "--memory=512m",
                "--cpus=1",
                "--read-only",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
                "--mount", f"type=bind,src={self.workspace},dst=/work",
                "--workdir", "/work",
                IMAGE,
            ]
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Could not start Docker container: {detail}")
        self.started = True

    def run(self, command: str) -> dict:
        if not self.started:
            raise RuntimeError("Docker terminal is not running")

        try:
            result = self._run_engine(
                [
                    "exec", self.name,
                    "/usr/bin/timeout", "--signal=TERM", "--kill-after=2s",
                    f"{self.timeout_seconds}s", "/bin/sh", "-lc", command,
                ],
                timeout=self.timeout_seconds + 8,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            timed_out = result.returncode == 124
            status = result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            timed_out = True
            status = 124

        combined = stdout
        if stderr:
            combined += ("\n" if combined else "") + stderr
        limit = 16000
        clipped = len(combined) > limit
        if clipped:
            combined = combined[:limit] + "\n[output clipped]"
        return {
            "exit_code": status,
            "timed_out": timed_out,
            "output": combined,
            "output_clipped": clipped,
        }

    def stop(self):
        if self.started:
            self._run_engine(["rm", "--force", self.name], timeout=30)
            self.started = False

