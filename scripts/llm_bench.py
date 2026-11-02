"""
Benchmark a running LLM tier over gRPC.

    python scripts/llm_bench.py [--addr localhost:50051] [--runs 1]
                                [--sustain 300] [--power] [--json out.json]

Token counts and model timings come from the server's Usage message (final
stream chunk): exact prompt/completion tokens from the model's tokenizer,
prefill and decode time measured inside the engine, and how many prompt tokens
were reused from the KV cache. Every prompt starts with a unique tag so no
request reuses the previous one's cache unless --allow-cache is given.

Per prompt it prints server prefill (ms and tok/s over evaluated tokens),
server decode tok/s, client time-to-first-token, and client overhead (wall
time minus server queue+prefill+decode: gRPC, serialization, Python).
Against a server without Usage it falls back to chunk counts and a 4-chars-per-
token estimate, and marks those numbers "est".

--sustain re-prompts for N seconds and reports how much of the burst decode
rate survives (thermal behaviour). --power samples `powermetrics` (needs
passwordless sudo, e.g. `sudo -v`) and reports average CPU/GPU/ANE watts and
completion tokens per joule.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

import grpc  # noqa: E402

from llm_service.llm_pb2 import GenerateRequest, GetActiveModelRequest  # noqa: E402
from llm_service.llm_pb2_grpc import LLMServiceStub  # noqa: E402

LONG_CONTEXT = (
    "The orchestrator routes each user request to a tier. The heavy tier handles coding, "
    "reasoning, and analysis. The standard tier handles routing, classification, and "
    "extraction. Every tier speaks the same gRPC contract and streams tokens back. "
) * 40

PROMPTS = [
    ("cold", "Say OK", 16),
    ("short", "What is 2+2? Answer in one word.", 16),
    ("long", "Explain in detail, step by step, how a gRPC streaming RPC differs from a unary RPC, "
             "including flow control, error propagation, and when you would choose each.", 128),
    ("prefill", LONG_CONTEXT + "\n\nSummarise the text above in two sentences.", 64),
]
SUSTAIN_PROMPT = PROMPTS[2]


def run_prompt(stub, prompt, max_tokens, timeout, allow_cache=False):
    if not allow_cache:
        # A unique leading tag defeats KV prefix reuse, so prefill is measured in full.
        prompt = f"[bench {uuid.uuid4().hex[:8]}]\n{prompt}"
    t0 = time.perf_counter()
    first = None
    chunks = 0
    parts = []
    final = None
    for chunk in stub.Generate(GenerateRequest(prompt=prompt, max_tokens=max_tokens, temperature=0.1),
                               timeout=timeout):
        if chunk.token:
            if first is None:
                first = time.perf_counter()
            chunks += 1
            parts.append(chunk.token)
        if chunk.is_final:
            final = chunk
    end = time.perf_counter()
    total = end - t0
    ttft = (first - t0) if first else total
    res = {"text": "".join(parts).strip(), "total_s": total, "client_ttft_s": ttft, "chunks": chunks}

    usage = final.usage if final is not None and final.HasField("usage") else None
    if usage is not None and usage.completion_tokens:
        server_s = (usage.queue_ms + usage.prefill_ms + usage.decode_ms) / 1000
        res.update(
            exact=True,
            finish_reason=final.finish_reason,
            prompt_tokens=usage.prompt_tokens,
            cached_prompt_tokens=usage.cached_prompt_tokens,
            completion_tokens=usage.completion_tokens,
            queue_ms=usage.queue_ms,
            prefill_ms=usage.prefill_ms,
            decode_ms=usage.decode_ms,
            prefill_tok_s=usage.prefill_tokens_per_sec,
            decode_tok_s=usage.tokens_per_sec,
            overhead_ms=max(0.0, (total - server_s) * 1000),
        )
    else:
        window = (end - first) if first else 0.0
        est_prompt = max(1, len(prompt) // 4)
        res.update(
            exact=False,
            finish_reason="",
            prompt_tokens=est_prompt,
            cached_prompt_tokens=0,
            completion_tokens=chunks,
            queue_ms=0.0,
            prefill_ms=ttft * 1000,
            decode_ms=window * 1000,
            prefill_tok_s=est_prompt / ttft if ttft > 0 else 0.0,
            decode_tok_s=(chunks - 1) / window if window > 0 and chunks > 1 else 0.0,
            overhead_ms=0.0,
        )
    return res


class PowerSampler:
    """Wraps `sudo -n powermetrics`; silently disabled when sudo is not cached."""

    PATTERN = re.compile(r"^(CPU|GPU|ANE) Power:\s*([\d.]+)\s*mW", re.M)

    def __init__(self):
        self.proc = None
        self.out = tempfile.NamedTemporaryFile("w+", suffix=".powermetrics", delete=False)
        self.t0 = self.t1 = None

    def start(self):
        try:
            self.proc = subprocess.Popen(
                ["sudo", "-n", "powermetrics", "--samplers", "cpu_power,gpu_power,ane_power", "-i", "1000"],
                stdout=self.out, stderr=subprocess.DEVNULL)
            time.sleep(1.5)
            if self.proc.poll() is not None:
                print("power: powermetrics unavailable (run `sudo -v` first); skipping power")
                self.proc = None
        except FileNotFoundError:
            self.proc = None
        self.t0 = time.perf_counter()
        return self.proc is not None

    def stop(self):
        self.t1 = time.perf_counter()
        if not self.proc:
            return None
        subprocess.run(["sudo", "-n", "kill", "-INT", str(self.proc.pid)], stderr=subprocess.DEVNULL)
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.out.seek(0)
        samples = {"CPU": [], "GPU": [], "ANE": []}
        for rail, mw in self.PATTERN.findall(self.out.read()):
            samples[rail].append(float(mw))
        avg = {k: (sum(v) / len(v) / 1000.0 if v else 0.0) for k, v in samples.items()}
        avg["all"] = avg["CPU"] + avg["GPU"] + avg["ANE"]
        avg["seconds"] = self.t1 - self.t0
        avg["joules"] = avg["all"] * avg["seconds"]
        return avg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--addr", default="localhost:50051")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--sustain", type=float, default=0.0, help="seconds of continuous load after the burst set")
    ap.add_argument("--power", action="store_true")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--allow-cache", action="store_true", help="do not tag prompts; allow KV prefix reuse")
    ap.add_argument("--json", help="write all results to this file")
    args = ap.parse_args()

    stub = LLMServiceStub(grpc.insecure_channel(args.addr))
    try:
        info = stub.GetActiveModel(GetActiveModelRequest(), timeout=10)
        meta = {"model": info.model_name, "file": info.model_filename, "tier": info.tier,
                "engine": info.engine or info.backend, "device": info.device or "n/a",
                "ctx": info.context_window}
    except grpc.RpcError as e:
        meta = {"model": "?", "file": "?", "tier": "?", "engine": "?", "device": "?", "ctx": 0,
                "error": e.code().name}
    print("target={} model={model} tier={tier} engine={engine} device={device} ctx={ctx}".format(args.addr, **meta))

    power = PowerSampler() if args.power else None
    if power:
        power.start()

    burst = []
    for r in range(args.runs):
        for label, prompt, max_tok in PROMPTS:
            res = run_prompt(stub, prompt, max_tok, args.timeout, args.allow_cache)
            res.update(label=label, run=r + 1)
            burst.append(res)
            est = "" if res["exact"] else " est"
            preview = (res["text"][:40] + "…") if len(res["text"]) > 40 else res["text"]
            print(f"[{r+1}/{args.runs}] {label:7s} prompt={res['prompt_tokens']:5d}{est} "
                  f"(cached {res['cached_prompt_tokens']}) prefill={res['prefill_ms']:7.0f}ms "
                  f"{res['prefill_tok_s']:6.0f} tok/s{est} | out={res['completion_tokens']:4d}{est} "
                  f"{res['finish_reason'] or '?':6s} decode={res['decode_tok_s']:6.1f} tok/s{est} | "
                  f"client ttft={res['client_ttft_s']*1000:6.0f}ms overhead={res['overhead_ms']:5.0f}ms  {preview!r}")

    sustained = []
    if args.sustain > 0:
        _, prompt, max_tok = SUSTAIN_PROMPT
        t_start = time.perf_counter()
        while time.perf_counter() - t_start < args.sustain:
            res = run_prompt(stub, prompt, max_tok, args.timeout, args.allow_cache)
            res["t"] = time.perf_counter() - t_start
            sustained.append(res)
        print(f"sustain: {len(sustained)} requests over {args.sustain:.0f}s")

    watts = power.stop() if power else None

    def median(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else 0.0

    long_runs = [b for b in burst if b["label"] == "long"]
    pre_runs = [b for b in burst if b["label"] == "prefill"]
    exact = all(b["exact"] for b in burst)
    summary = dict(meta, addr=args.addr, exact=exact,
                   decode_tok_s=round(median([b["decode_tok_s"] for b in long_runs]), 1),
                   long_prefill_ms=round(median([b["prefill_ms"] for b in long_runs])),
                   prefill_prompt_tokens=pre_runs[0]["prompt_tokens"] if pre_runs else 0,
                   prefill_ms=round(median([b["prefill_ms"] for b in pre_runs])),
                   prefill_tok_s=round(median([b["prefill_tok_s"] for b in pre_runs])),
                   client_overhead_ms=round(median([b["overhead_ms"] for b in burst]), 1))
    if sustained:
        first_rate = sustained[0]["decode_tok_s"]
        at60 = next((s["decode_tok_s"] for s in sustained if s["t"] >= 60), sustained[-1]["decode_tok_s"])
        last_rate = sustained[-1]["decode_tok_s"]
        summary.update(sustain_s=args.sustain, decode_t0=round(first_rate, 1), decode_t60=round(at60, 1),
                       decode_end=round(last_rate, 1),
                       retained_pct=round(100.0 * last_rate / first_rate, 1) if first_rate else 0.0)
    if watts:
        decode_tokens = sum(s["completion_tokens"] for s in burst + sustained)
        summary.update(avg_w_cpu=round(watts["CPU"], 2), avg_w_gpu=round(watts["GPU"], 2),
                       avg_w_ane=round(watts["ANE"], 2), avg_w_all=round(watts["all"], 2),
                       tokens_per_joule=round(decode_tokens / watts["joules"], 2) if watts["joules"] else 0.0)

    print("SUMMARY " + " ".join(f"{k}={v}" for k, v in summary.items() if k != "error"))
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"summary": summary, "burst": burst, "sustained": sustained, "power": watts}, fh, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
