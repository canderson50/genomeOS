"""Run one command on a disposable RunPod GPU pod for the drafting agent, inside a hard budget.

  python runpod_job.py check    --gpu "NVIDIA A40"
  python runpod_job.py run      --sha <pushed commit> --gpu "NVIDIA A40" --minutes 120 \
                                --ledger <agent-notes>/gpu-ledger.tsv --out <dir> -- <command ...>
  python runpod_job.py selftest --gpu "NVIDIA A40" --ledger <agent-notes>/gpu-ledger.tsv

Uses RunPod's REST API v2 (https://api.runpod.io/v2). Every step fails closed; there is no
fallback and no force option.

- `check` reads the live v2 contract and refuses when create-pod no longer accepts a field this
  script sends, or the endpoints it calls are gone. It then reads the live GPU catalog and refuses
  a GPU type that is unknown, not on Secure Cloud, or out of stock. `run` and `selftest` run it.
- The ledger (one TSV row per pod) is the budget: a pod starts only if this UTC month's recorded
  spend plus the GPU's catalog price x `--minutes` stays within `--budget`, the price is at most
  `--max-rate`, and `selftest` has recorded that a pod stops billing at its deadline on its own.
  The caller commits the ledger after every pod, including failed ones.
- The pod sees only the public fork at one commit, downloaded anonymously. No credential, token
  or private file is sent to it. It serves its results on port 8000 through RunPod's HTTP proxy.
  At its deadline it deletes itself if RunPod gave it a pod-scoped key, and exits its container
  either way, which stops GPU billing even if this process has died. This process deletes it too.

Requests carry no key of their own: the cloud environment's network secret adds it for
api.runpod.io. RUNPOD_API_KEY, when set, is sent instead, for running elsewhere.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.runpod.io/v2"
IMAGE = "nvidia/cuda:12.4.1-base-ubuntu22.04"
MIN_CUDA = "12.4"  # the image's CUDA runtime; hosts with an older driver cannot run it
GPU_EXTRAS = "jax[cuda12]==0.11.2 cupy-cuda12x==14.2.0 cuda-pathfinder==1.8.1"
FIELD_TYPES = {
    "name": "string",
    "image": "string",
    "cloud": None,
    "gpu": None,
    "disk": "integer",
    "env": "object",
    "ports": "array",
    "entrypoint": "array",
}
ENDPOINTS = (
    ("/v2/pods", "post"),
    ("/v2/pods/{id}", "get"),
    ("/v2/pods/{id}", "delete"),
    ("/v2/catalog/gpus", "get"),
)
LEDGER_HEADER = "date\tpod\tgpu\tusd_per_hr\tminutes\tusd\tsha\texit\tnote\n"
REACH_MINUTES = 12  # abandon a pod whose results endpoint never answers within this long
GONE = {"EXITED", "ERROR", "TERMINATED"}
# RunPod's edge rejects Python's default User-Agent (Cloudflare error 1010), so name the client.
USER_AGENT = "genomeos-drafter/1 (+https://github.com/canderson50/genomeOS)"

# Runs inside the pod. Results land in /results, served on :8000 from the start, so progress is
# visible while the command runs. The work runs in the background; the foreground waits for
# DEADLINE (epoch seconds), then deletes the pod with the pod-scoped key RunPod may inject and
# exits, so the container stops even when that key is missing or refused.
POD_SCRIPT = r"""
set -u
mkdir -p /results; cd /results || exit 1
phase() { printf '{"phase": "%s", "time": "%s"}\n' "$1" "$(date -u +%FT%TZ)" > /results/status.json; }
remove_self() {
  curl -s -X DELETE -H "Authorization: Bearer ${RUNPOD_API_KEY:-none}" \
    "https://api.runpod.io/v2/pods/${RUNPOD_POD_ID:-none}" > /results/selfdelete.log 2>&1
  curl -s -H 'Content-Type: application/json' \
    -d "{\"query\": \"mutation { podTerminate(input: {podId: \\\"${RUNPOD_POD_ID:-none}\\\"}) }\"}" \
    "https://api.runpod.io/graphql?api_key=${RUNPOD_API_KEY:-none}" >> /results/selfdelete.log 2>&1
}
if [ "$(date +%s)" -ge "$DEADLINE" ]; then exit 0; fi
work() {
  phase setup
  apt-get update -qq && apt-get install -y -qq --no-install-recommends curl ca-certificates git \
    python3 > /results/setup.log 2>&1
  python3 -m http.server 8000 --directory /results > /dev/null 2>&1 &
  nvidia-smi > /results/nvidia-smi.txt 2>&1
  if [ "${SELFTEST:-0}" = "1" ]; then phase selftest-waiting; return; fi
  curl -LsSf https://astral.sh/uv/install.sh | sh >> /results/setup.log 2>&1
  export PATH="$HOME/.local/bin:$PATH"
  mkdir -p /work; cd /work || { phase failed; return; }
  curl -LsSf "https://codeload.github.com/${REPO}/tar.gz/${SHA}" | tar -xz --strip-components=1
  # shellcheck disable=SC1091
  { uv venv --python 3.12 .venv && . .venv/bin/activate && uv pip install -r requirements.lock \
    && uv pip install -e . --no-deps && read -ra extras <<< "$GPU_EXTRAS" \
    && uv pip install "${extras[@]}"; } >> /results/setup.log 2>&1
  setup_rc=$?
  uv pip freeze > /results/freeze.txt 2>&1
  phase running
  if [ "$setup_rc" -eq 0 ]; then
    timeout "$COMMAND_SECONDS" bash -c "$COMMAND" > /results/command.log 2>&1; rc=$?
  else
    rc=$(( 1000 + setup_rc ))
  fi
  cp -f /work/*.xml /results/ 2>/dev/null
  cd /results || { phase failed; return; }
  # status.json is live progress, rewritten to "done" after this manifest, so it is never hashed.
  python3 - "$rc" "$SHA" <<'PY'
import hashlib, json, pathlib, sys
live = {"done.json", "status.json"}
files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted(pathlib.Path(".").iterdir()) if p.is_file() and p.name not in live}
json.dump({"exit": int(sys.argv[1]), "sha": sys.argv[2], "files": files}, open("done.json", "w"))
PY
  phase "done"
}
work &
sleep $(( DEADLINE - $(date +%s) ))
remove_self
exit 0
"""


class Refusal(SystemExit):
    """A fail-closed stop: printed and exited with status 2."""

    def __init__(self, message: str):
        print(f"REFUSED: {message}", file=sys.stderr)
        super().__init__(2)


def request(method: str, url: str, body: dict | None = None) -> tuple[int, bytes]:
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if os.environ.get("RUNPOD_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['RUNPOD_API_KEY']}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def properties(spec: dict, schema: dict) -> dict:
    """Every property a schema accepts, following $ref and allOf."""
    if "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    found = dict(schema.get("properties", {}))
    for part in schema.get("allOf", []):
        found.update(properties(spec, part))
    return found


def check(gpu: str) -> dict:
    """Validate the live contract and the GPU; return the GPU's catalog entry."""
    status, raw = request("GET", f"{API}/openapi.json")
    if status != 200:
        raise Refusal(f"could not read the live v2 contract ({status})")
    spec = json.loads(raw)
    for path, method in ENDPOINTS:
        if method not in spec.get("paths", {}).get(path, {}):
            raise Refusal(f"the live contract has no {method.upper()} {path}")
    create = spec["paths"]["/v2/pods"]["post"]["requestBody"]["content"]["application/json"]
    accepted = properties(spec, create["schema"])
    for field, kind in FIELD_TYPES.items():
        if field not in accepted:
            raise Refusal(f"create-pod no longer accepts {field!r}")
        if kind and accepted[field].get("type") != kind:
            raise Refusal(f"create-pod field {field!r} is {accepted[field].get('type')!r}, not {kind!r}")
    gpu_fields = properties(spec, accepted["gpu"])
    for field in ("id", "count", "minCudaVersion"):
        if field not in gpu_fields:
            raise Refusal(f"create-pod gpu no longer accepts {field!r}")
    pod_fields = properties(spec, {"$ref": "#/components/schemas/Pod"})
    if not {"id", "status", "cost"} <= set(pod_fields):
        raise Refusal("the Pod schema no longer reports id, status and cost")

    query = urllib.parse.urlencode({"product": "POD", "include": "AVAILABILITY"})
    status, raw = request("GET", f"{API}/catalog/gpus?{query}")
    if status != 200:
        raise Refusal(f"could not read the GPU catalog ({status}); is the RunPod key in place?")
    entry = next((g for g in json.loads(raw)["gpus"] if g["id"] == gpu), None)
    if entry is None:
        raise Refusal(f"unknown GPU type {gpu!r}")
    if not entry["secure"] or not entry["price"]["secure"]:
        raise Refusal(f"{gpu!r} is not offered on Secure Cloud")
    if entry.get("availability") == "NONE":
        raise Refusal(f"{gpu!r} has no Secure Cloud stock right now")
    print(
        f"contract ok; {gpu!r} on Secure Cloud at ${entry['price']['secure']}/h, "
        f"availability {entry.get('availability')}"
    )
    return entry


def ledger_rows(ledger: pathlib.Path) -> list[dict]:
    if not ledger.exists():
        return []
    lines = ledger.read_text().splitlines()
    if not lines or lines[0] + "\n" != LEDGER_HEADER:
        raise Refusal(f"{ledger} does not start with the expected header")
    keys = LEDGER_HEADER.strip().split("\t")
    return [dict(zip(keys, line.split("\t"), strict=True)) for line in lines[1:] if line]


def month_spend(rows: list[dict], now: dt.datetime) -> float:
    month = now.strftime("%Y-%m")
    return sum(float(row["usd"]) for row in rows if row["date"].startswith(month))


def append_ledger(ledger: pathlib.Path, row: list[str]) -> None:
    if not ledger.exists():
        ledger.write_text(LEDGER_HEADER)
    with ledger.open("a") as handle:
        handle.write("\t".join(cell.replace("\t", " ") for cell in row) + "\n")


def gate(args, now: dt.datetime, need_selftest: bool) -> float:
    """Check the contract, GPU, selftest record and budget; return the catalog price per hour."""
    price = float(check(args.gpu)["price"]["secure"])
    if price > args.max_rate:
        raise Refusal(f"{args.gpu!r} costs ${price}/h, above --max-rate ${args.max_rate}/h")
    rows = ledger_rows(args.ledger)
    if need_selftest and not any(row["note"].startswith("selftest-passed") for row in rows):
        raise Refusal("no recorded selftest-passed row; run `selftest` first")
    spent = month_spend(rows, now)
    worst = price * args.minutes / 60
    if spent + worst > args.budget:
        raise Refusal(f"budget: ${spent:.2f} spent this month + up to ${worst:.2f} > ${args.budget:.2f}")
    print(f"budget ok: ${spent:.2f} spent in {now:%Y-%m}; this pod costs at most ${worst:.2f}")
    return price


def create_pod(args, name: str, deadline: int, env: dict) -> str:
    command_seconds = max(60, deadline - int(time.time()) - 15 * 60)
    env = {"DEADLINE": str(deadline), "COMMAND_SECONDS": str(command_seconds), **env}
    body = {
        "name": name,
        "image": IMAGE,
        "cloud": "SECURE",
        "gpu": {"id": args.gpu, "count": 1, "minCudaVersion": MIN_CUDA},
        "disk": 60,
        "ports": ["8000/http"],
        "env": env,
        "entrypoint": ["bash", "-c", POD_SCRIPT],
    }
    status, raw = request("POST", f"{API}/pods", body)
    if status != 201:
        raise Refusal(f"pod creation failed ({status}): {raw[:500]!r}")
    pod_id = json.loads(raw)["id"]
    print(f"pod {pod_id} created on {args.gpu}")
    return pod_id


def pod_state(pod_id: str) -> tuple[str, float | None]:
    """The pod's status and billed USD/h; ("TERMINATED", None) once it no longer exists."""
    status, raw = request("GET", f"{API}/pods/{pod_id}")
    if status == 404:
        return "TERMINATED", None
    if status != 200:
        return f"UNREADABLE-{status}", None
    pod = json.loads(raw)
    return pod.get("status", "UNKNOWN"), pod.get("cost")


def delete_pod(pod_id: str) -> bool:
    request("DELETE", f"{API}/pods/{pod_id}")
    for _ in range(12):
        if pod_state(pod_id)[0] == "TERMINATED":
            return True
        time.sleep(5)
    return False


def fetch(url: str) -> bytes | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError):
        return None


def record(args, now, pod_id, rate, started, sha, exit_code, note) -> None:
    minutes = (time.time() - started) / 60
    usd = rate * minutes / 60
    append_ledger(
        args.ledger,
        [
            now.strftime("%Y-%m-%dT%H:%MZ"),
            pod_id,
            args.gpu,
            f"{rate}",
            f"{minutes:.1f}",
            f"{usd:.4f}",
            sha,
            exit_code,
            note,
        ],
    )
    print(f"{note}: pod {pod_id}, {minutes:.1f} min, about ${usd:.2f}; ledger updated")


def run(args) -> int:
    now = dt.datetime.now(dt.UTC)
    rate = gate(args, now, need_selftest=True)
    if len(args.sha) != 40:
        raise Refusal("--sha must be a full 40-character commit SHA that is pushed to the fork")
    started = time.time()
    deadline = int(started + args.minutes * 60)
    command = shlex.join(args.command)
    env = {"REPO": args.repo, "SHA": args.sha, "COMMAND": command, "GPU_EXTRAS": GPU_EXTRAS}
    pod_id = create_pod(args, f"genomeos-drafter-{args.sha[:7]}", deadline, env)
    exit_code, note = "none", "no-results"
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        base = f"https://{pod_id}-8000.proxy.runpod.net"
        reached = False
        while time.time() < deadline - 60:
            state, cost = pod_state(pod_id)
            if cost:
                if cost > rate * 1.1:
                    note = f"billed ${cost}/h, above the catalog ${rate}/h"
                    return 2
                rate = max(rate, cost)
            if state in GONE:
                note = f"pod {state.lower()} before results"
                return 2
            reached = reached or fetch(f"{base}/status.json") is not None
            if not reached and time.time() > started + REACH_MINUTES * 60:
                note = f"results endpoint unreachable after {REACH_MINUTES} min"
                return 2
            done = fetch(f"{base}/done.json")
            if done:
                manifest = json.loads(done)
                (args.out / "done.json").write_bytes(done)
                for name, digest in manifest["files"].items():
                    content = fetch(f"{base}/{name}") or b""
                    (args.out / name).write_bytes(content)
                    if hashlib.sha256(content).hexdigest() != digest:
                        note = f"hash mismatch on {name}"
                        return 2
                if manifest["sha"] != args.sha:
                    note = "pod ran a different commit"
                    return 2
                exit_code, note = str(manifest["exit"]), "results-verified"
                print(f"command exit {exit_code}; {len(manifest['files'])} files in {args.out}")
                return 0 if manifest["exit"] == 0 else 1
            time.sleep(30)
        note = "deadline reached without results"
        return 2
    finally:
        if not delete_pod(pod_id):
            note += "; DELETE NOT CONFIRMED"
        record(args, now, pod_id, rate, started, args.sha, exit_code, note)


def selftest(args) -> int:
    """Start an idle pod; pass only if its results endpoint answers and it then stops billing.

    This process never stops the pod unless the test has already failed, so a pass proves the
    in-pod deadline works without help. Removing itself or exiting its container (status EXITED,
    billed $0/h) both count; an exited pod is then deleted here.
    """
    now = dt.datetime.now(dt.UTC)
    args.minutes = REACH_MINUTES + 3
    rate = gate(args, now, need_selftest=False)
    started = time.time()
    deadline = int(started + args.minutes * 60)
    pod_id = create_pod(args, "genomeos-drafter-selftest", deadline, {"SELFTEST": "1"})
    base = f"https://{pod_id}-8000.proxy.runpod.net"
    reached, outcome = False, None
    while time.time() < deadline + 5 * 60:
        reached = reached or fetch(f"{base}/status.json") is not None
        state, cost = pod_state(pod_id)
        if cost:
            rate = max(rate, cost)
        if state == "TERMINATED":
            outcome = "removed itself"
            break
        if state == "EXITED" and not cost:
            outcome = "stopped itself"
            break
        if state == "ERROR":
            break
        time.sleep(20)
    passed = reached and outcome is not None
    note = "selftest-passed" if passed else "selftest-failed"
    note += f" (endpoint {'reached' if reached else 'never reached'}, {outcome or 'kept running'})"
    if outcome != "removed itself":
        note += "; deleted by caller" if delete_pod(pod_id) else "; DELETE NOT CONFIRMED"
    record(args, now, pod_id, rate, started, "-", "-", note)
    return 0 if passed else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["check", "run", "selftest"])
    parser.add_argument("--gpu", default="NVIDIA A40")
    parser.add_argument("--repo", default="canderson50/genomeOS")
    parser.add_argument("--sha", default="")
    parser.add_argument("--minutes", type=int, default=120)
    parser.add_argument("--budget", type=float, default=25.0, help="USD per UTC calendar month")
    parser.add_argument("--max-rate", type=float, default=2.0, help="refuse GPUs above this USD/h")
    parser.add_argument("--ledger", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("gpu-results"))
    parser.add_argument("command", nargs="*")
    args = parser.parse_args()
    if args.minutes > 120:
        raise Refusal("--minutes may not exceed 120")
    if args.action == "check":
        check(args.gpu)
        return 0
    if args.ledger is None:
        raise Refusal("--ledger is required")
    if args.action == "selftest":
        return selftest(args)
    if not args.command:
        raise Refusal("give the command to run after --")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
