"""Local Docker backend: the fallback while Sandboxes access is pending, and the dev loop.

Network is disabled and the container is discarded after each run. `image_ref` is a Docker
image tag (e.g. the breakwater-harness image with packaging refs preinstalled).
Resources come from getrusage(RUSAGE_CHILDREN) inside the container, after the command exits.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from breakwater.backends.base import Resources, RunResult

# Runs the command, then prints rusage of the children so the harness gets a second clock
# even without ConTree. The marker line is stripped from stdout.
_WRAP = (
    "import resource,subprocess,sys;"
    "p=subprocess.run(sys.argv[1:]);"
    "r=resource.getrusage(resource.RUSAGE_CHILDREN);"
    "print('__BW_RUSAGE__',r.ru_utime,r.ru_stime,r.ru_maxrss,r.ru_nivcsw,file=sys.stderr);"
    "sys.exit(p.returncode)"
)
_MARK = "__BW_RUSAGE__"


class DockerBackend:
    name = "docker"

    def run(self, image_ref, cmd, *, files=None, stdin=None, timeout_s=300, keep=False, tag=None) -> RunResult:
        with tempfile.TemporaryDirectory() as tmp:
            mounts: list[str] = []
            for rel, data in (files or {}).items():
                p = Path(tmp) / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            if files:
                mounts = ["-v", f"{tmp}:/inputs:ro"]
            docker = ["docker", "run", "--rm", "-i", "--network=none", *mounts, image_ref,
                      "python", "-c", _WRAP, *cmd]
            t0 = time.perf_counter()
            proc = subprocess.run(docker, input=stdin, capture_output=True, text=True, timeout=timeout_s)
            duration_ms = int((time.perf_counter() - t0) * 1000)

        resources = Resources()
        stderr_lines = []
        for line in proc.stderr.splitlines():
            if line.startswith(_MARK):
                u, s, rss, ivcsw = line.split()[1:]
                resources = Resources(float(u), float(s), int(rss), int(ivcsw))
            else:
                stderr_lines.append(line)
        return RunResult(proc.stdout, "\n".join(stderr_lines), proc.returncode, duration_ms, self.name,
                         image_ref=None, resources=resources)
