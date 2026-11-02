#!/usr/bin/env python3
"""
Resource guard: spot runaway Docker/LLM processes and piling-up artefacts, and clean them.

    python3 scripts/resource_guard.py check            # read-only, exit 1 if anything needs attention
    python3 scripts/resource_guard.py clean            # dry run: show what would be removed or stopped
    python3 scripts/resource_guard.py clean --apply    # do it

What `check` looks at:
  host     free disk, swap, processes pinning the CPU, a busy Docker VM with idle containers
  docker   crash-looping / unhealthy / CPU- or memory-hungry containers, VM disk size,
           reclaimable images, build cache
  llm      host LLM tiers: stale pid files, llm_service processes nobody supervises
  models   size of every model cache, half-finished downloads, the same model stored twice

What `clean --apply` does (and never more):
  - prunes Docker build cache down to GUARD_BUILD_CACHE_KEEP_GB
  - removes dangling images, and unused images older than GUARD_IMAGE_MIN_AGE_DAYS that no
    container uses and the compose files (any profile) do not reference
  - disables restart on crash-looping containers and stops them (docker update --restart=no)
  - stops orphaned llm_service processes and removes stale pid files
  - deletes partial downloads (*.incomplete) older than a day
It never deletes model weights; it lists duplicates and the largest caches with the command
to remove them by hand. Docker's disk image shrinks on its own after pruning (Docker Desktop
reclaims freed blocks), which can take a few minutes.

Thresholds are environment variables; see THRESHOLDS below. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


THRESHOLDS = {
    "min_free_disk_gb": _env_float("GUARD_MIN_FREE_DISK_GB", 50),
    "max_swap_gb": _env_float("GUARD_MAX_SWAP_GB", 8),
    "host_cpu_pct": _env_float("GUARD_HOST_CPU_PCT", 150),           # sustained, per process
    "container_cpu_pct": _env_float("GUARD_CONTAINER_CPU_PCT", 80),  # sustained
    "container_mem_pct": _env_float("GUARD_CONTAINER_MEM_PCT", 80),  # of its limit
    "restart_loop_count": _env_float("GUARD_RESTART_LOOP_COUNT", 5),
    "docker_disk_gb": _env_float("GUARD_DOCKER_DISK_GB", 100),       # Docker.raw on disk
    "image_reclaimable_gb": _env_float("GUARD_IMAGE_RECLAIMABLE_GB", 20),
    "build_cache_gb": _env_float("GUARD_BUILD_CACHE_GB", 15),
    "build_cache_keep_gb": _env_float("GUARD_BUILD_CACHE_KEEP_GB", 10),
    "image_min_age_days": _env_float("GUARD_IMAGE_MIN_AGE_DAYS", 14),
    "model_cache_total_gb": _env_float("GUARD_MODEL_CACHE_GB", 100),
    "sample_seconds": _env_float("GUARD_SAMPLE_SECONDS", 5),
}

# Model caches to measure. GUARD_MODEL_DIRS (colon-separated) adds more.
MODEL_DIRS = [
    ROOT / "llm_service" / "models.nosync",
    ROOT.parent.parent / "ANE:GPU:CPU" / "cache.nosync",
    HOME / ".cache" / "huggingface",
    HOME / ".cache" / "llama.cpp",
    HOME / ".cache" / "lm-studio",
    HOME / ".lmstudio" / "models",
    HOME / ".ollama" / "models",
] + [Path(p) for p in os.environ.get("GUARD_MODEL_DIRS", "").split(":") if p]

DOCKER_RAW = HOME / "Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw"
DOCKER_VM_PROCS = ("com.apple.Virtualization.VirtualMachine", "com.docker.virtualization", "qemu-system")
LLM_RUN = ROOT / "logs" / "llm"

# ── output ────────────────────────────────────────────────────────────────────
TTY = sys.stdout.isatty()
def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if TTY else s
OK, WARN, BAD, DIM, BOLD = (lambda s: _c("32", s)), (lambda s: _c("33", s)), (lambda s: _c("31", s)), (lambda s: _c("2", s)), (lambda s: _c("1", s))


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def bad(self, msg: str) -> None:
        self.problems.append(msg)
        print(f"  {BAD('✗')} {msg}")

    def ok(self, msg: str) -> None:
        print(f"  {OK('✓')} {msg}")

    def info(self, msg: str) -> None:
        self.notes.append(msg)
        print(f"  {DIM('·')} {msg}")


# ── helpers (pure, unit-tested) ───────────────────────────────────────────────
_UNITS = {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
          "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}


def parse_size(text: str) -> float:
    """'48.04GB' / '32.29GB (67%)' / '1.025GiB' / '0B' -> bytes."""
    m = re.match(r"\s*([\d.]+)\s*([a-zA-Z]*)", text or "")
    if not m:
        return 0.0
    unit = (m.group(2) or "b").lower()
    return float(m.group(1)) * _UNITS.get(unit, 1)


def parse_pct(text: str) -> float:
    try:
        return float((text or "0").strip().rstrip("%"))
    except ValueError:
        return 0.0


def is_crash_looping(status: str, restart_count: int, uptime_s: float, limit: float) -> bool:
    """Restarting now, or restarted `limit`+ times and up for less than an hour."""
    return status == "restarting" or (restart_count >= limit and uptime_s < 3600)


def image_removal_candidates(images: list[dict], in_use: set[str], protected_repos: set[str],
                             min_age_days: float, now: datetime) -> list[dict]:
    """Unused images older than min_age_days whose repository compose does not reference."""
    out = []
    for img in images:
        repo = img["repo"]
        if img["id"] in in_use or repo in protected_repos:
            continue
        if repo == "<none>":
            out.append(img)  # dangling
            continue
        age_days = (now - img["created"]).total_seconds() / 86400
        if age_days >= min_age_days:
            out.append(img)
    return out


def gb(n: float) -> str:
    return f"{n / 1e9:.1f} GB"


# ── shell ─────────────────────────────────────────────────────────────────────
def run(cmd: list[str], timeout: float = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def docker_up() -> bool:
    return shutil.which("docker") is not None and run(["docker", "info", "--format", "{{.ID}}"], 15)[0] == 0


def json_lines(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def parse_docker_time(s: str) -> datetime:
    s = re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00"))
    s = re.sub(r" ([A-Z]{3,4})$", "", s)  # "2026-09-18 10:00:00 -0400 EDT"
    for fmt in (None, "%Y-%m-%d %H:%M:%S %z"):
        try:
            return datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


# ── checks ────────────────────────────────────────────────────────────────────
def ps_sample() -> dict[int, tuple[float, int, str]]:
    _, out = run(["ps", "-axo", "pid=,pcpu=,rss=,comm="])
    procs = {}
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            try:
                procs[int(parts[0])] = (float(parts[1]), int(parts[2]) * 1024, parts[3])
            except ValueError:
                pass
    return procs


def check_host(r: Report, docker_cpu_total: float | None) -> None:
    print(BOLD("Host"))
    du = shutil.disk_usage("/")
    if du.free / 1e9 < THRESHOLDS["min_free_disk_gb"]:
        r.bad(f"only {gb(du.free)} free on / (threshold {THRESHOLDS['min_free_disk_gb']:.0f} GB)")
    else:
        r.ok(f"{gb(du.free)} free on /")

    _, swap = run(["sysctl", "-n", "vm.swapusage"])
    m = re.search(r"used = ([\d.]+)M", swap)
    if m:
        used_gb = float(m.group(1)) / 1024
        (r.bad if used_gb > THRESHOLDS["max_swap_gb"] else r.ok)(
            f"swap used {used_gb:.1f} GB" + (" (memory pressure: something is too big)" if used_gb > THRESHOLDS["max_swap_gb"] else ""))

    a = ps_sample()
    time.sleep(THRESHOLDS["sample_seconds"])
    b = ps_sample()
    hot = []
    for pid, (cpu2, rss, comm) in b.items():
        cpu1 = a.get(pid, (0, 0, ""))[0]
        if min(cpu1, cpu2) >= THRESHOLDS["host_cpu_pct"]:
            hot.append((min(cpu1, cpu2), pid, rss, comm))
    vm_busy = False
    for cpu, pid, rss, comm in sorted(hot, reverse=True):
        name = os.path.basename(comm)
        is_vm = any(v in comm for v in DOCKER_VM_PROCS)
        if is_vm and docker_cpu_total is not None and docker_cpu_total < 30:
            vm_busy = True
            r.bad(f"Docker VM at {cpu:.0f}% CPU while containers use {docker_cpu_total:.0f}%: VM is stuck. "
                  f"Restart Docker Desktop")
        elif not is_vm:
            r.bad(f"pid {pid} {name} sustained {cpu:.0f}% CPU, {gb(rss)} RSS")
    if not hot:
        r.ok(f"no process above {THRESHOLDS['host_cpu_pct']:.0f}% CPU for {THRESHOLDS['sample_seconds']:.0f}s")
    elif not vm_busy and all(any(v in c for v in DOCKER_VM_PROCS) for *_, c in hot):
        r.ok("only the Docker VM is busy, and its containers account for it")


def check_docker(r: Report) -> float | None:
    print(BOLD("Docker"))
    if not docker_up():
        r.info("Docker is not running; skipped")
        return None

    if DOCKER_RAW.exists():
        on_disk = DOCKER_RAW.stat().st_blocks * 512
        (r.bad if on_disk / 1e9 > THRESHOLDS["docker_disk_gb"] else r.ok)(
            f"Docker disk image uses {gb(on_disk)} on disk")

    _, df = run(["docker", "system", "df", "--format", "{{json .}}"])
    for row in json_lines(df):
        kind, reclaim = row.get("Type"), parse_size(row.get("Reclaimable", "0"))
        size = parse_size(row.get("Size", "0"))
        if kind == "Images":
            (r.bad if reclaim / 1e9 > THRESHOLDS["image_reclaimable_gb"] else r.ok)(
                f"images {gb(size)}, {gb(reclaim)} reclaimable")
        elif kind == "Build Cache":
            (r.bad if size / 1e9 > THRESHOLDS["build_cache_gb"] else r.ok)(f"build cache {gb(size)}")
        elif kind == "Local Volumes" and reclaim > 5e9:
            r.bad(f"volumes: {gb(reclaim)} in unused volumes (docker volume prune)")

    # Crash loops and unhealthy containers
    _, ids = run(["docker", "ps", "-aq"])
    now = datetime.now(timezone.utc)
    if ids.split():
        _, raw = run(["docker", "inspect", *ids.split()])
        try:
            infos = json.loads(raw)
        except json.JSONDecodeError:
            infos = []
        loops = 0
        for c in infos:
            name, st = c["Name"].lstrip("/"), c["State"]
            uptime = (now - parse_docker_time(st.get("StartedAt", ""))).total_seconds()
            if is_crash_looping(st.get("Status", ""), c.get("RestartCount", 0), uptime,
                                THRESHOLDS["restart_loop_count"]):
                loops += 1
                r.bad(f"{name} is crash-looping ({c.get('RestartCount', 0)} restarts, up {uptime:.0f}s)")
            health = (st.get("Health") or {}).get("Status")
            if health == "unhealthy":
                r.bad(f"{name} is unhealthy")
        if not loops:
            r.ok(f"{len(infos)} containers, none crash-looping")

    # Sustained CPU / memory per container (two samples)
    def stats() -> dict[str, tuple[float, float]]:
        _, out = run(["docker", "stats", "--no-stream", "--format", "{{json .}}"], 60)
        return {s["Name"]: (parse_pct(s.get("CPUPerc")), parse_pct(s.get("MemPerc"))) for s in json_lines(out)}

    s1 = stats()
    time.sleep(THRESHOLDS["sample_seconds"])
    s2 = stats()
    total = 0.0
    flagged = False
    for name, (cpu2, mem) in s2.items():
        cpu = min(cpu2, s1.get(name, (cpu2, 0))[0])
        total += cpu2
        if cpu >= THRESHOLDS["container_cpu_pct"]:
            flagged = True
            r.bad(f"{name} sustained {cpu:.0f}% CPU")
        if mem >= THRESHOLDS["container_mem_pct"]:
            flagged = True
            r.bad(f"{name} at {mem:.0f}% of its memory limit")
    if not flagged:
        r.ok(f"no container above {THRESHOLDS['container_cpu_pct']:.0f}% CPU or "
             f"{THRESHOLDS['container_mem_pct']:.0f}% memory")
    return total


def llm_processes() -> list[tuple[int, str]]:
    _, out = run(["ps", "-axo", "pid=,command="])
    found = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if "llm_service.llm_service" in cmd or cmd.endswith("llm_service.py"):
            found.append((int(pid), cmd))
    return found


def supervised_pids() -> dict[int, Path]:
    pids = {}
    for pf in LLM_RUN.glob("*.pid") if LLM_RUN.exists() else []:
        try:
            pids[int(pf.read_text().strip())] = pf
        except ValueError:
            pids[-1] = pf
    return pids


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OverflowError, ValueError):
        return False


def check_llm(r: Report) -> tuple[list[int], list[Path]]:
    print(BOLD("Host LLM tiers"))
    sup = supervised_pids()
    stale = [pf for pid, pf in sup.items() if not pid_alive(pid)]
    for pf in stale:
        r.bad(f"stale pid file {pf.relative_to(ROOT)} (process is gone)")
    orphans = []
    for pid, cmd in llm_processes():
        if pid not in sup:
            orphans.append(pid)
            r.bad(f"orphaned llm_service process pid {pid} (not started by the supervisor, holds model memory)")
    live = [pf.stem for pid, pf in sup.items() if pid_alive(pid)]
    if not stale and not orphans:
        r.ok(f"supervised tiers: {', '.join(live) if live else 'none running'}")
    return orphans, stale


def dir_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_blocks * 512
            except OSError:
                pass
    return total


def model_inventory() -> list[tuple[str, Path, int]]:
    """(model key, path, bytes) for GGUF files and HF cache repos."""
    items = []
    for base in MODEL_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("*.gguf"):
            if p.is_file() and not p.is_symlink():
                items.append((f"gguf:{p.name}", p, p.stat().st_size))
        for hub in [base / "hub", base / "hf" / "hub", base]:
            if not hub.is_dir():
                continue
            for repo in hub.glob("models--*"):
                size, seen = 0, set()
                for f in repo.rglob("*"):
                    if f.is_file():
                        real = f.resolve()
                        if real not in seen:
                            seen.add(real)
                            size += real.stat().st_size
                items.append((f"hf:{repo.name[8:].replace('--', '/')}", repo, size))
    return items


def check_models(r: Report) -> list[Path]:
    print(BOLD("Model caches"))
    total = 0
    for base in MODEL_DIRS:
        if base.exists():
            size = dir_size(base)
            total += size
            if size > 1e9:
                r.info(f"{gb(size):>9}  {base}")
    (r.bad if total / 1e9 > THRESHOLDS["model_cache_total_gb"] else r.ok)(
        f"model caches total {gb(total)} (threshold {THRESHOLDS['model_cache_total_gb']:.0f} GB)")

    partial = []
    cutoff = time.time() - 86400
    for base in MODEL_DIRS:
        if base.exists():
            partial += [p for p in base.rglob("*.incomplete") if p.stat().st_mtime < cutoff]
    if partial:
        r.bad(f"{len(partial)} abandoned partial downloads, {gb(sum(p.stat().st_size for p in partial))}")

    inv = model_inventory()
    by_key: dict[str, list[tuple[Path, int]]] = {}
    for key, path, size in inv:
        by_key.setdefault(key, []).append((path, size))
    dups = {k: v for k, v in by_key.items() if len({p.resolve() for p, _ in v}) > 1}
    for key, copies in dups.items():
        r.bad(f"{key[key.index(':') + 1:]} is stored {len(copies)} times ({gb(copies[0][1])} each):")
        for p, _ in copies:
            print(f"      {p}")
    largest = sorted(inv, key=lambda x: -x[2])[:5]
    for key, path, size in largest:
        r.info(f"largest: {gb(size):>9}  {key[key.index(':') + 1:]}")
    return partial


# ── clean ─────────────────────────────────────────────────────────────────────
def compose_repos() -> set[str]:
    repos = set()
    for args in (["config", "--images"], ["--profile", "cpu-fallback", "--profile", "lidm", "--profile", "airllm",
                                          "config", "--images"]):
        _, out = run(["docker", "compose", "--project-directory", str(ROOT), *args], 60)
        repos |= {line.strip().split(":")[0] for line in out.splitlines() if line.strip()}
    return repos


def clean(apply: bool) -> int:
    mode = "APPLY" if apply else "DRY RUN (add --apply to execute)"
    print(BOLD(f"Clean: {mode}"))
    actions = 0

    def act(desc: str, cmd: list[str] | None = None, fn=None) -> None:
        nonlocal actions
        actions += 1
        print(f"  {'→' if apply else '·'} {desc}")
        if apply:
            if cmd:
                code, out = run(cmd, 600)
                tail = out.strip().splitlines()[-1:] if out.strip() else []
                print(f"      {DIM(tail[0]) if tail else ''}" if code == 0 else f"      {BAD('failed: ' + out.strip()[:200])}")
            if fn:
                fn()

    if docker_up():
        _, df = run(["docker", "system", "df", "--format", "{{json .}}"])
        cache = next((parse_size(x["Size"]) for x in json_lines(df) if x.get("Type") == "Build Cache"), 0)
        keep = THRESHOLDS["build_cache_keep_gb"]
        if cache / 1e9 > keep:
            act(f"prune build cache {gb(cache)} down to {keep:.0f} GB",
                ["docker", "builder", "prune", "-f", "--max-used-space", f"{int(keep)}gb"])

        _, used = run(["docker", "ps", "-a", "--format", "{{.Image}}"])
        _, used_ids = run(["docker", "ps", "-aq", "--no-trunc"])
        in_use: set[str] = set()
        if used_ids.split():
            _, raw = run(["docker", "inspect", "--format", "{{.Image}}", *used_ids.split()])
            in_use = {x.strip()[7:19] for x in raw.splitlines() if x.strip().startswith("sha256:")}
        _, imgs = run(["docker", "images", "--format", "{{json .}}"])
        images = [{"id": i["ID"][:12], "repo": i["Repository"], "tag": i["Tag"], "size": parse_size(i["Size"]),
                   "created": parse_docker_time(i["CreatedAt"])} for i in json_lines(imgs)]
        protected = compose_repos() | {u.split(":")[0] for u in used.split()}
        cands = image_removal_candidates(images, in_use, protected, THRESHOLDS["image_min_age_days"],
                                         datetime.now(timezone.utc))
        for img in cands:
            label = img["id"] if img["repo"] == "<none>" else f"{img['repo']}:{img['tag']}"
            act(f"remove unused image {label} ({gb(img['size'])}, built {img['created']:%Y-%m-%d})",
                ["docker", "rmi", img["id"]])

        _, ids = run(["docker", "ps", "-aq"])
        if ids.split():
            _, raw = run(["docker", "inspect", *ids.split()])
            now = datetime.now(timezone.utc)
            for c in json.loads(raw or "[]"):
                st = c["State"]
                uptime = (now - parse_docker_time(st.get("StartedAt", ""))).total_seconds()
                if is_crash_looping(st.get("Status", ""), c.get("RestartCount", 0), uptime,
                                    THRESHOLDS["restart_loop_count"]):
                    name = c["Name"].lstrip("/")
                    act(f"stop crash-looping {name} and disable its restart policy "
                        f"(undo: docker update --restart=unless-stopped {name} && docker start {name})",
                        ["sh", "-c", f"docker update --restart=no {name} && docker stop {name}"])
    else:
        print(f"  {DIM('Docker is not running; Docker cleanup skipped')}")

    sup = supervised_pids()
    for pid, pf in sup.items():
        if not pid_alive(pid):
            act(f"remove stale pid file {pf.relative_to(ROOT)}", fn=lambda pf=pf: pf.unlink(missing_ok=True))
    for pid, cmd in llm_processes():
        if pid not in sup:
            act(f"stop orphaned llm_service pid {pid}", fn=lambda pid=pid: os.kill(pid, signal.SIGTERM))

    cutoff = time.time() - 86400
    for base in MODEL_DIRS:
        if base.exists():
            for p in base.rglob("*.incomplete"):
                if p.stat().st_mtime < cutoff:
                    act(f"delete partial download {p} ({gb(p.stat().st_size)})", fn=lambda p=p: p.unlink(missing_ok=True))

    if not actions:
        print(f"  {OK('✓')} nothing to clean")
    print(DIM("  Model weights are never deleted here. Remove a model by hand, e.g.\n"
              "    rm -rf '<cache>/hub/models--org--name'   or   hf cache delete"))
    return 0


def check() -> int:
    r = Report()
    docker_cpu = check_docker(r)
    check_host(r, docker_cpu)
    check_llm(r)
    check_models(r)
    print()
    if r.problems:
        print(BAD(f"{len(r.problems)} issue(s). Preview fixes with: make guard-clean   apply with: make guard-clean APPLY=1"))
        return 1
    print(OK("All clear."))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "clean"], nargs="?", default="check")
    ap.add_argument("--apply", action="store_true", help="clean: actually do it")
    args = ap.parse_args()
    return check() if args.command == "check" else clean(args.apply)


if __name__ == "__main__":
    sys.exit(main())
