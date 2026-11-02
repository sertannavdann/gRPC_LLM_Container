"""Stability test for a running GPU LLM tier.

Usage:
    python scripts/llm_stability.py [--addr localhost:50051] [--soak 60] [--concurrency 4]
                                    [--expect-device metal] [--pidfile logs/llm/heavy.pid]
                                    [--long-ctx] [--json out.json]

Where llm_bench.py measures speed, this script checks that the tier keeps
behaving under the conditions that break GPU serving in practice:

  health      Health/Check is SERVING and GetActiveModel reports the expected device.
  accounting  A capped request returns exactly max_tokens with finish_reason=length,
              and a short answer finishes with finish_reason=stop.
  concurrency N parallel requests all complete with a final chunk; the engine
              serialises them (queue_ms > 0 on at least one) and never errors.
  soak        Continuous requests for --soak seconds; the last quarter's median
              decode speed must stay within --degrade of the first quarter's,
              with zero errors (catches thermal throttling and GPU contention).
  memory      RSS of the tier process (from --pidfile) must not grow by more
              than --rss-growth MB across the soak (catches KV/graph leaks).
  overflow    A prompt longer than the context window must fail cleanly with a
              gRPC error while the process stays alive and SERVING
              (llama.cpp only; MLX has no hard context limit).
  long-ctx    (--long-ctx) A prompt filling ~70% of the context window
              completes; this is where Metal memory pressure first shows.

Exit code 0 when every check passes, 1 otherwise. Run from the repo root.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

import grpc  # noqa: E402
from grpc_health.v1 import health_pb2, health_pb2_grpc  # noqa: E402

from llm_service.llm_pb2 import GenerateRequest, GetActiveModelRequest  # noqa: E402
from llm_service.llm_pb2_grpc import LLMServiceStub  # noqa: E402

SOAK_PROMPT = (
    "Explain how a gRPC streaming RPC differs from a unary RPC, including flow "
    "control and error propagation. Use concrete examples."
)


class Check:
    def __init__(self):
        self.results = []
        self.failed = False

    def record(self, name, ok, detail):
        self.results.append({"check": name, "ok": bool(ok), "detail": detail})
        self.failed |= not ok
        print(f"{'PASS' if ok else 'FAIL'} {name:12s} {detail}")


def generate(stub, prompt, max_tokens, timeout, tag=True):
    """Run one request and return (text, final_chunk, wall_s). Raises grpc.RpcError."""
    if tag:
        prompt = f"[stab {uuid.uuid4().hex[:8]}]\n{prompt}"
    t0 = time.perf_counter()
    parts, final = [], None
    for chunk in stub.Generate(GenerateRequest(prompt=prompt, max_tokens=max_tokens, temperature=0.1),
                               timeout=timeout):
        if chunk.token:
            parts.append(chunk.token)
        if chunk.is_final:
            final = chunk
    return "".join(parts), final, time.perf_counter() - t0


def health_status(channel):
    try:
        resp = health_pb2_grpc.HealthStub(channel).Check(health_pb2.HealthCheckRequest(service=""), timeout=5)
        return health_pb2.HealthCheckResponse.ServingStatus.Name(resp.status)
    except grpc.RpcError as e:
        return f"ERROR:{e.code().name}"


def rss_mb(pid):
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=True)
        return int(out.stdout.strip() or 0) / 1024
    except (subprocess.CalledProcessError, ValueError):
        return None


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--addr", default="localhost:50051")
    ap.add_argument("--expect-device", default="metal", help="'' to skip the device check")
    ap.add_argument("--pidfile", default="", help="tier pid file for RSS/liveness checks (logs/llm/<tier>.pid)")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--soak", type=float, default=60.0, help="seconds of continuous load; 0 disables")
    ap.add_argument("--soak-tokens", type=int, default=64)
    ap.add_argument("--degrade", type=float, default=0.15, help="allowed drop in decode tok/s, last vs first quarter")
    ap.add_argument("--rss-growth", type=float, default=512.0, help="allowed RSS growth in MB over the soak")
    ap.add_argument("--long-ctx", action="store_true", help="also fill ~70%% of the context window")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--json", help="write results to this file")
    args = ap.parse_args()

    check = Check()
    channel = grpc.insecure_channel(args.addr)
    stub = LLMServiceStub(channel)

    # --- health -------------------------------------------------------------
    status = health_status(channel)
    try:
        info = stub.GetActiveModel(GetActiveModelRequest(), timeout=10)
    except grpc.RpcError as e:
        check.record("health", False, f"{args.addr} unreachable: {e.code().name}")
        return 1
    device, engine, n_ctx = info.device, info.engine, info.context_window
    dev_ok = not args.expect_device or device == args.expect_device
    check.record("health", status == "SERVING" and dev_ok,
                 f"{status} model={info.model_name} tier={info.tier} engine={engine} device={device} ctx={n_ctx}")

    pid = None
    if args.pidfile:
        try:
            pid = int(open(args.pidfile).read().strip())
        except (OSError, ValueError):
            check.record("pidfile", False, f"cannot read {args.pidfile}")
    rss_before = rss_mb(pid) if pid else None

    # --- accounting ---------------------------------------------------------
    try:
        text, final, _ = generate(stub, SOAK_PROMPT, 40, args.timeout)
        u = final.usage
        ok = (final.HasField("usage") and u.completion_tokens == 40 and final.finish_reason == "length"
              and u.prompt_tokens > 0 and u.decode_ms > 0)
        check.record("accounting", ok,
                     f"cap=40 got={u.completion_tokens} finish={final.finish_reason} "
                     f"prompt={u.prompt_tokens} decode={u.tokens_per_sec:.1f} tok/s")
        # The service has no chat templating yet, so a raw prompt lets a small model
        # ramble instead of emitting end-of-text. Wrap this one in ChatML (both tiers
        # are Qwen2.5) so the check exercises the engine's EOS handling, not the model's whim.
        chat = ("<|im_start|>user\nReply with the single word OK and nothing else.<|im_end|>\n"
                "<|im_start|>assistant\n")
        text, final, _ = generate(stub, chat, 64, args.timeout, tag=False)
        check.record("stop", final.finish_reason == "stop" and final.usage.completion_tokens < 64,
                     f"finish={final.finish_reason} tokens={final.usage.completion_tokens} text={text.strip()[:30]!r}")
    except grpc.RpcError as e:
        check.record("accounting", False, f"rpc error {e.code().name}: {e.details()}")

    # --- concurrency --------------------------------------------------------
    def one(_):
        try:
            _, final, wall = generate(stub, SOAK_PROMPT, 32, args.timeout)
            return {"ok": final is not None, "queue_ms": final.usage.queue_ms, "wall_s": wall}
        except grpc.RpcError as e:
            return {"ok": False, "error": e.code().name}

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        outcomes = list(pool.map(one, range(args.concurrency)))
    all_ok = all(o["ok"] for o in outcomes)
    queued = [o["queue_ms"] for o in outcomes if o.get("ok")]
    check.record("concurrency", all_ok and (args.concurrency < 2 or max(queued, default=0) > 0),
                 f"n={args.concurrency} completed={sum(o['ok'] for o in outcomes)} "
                 f"max_queue={max(queued, default=0):.0f}ms errors={[o.get('error') for o in outcomes if not o['ok']]}")

    # --- soak ---------------------------------------------------------------
    speeds, errors, n_req = [], 0, 0
    if args.soak > 0:
        t_end = time.perf_counter() + args.soak
        while time.perf_counter() < t_end:
            n_req += 1
            try:
                _, final, _ = generate(stub, SOAK_PROMPT, args.soak_tokens, args.timeout)
                speeds.append(final.usage.tokens_per_sec)
            except grpc.RpcError:
                errors += 1
        if len(speeds) >= 8:
            q = max(2, len(speeds) // 4)
            first, last = statistics.median(speeds[:q]), statistics.median(speeds[-q:])
            drop = (first - last) / first if first else 1.0
            check.record("soak", errors == 0 and drop <= args.degrade,
                         f"{n_req} req in {args.soak:.0f}s first_q={first:.1f} last_q={last:.1f} tok/s "
                         f"drop={drop*100:.1f}% (limit {args.degrade*100:.0f}%) errors={errors}")
        else:
            check.record("soak", errors == 0 and speeds,
                         f"{n_req} req, too few for a trend; median={statistics.median(speeds) if speeds else 0:.1f} errors={errors}")

    # --- memory -------------------------------------------------------------
    if pid:
        rss_after = rss_mb(pid)
        if rss_before is None or rss_after is None:
            check.record("memory", False, f"pid {pid} not found")
        else:
            growth = rss_after - rss_before
            check.record("memory", growth <= args.rss_growth,
                         f"rss {rss_before:.0f} -> {rss_after:.0f} MB (+{growth:.0f}, limit {args.rss_growth:.0f})")

    # --- overflow -----------------------------------------------------------
    if engine == "llamacpp":
        # ~1 token per 3-4 chars; make it comfortably longer than the window.
        huge = "lorem ipsum " * (n_ctx * 2)
        try:
            generate(stub, huge, 8, args.timeout, tag=False)
            check.record("overflow", False, "oversized prompt was accepted")
        except grpc.RpcError as e:
            still = health_status(channel)
            alive = pid_alive(pid) if pid else True
            check.record("overflow", e.code() == grpc.StatusCode.INTERNAL and still == "SERVING" and alive,
                         f"rejected with {e.code().name}; health={still} alive={alive}")
    else:
        print(f"SKIP overflow     engine={engine} has no hard context limit")

    # --- long-ctx -----------------------------------------------------------
    if args.long_ctx:
        words = int(n_ctx * 0.7 * 0.75)  # ~0.75 words per token for English prose
        prompt = ("The quick brown fox jumps over the lazy dog. " * (words // 9 + 1)) + "\nSummarise the above in one sentence."
        try:
            _, final, wall = generate(stub, prompt, 32, args.timeout)
            u = final.usage
            check.record("long-ctx", final.finish_reason in ("stop", "length"),
                         f"prompt={u.prompt_tokens}/{n_ctx} prefill={u.prefill_ms/1000:.1f}s "
                         f"({u.prefill_tokens_per_sec:.0f} tok/s) wall={wall:.1f}s")
        except grpc.RpcError as e:
            check.record("long-ctx", False, f"rpc error {e.code().name}: {e.details()}")

    # --- final health -------------------------------------------------------
    final_status = health_status(channel)
    check.record("final", final_status == "SERVING" and (pid is None or pid_alive(pid)),
                 f"health={final_status}" + (f" pid={pid} alive={pid_alive(pid)}" if pid else ""))

    summary = {
        "addr": args.addr, "model": info.model_name, "tier": info.tier, "engine": engine, "device": device,
        "ctx": n_ctx, "passed": not check.failed, "soak_speeds": speeds, "checks": check.results,
    }
    if args.json:
        with open(args.json, "w") as f:
            json.dump(summary, f, indent=2)
    print(f"RESULT {'PASS' if not check.failed else 'FAIL'} model={info.model_name} tier={info.tier} "
          f"engine={engine} device={device} checks={sum(r['ok'] for r in check.results)}/{len(check.results)}")
    return 0 if not check.failed else 1


if __name__ == "__main__":
    sys.exit(main())
