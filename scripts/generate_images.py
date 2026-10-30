#!/usr/bin/env python3
"""Generate numbered PNGs from prompts.txt, or submit/collect an image batch.

Python 3.11+, standard library only. Preview is the default; --execute spends API
credits. See docs/IMAGE_PIPELINE.md for billing and recovery boundaries.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import hashlib
import json
import os
import random
import re
import shutil
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path

API = "https://api.openai.com/v1"
MODEL = "gpt-image-2.5-sunburst"
TERMINAL = {"completed", "failed", "expired", "cancelled"}
FATAL_CREDIT = {"credit_balance_exhausted", "insufficient_quota", "billing_hard_limit_reached"}
PNG = b"\x89PNG\r\n\x1a\n"


class APIError(RuntimeError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"HTTP {status}: {code}: {message}")
        self.status, self.code = status, code


class Client:
    def __init__(self, retries=5, timeout=600):
        self.key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not self.key:
            raise ValueError("Set OPENAI_API_KEY for the organization receiving the credits.")
        self.retries, self.timeout = retries, timeout

    def request(self, method, path, body=None, content_type="application/json", destination=None):
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": content_type}
        for env, header in (("OPENAI_ORG_ID", "OpenAI-Organization"),
                            ("OPENAI_PROJECT_ID", "OpenAI-Project")):
            if os.environ.get(env):
                headers[header] = os.environ[env]
        data = body if isinstance(body, bytes) else (
            json.dumps(body).encode() if body is not None else None)
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    if destination is not None:
                        temp = destination.with_suffix(destination.suffix + ".part")
                        with temp.open("wb") as handle:
                            shutil.copyfileobj(response, handle, length=1024 * 1024)
                        temp.replace(destination)
                        return None
                    payload = response.read()
                return json.loads(payload)
            except urllib.error.HTTPError as exc:
                try:
                    error = json.loads(exc.read()).get("error", {})
                except (ValueError, AttributeError):
                    error = {}
                code = str(error.get("code") or error.get("type") or "http_error")
                message = str(error.get("message") or exc.reason).replace(self.key, "[redacted]")
                if exc.code != 429 or code in FATAL_CREDIT or attempt == self.retries:
                    raise APIError(exc.code, code, message) from None
                try:
                    retry_after = float(exc.headers.get("Retry-After", "0"))
                except ValueError:
                    retry_after = 0
                delay = max(retry_after, min(60, 2 ** attempt + random.random()))
                if delay > 60:
                    raise APIError(429, code, "Retry-After exceeds 60s; rerun later.") from None
                print(f"Rate limited; retry {attempt + 1}/{self.retries} in {delay:.1f}s", file=sys.stderr)
                time.sleep(delay)
            # Do not replay a paid POST after a timeout, connection failure or 5xx:
            # the server may have accepted it. The persisted state records ambiguity.

    def upload(self, content):
        boundary = "afs-image-" + uuid.uuid4().hex
        payload = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nbatch\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="requests.jsonl"\r\n'
            'Content-Type: application/jsonl\r\n\r\n'
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        return self.request("POST", "/files", payload, f"multipart/form-data; boundary={boundary}")

    def download(self, path, target):
        # A batch can contain GBs of base64. Stream to disk instead of reading the
        # complete result into memory. Interrupted GETs can be collected again.
        return self.request("GET", path, destination=target)


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


@contextmanager
def run_lock(out):
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".image-pipeline.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another process owns this output directory.") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def validate_size(size):
    match = re.fullmatch(r"(\d+)x(\d+)", size)
    if not match:
        raise ValueError("Size must be WIDTHxHEIGHT, for example 3840x2160.")
    w, h = map(int, match.groups())
    if not (w and h and w % 16 == h % 16 == 0 and max(w, h) <= 3840
            and max(w, h) <= 3 * min(w, h) and 655360 <= w * h <= 8294400):
        raise ValueError("Size violates the documented GPT Image 2.5 edge/pixel/aspect limits.")
    return w, h


def read_prompts(path):
    prompts = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not prompts or any(len(p) > 32000 for p in prompts):
        raise ValueError("Supply at least one nonblank prompt; each must be <=32000 characters.")
    return prompts


def image_body(prompt, config):
    return {**config, "prompt": prompt, "n": 1, "output_format": "png"}


def load_state(out, prompts, config):
    path = out / "manifest.json"
    if path.exists():
        state = json.loads(path.read_text())
        if state["config"] != config or state["prompts"] != prompts:
            raise ValueError("Prompts/settings differ from this run; use a new --out directory.")
        for key, item in state["items"].items():
            if item["status"] == "done":
                png = out / f"{int(key):04d}.png"
                if not png.is_file() or hashlib.sha256(png.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError(f"Completed output {png.name} is missing or changed; preserve and inspect it.")
        return state
    # Refuse foreign numbered outputs instead of overwriting or assuming completion.
    if any(out.glob("[0-9]*.png")):
        raise ValueError("Numbered PNGs exist without a manifest; use a new --out directory.")
    return {"schema_version": 1, "run_id": uuid.uuid4().hex, "config": config,
            "prompts": prompts, "items": {}, "batches": []}


def usage_cost(usage, batch):
    """Uncached token-rate estimate; actual billing/credit balance is authoritative."""
    if not isinstance(usage, dict) or not isinstance(usage.get("output_tokens"), int):
        return {"output_tokens": None, "output_cost_usd": None, "estimated_total_usd": None}
    factor = 0.5 if batch else 1
    output = usage["output_tokens"] * 30 * factor / 1_000_000
    details = usage.get("input_tokens_details") or {}
    text, image = details.get("text_tokens"), details.get("image_tokens")
    total = None
    if isinstance(text, int) and isinstance(image, int):
        total = output + (text * 5 + image * 8) * factor / 1_000_000
    return {"output_tokens": usage["output_tokens"], "output_cost_usd": output,
            "estimated_total_usd": total}


def print_usage(state, index):
    item = state["items"][str(index)]
    costs = [v.get("cost", {}).get("output_cost_usd") for v in state["items"].values()
             if v["status"] == "done"]
    known = sum(c for c in costs if c is not None)
    suffix = " + unknown usage" if None in costs else ""
    print(f"{index:04d}.png: output_tokens={item['cost']['output_tokens']}; "
          f"running output cost=${known:.6f}{suffix}; input charges are additional")


def save_image(out, state, index, response, batch, request_id=None):
    # Keep one response spool until the PNG+manifest are durable. This recovers a
    # crash after API success without generating (and paying for) the image again.
    spool = out / f"{index:04d}.response.json"
    if not spool.exists():
        atomic_json(spool, {"response": response, "batch": batch, "request_id": request_id})
    data = response.get("data") or []
    if len(data) != 1 or not data[0].get("b64_json"):
        raise ValueError(f"Image {index} returned no single base64 image; response spool retained.")
    try:
        png = base64.b64decode(data[0]["b64_json"], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError(f"Image {index} returned invalid base64; response spool retained.") from None
    if not png.startswith(PNG) or len(png) < 24 or png[12:16] != b"IHDR":
        raise ValueError(f"Image {index} is not a PNG; response spool retained.")
    dimensions = struct.unpack(">II", png[16:24])
    if dimensions != validate_size(state["config"]["size"]):
        raise ValueError(f"Image {index} dimensions {dimensions} differ from requested size; spool retained.")
    target = out / f"{index:04d}.png"
    if target.exists():
        if target.read_bytes() != png:
            raise ValueError(f"Refusing to overwrite {target}.")
    else:
        with target.open("xb") as handle:
            handle.write(png)
            handle.flush()
            os.fsync(handle.fileno())
    state["items"][str(index)] = {
        "status": "done", "sha256": hashlib.sha256(png).hexdigest(),
        "usage": response.get("usage"), "cost": usage_cost(response.get("usage"), batch),
        "batch": batch, "request_id": request_id,
        "revised_prompt": data[0].get("revised_prompt"),
    }
    atomic_json(out / "manifest.json", state)
    spool.unlink()  # Regenerable base64 duplicate, after verified PNG+receipt.
    print_usage(state, index)


def pending(state, limit):
    indices = [i for i in range(1, len(state["prompts"]) + 1)
               if state["items"].get(str(i), {}).get("status") != "done"]
    return indices[:limit] if limit else indices


def generate(client, out, state, indices):
    for index in indices:
        item = state["items"].get(str(index), {})
        spool = out / f"{index:04d}.response.json"
        if spool.exists():
            saved = json.loads(spool.read_text())
            save_image(out, state, index, **saved)
            continue
        if item.get("status") in {"requesting", "queued"}:
            raise ValueError(f"Image {index} is {item['status']}; inspect its batch/dashboard before retrying in a new run.")
        state["items"][str(index)] = {"status": "requesting"}
        atomic_json(out / "manifest.json", state)
        try:
            response = client.request("POST", "/images/generations",
                                      image_body(state["prompts"][index - 1], state["config"]))
        except APIError as exc:
            if 400 <= exc.status < 500:
                state["items"][str(index)] = {"status": "refused", "error_code": exc.code}
                atomic_json(out / "manifest.json", state)
            raise
        save_image(out, state, index, response, False)


def submit_batch(client, out, state, indices):
    if len(indices) > 50000:
        raise ValueError("A batch allows at most50000 requests; use --limit.")
    for index in indices:
        if state["items"].get(str(index), {}).get("status") in {"requesting", "queued"}:
            raise ValueError(f"Image {index} already has an unresolved request; collect it first.")
    records = [{"custom_id": f"image-{i:04d}", "method": "POST", "url": "/v1/images/generations",
                "body": image_body(state["prompts"][i - 1], state["config"])} for i in indices]
    payload = ("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n").encode()
    if len(payload) > 200_000_000:
        raise ValueError("Batch input exceeds200MB; use --limit.")
    batch = {"indices": indices, "status": "uploading", "input_sha256": hashlib.sha256(payload).hexdigest()}
    state["batches"].append(batch)
    for i in indices:
        state["items"][str(i)] = {"status": "queued"}
    atomic_json(out / "manifest.json", state)
    (out / f"batch-{len(state['batches']):03d}.input.jsonl").write_bytes(payload)
    uploaded = client.upload(payload)
    batch.update(input_file_id=uploaded["id"], status="submitting")
    atomic_json(out / "manifest.json", state)
    result = client.request("POST", "/batches", {
        "input_file_id": uploaded["id"], "endpoint": "/v1/images/generations",
        "completion_window": "24h", "metadata": {"afs_image_run": state["run_id"]}})
    batch.update(id=result["id"], status=result["status"])
    atomic_json(out / "manifest.json", state)
    print(f"Submitted {batch['id']} ({len(indices)} images). Collect later with --collect; no polling process needed.")


def collect_batches(client, out, state):
    failures, waiting = [], False
    for batch in state["batches"]:
        if not batch.get("id"):
            raise ValueError("Batch submission has no saved ID. Inspect the dashboard using input_file_id/run_id; do not resubmit blindly.")
        if batch.get("collected"):
            failures.extend((i, state["items"].get(str(i), {}).get("error", {}).get("code", "batch_error"))
                            for i in batch["indices"]
                            if state["items"].get(str(i), {}).get("status") != "done")
            continue
        result = client.request("GET", "/batches/" + batch["id"])
        batch["status"] = result["status"]
        atomic_json(out / "manifest.json", state)
        print(f"{batch['id']}: {result['status']} {result.get('request_counts', {})}")
        if result["status"] not in TERMINAL:
            waiting = True
            continue
        seen = set()
        for field in ("output_file_id", "error_file_id"):
            if not result.get(field):
                continue
            # Download before consuming so a failed item does not lose partial results.
            raw_path = out / f"{batch['id']}-{field}.jsonl"
            client.download("/files/" + result[field] + "/content", raw_path)
            with raw_path.open() as raw_handle:
                for line in raw_handle:
                    row = json.loads(line)
                    match = re.fullmatch(r"image-(\d+)", row.get("custom_id", ""))
                    if not match or int(match[1]) not in batch["indices"]:
                        raise ValueError("Batch returned an unknown custom_id; raw results retained.")
                    index = int(match[1])
                    if index in seen:
                        raise ValueError("Batch returned a duplicate custom_id; raw results retained.")
                    seen.add(index)
                    response = row.get("response") or {}
                    if response.get("status_code") == 200 and not row.get("error"):
                        if state["items"].get(str(index), {}).get("status") != "done":
                            save_image(out, state, index, response["body"], True, response.get("request_id"))
                    else:
                        if state["items"].get(str(index), {}).get("status") == "done":
                            raise ValueError("Batch error contradicts a completed image; raw results retained.")
                        error = row.get("error") or (response.get("body") or {}).get("error") or {}
                        state["items"][str(index)] = {"status": "failed", "error": error}
                        failures.append((index, error.get("code", "batch_error")))
            atomic_json(out / "manifest.json", state)
            # Images, usage, request IDs and errors are durable. Remove only the
            # downloaded base64 duplicate, not the PNGs or manifest.
            raw_path.unlink()
        missing = set(batch["indices"]) - seen
        if missing:
            failures.extend((i, "missing_batch_result") for i in sorted(missing))
        batch["collected"] = not missing
        batch["errors"] = result.get("errors")
        atomic_json(out / "manifest.json", state)
    if failures:
        raise ValueError(f"Batch errors (no automatic resubmission): {failures}. Successful images are preserved.")
    return 3 if waiting else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompts", nargs="?", type=Path, default=Path("prompts.txt"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--quality", choices=["low", "medium", "high", "xhigh", "max", "auto"], default="max")
    parser.add_argument("--size", default="3840x2160")
    parser.add_argument("--model", choices=[MODEL, MODEL + "-2026-09-08"], default=MODEL)
    parser.add_argument("--background", choices=["opaque", "transparent", "auto"], default="opaque")
    parser.add_argument("--limit", type=int, help="Maximum new images in this invocation")
    parser.add_argument("--batch", action="store_true", help="Submit asynchronous image batch")
    parser.add_argument("--collect", action="store_true", help="Retrieve existing batch status/results; never submit")
    parser.add_argument("--execute", action="store_true", help="Allow API requests (generation/batch submission spends credits)")
    args = parser.parse_args(argv)
    try:
        validate_size(args.size)
        if args.limit is not None and args.limit < 1:
            raise ValueError("--limit must be positive.")
        if args.collect and args.batch:
            raise ValueError("Use --batch to submit or --collect to retrieve, separately.")
        if args.collect:
            state = json.loads((args.out / "manifest.json").read_text())
            prompts, config = state["prompts"], state["config"]
        else:
            prompts = read_prompts(args.prompts)
            config = {"model": args.model, "quality": args.quality, "size": args.size,
                      "background": args.background}
        # Preview reads existing state but creates no files and makes no API calls.
        state = load_state(args.out, prompts, config)
        indices = pending(state, args.limit)
        print(f"{config['model']} | {config['quality']} | {config['size']} | "
              f"{len(indices)} pending | {'batch' if args.batch or args.collect else 'standard'}")
        if not args.execute:
            print("Preview only; no API requests. Add --execute to run. Per-image cost is unknown before usage is returned.")
            return 0
        with run_lock(args.out):
            state = load_state(args.out, prompts, config)
            if args.collect:
                return collect_batches(Client(), args.out, state)
            indices = pending(state, args.limit)
            if not indices:
                print("All images already complete; no requests sent.")
                return 0
            client = Client()
            if args.batch:
                submit_batch(client, args.out, state, indices)
            else:
                generate(client, args.out, state, indices)
        return 0
    except (APIError, ValueError, OSError, KeyError, urllib.error.URLError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("STOP: interrupted; inspect manifest before retrying an unresolved request.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
