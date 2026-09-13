"""Preview-first, loopback-only SSE latency benchmark. No engine mutations/tools.

MIT-licensed. Python 3.10+, standard library only. Reports never retain prompts,
model text, reasoning, tool arguments, credentials or HTTP error bodies.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 4 * 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode()).hexdigest()


def local_url(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme not in ("http", "https") or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ValueError("Use an HTTP(S) loopback URL without credentials/query/fragment")
    host = parsed.hostname
    if host == "localhost":
        host = "127.0.0.1"  # no DNS or proxy escape
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError("Only numeric loopback or localhost endpoints are accepted") from None
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def make_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def load_fixture(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("Fixture too large")
    data = json.loads(raw)
    if data.get("version") != 1 or not isinstance(data.get("cases"), list):
        raise ValueError("Expected version 1 with cases array")
    if not 1 <= len(data["cases"]) <= 32:
        raise ValueError("Use 1–32 fixture cases")
    seen = set()
    for case in data["cases"]:
        name = case.get("id", "")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", name) or name in seen:
            raise ValueError("Use unique lowercase case identifiers")
        seen.add(name)
        req, expect = case.get("request"), case.get("expect")
        if not isinstance(req, dict) or not isinstance(req.get("messages"), list) or not req["messages"]:
            raise ValueError("Each case requires request.messages")
        if not isinstance(expect, dict) or len(expect) != 1:
            raise ValueError("Each case requires one declared expectation")
        key = next(iter(expect))
        if key in ("text_exact", "text_regex"):
            if not isinstance(expect[key], str) or not expect[key]:
                raise ValueError("Text expectation must be nonempty")
            if key == "text_regex":
                re.compile(expect[key])
        elif key == "tool_call":
            call = expect[key]
            if (not isinstance(call, dict) or not isinstance(call.get("name"), str)
                    or not isinstance(call.get("arguments"), dict)):
                raise ValueError("Tool expectation requires name and arguments object")
        else:
            raise ValueError("Unsupported expectation")
    return data


def payload_for(case, model, seed):
    payload = dict(case["request"])
    if payload.get("model", model) != model:
        raise ValueError("Fixture model differs from requested model")
    # Preserve all thinking, tool, sampling and context fields verbatim.
    payload.update(model=model, stream=True, seed=seed)
    return payload


def _text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Unsupported stream text dialect; an adapter is required")
    return value


def parse_stream(response, started, clock=time.perf_counter):
    content, reasoning, calls, usage = "", "", {}, {}
    first_activity = first_content = finish = None
    done, size = False, 0
    for line in response:
        size += len(line)
        if size > MAX_BYTES:
            raise ValueError("Stream exceeds benchmark memory bound")
        if not line.startswith(b"data:"):
            continue
        raw = line[5:].strip()
        if raw == b"[DONE]":
            done = True
            break
        if not raw:
            continue
        event = json.loads(raw)
        if event.get("error"):
            raise ValueError("Server stream reported an error")
        if isinstance(event.get("usage"), dict):
            usage.update(event["usage"])
        for choice in event.get("choices", []):
            if choice.get("index", 0) != 0:
                raise ValueError("Multiple completion choices require a separate adapter")
            delta = choice.get("delta") or {}
            text = _text(delta.get("content"))
            thought = _text(delta.get("reasoning_content")) + _text(delta.get("reasoning"))
            tool_parts = delta.get("tool_calls") or []
            now = clock() - started
            if (text or thought or tool_parts) and first_activity is None:
                first_activity = now
            if text and first_content is None:
                first_content = now
            content += text
            reasoning += thought
            for part in tool_parts:
                index = part.get("index", 0)
                if type(index) is not int or not 0 <= index < 64:
                    raise ValueError("Invalid tool stream index")
                call = calls.setdefault(index, {"name": "", "arguments": ""})
                fn = part.get("function") or {}
                call["name"] += _text(fn.get("name"))
                call["arguments"] += _text(fn.get("arguments"))
            if choice.get("finish_reason") is not None:
                finish = choice["finish_reason"]
    return {"content": content, "reasoning": reasoning, "calls": calls, "usage": usage,
            "done": done, "finish": finish, "seconds": clock() - started,
            "first_activity_s": first_activity, "first_content_s": first_content}


def screen(result, expect):
    if not result["done"] or result["finish"] not in ("stop", "tool_calls"):
        return False
    if "tool_call" in expect:
        if result["finish"] != "tool_calls" or len(result["calls"]) != 1:
            return False
        actual = next(iter(result["calls"].values()))
        try:
            return (actual["name"] == expect["tool_call"]["name"]
                    and json.loads(actual["arguments"]) == expect["tool_call"]["arguments"])
        except (ValueError, TypeError):
            return False
    if result["calls"] or result["finish"] != "stop":
        return False
    text = result["content"].strip()
    return (text == expect["text_exact"] if "text_exact" in expect
            else re.fullmatch(expect["text_regex"], text, flags=re.DOTALL) is not None)


def clean_result(result, expect):
    tokens = result["usage"].get("completion_tokens")
    tokens = tokens if type(tokens) is int and tokens > 0 else None
    seconds = result["seconds"]
    return {"valid": screen(result, expect), "seconds": seconds,
            "first_activity_s": result["first_activity_s"], "first_content_s": result["first_content_s"],
            "completion_tokens": tokens, "end_to_end_tps": tokens / seconds if tokens and seconds > 0 else None,
            "thinking_emitted": bool(result["reasoning"]), "finish_reason": result["finish"],
            "output_sha256": digest([result["content"], result["reasoning"], result["calls"]]),
            "tools_executed": False}


def read_status(opener, url, headers, timeout):
    with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Status exceeds memory bound")
    status = json.loads(raw)
    fields = ("active_requests", "waiting_requests", "models_loading")
    if any(type(status.get(k)) is not int for k in fields):
        raise ValueError("Unrecognized idle status; add a tested runtime adapter")
    if any(status[k] != 0 for k in fields):
        raise RuntimeError("Local service is busy; stop the benchmark")
    count = status.get("total_requests")
    return count if type(count) is int and count >= 0 else None


def run(args, opener=None):
    fixture = load_fixture(args.fixture)
    endpoint = local_url(args.base_url) + "/chat/completions"
    status_url = local_url(args.status_url) if args.status_url else None
    if not args.model.strip():
        raise ValueError("Model identifier required")
    for case in fixture["cases"]:
        payload_for(case, args.model, args.seed)
    report = {"version": 1, "label": args.label, "model": args.model,
              "fixture_sha256": digest(fixture), "warmups": args.warmups, "repeats": args.repeats,
              "seed": args.seed, "preview_only": not args.run, "complete": False, "rows": []}
    identity_path = getattr(args, "identity", None)
    if identity_path:
        identity = Path(identity_path).read_bytes()
        if len(identity) > MAX_BYTES:
            raise ValueError("Identity document too large")
        report["identity_sha256"] = digest(json.loads(identity))
    if not args.run:
        report["cases"] = [c["id"] for c in fixture["cases"]]
        return report
    if not args.confirm_idle:
        raise ValueError("Live runs require --confirm-idle and an exclusive test window")
    opener = opener or make_opener()
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if args.api_key_env:
        key = os.environ.get(args.api_key_env)
        if not key:
            raise ValueError("The specified local API-key environment variable is unset")
        headers["Authorization"] = "Bearer " + key
    for case in fixture["cases"]:
        for stage, count in (("warmup", args.warmups), ("warm", args.repeats)):
            for index in range(count):
                payload = payload_for(case, args.model, args.seed + index)
                row = {"case": case["id"], "stage": stage, "trial": index + 1,
                       "seed": args.seed + index, "request_sha256": digest(payload),
                       "valid": False, "isolation": "unknown"}
                report["rows"].append(row)
                try:
                    before = read_status(opener, status_url, headers, args.timeout) if status_url else None
                    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers=headers)
                    started = time.perf_counter()
                    with opener.open(req, timeout=args.timeout) as response:
                        result = parse_stream(response, started)
                    row.update(clean_result(result, case["expect"]))
                    after = read_status(opener, status_url, headers, args.timeout) if status_url else None
                    if before is not None and after is not None:
                        row["isolation"] = "counter_verified" if after - before == 1 else "contaminated"
                        row["valid"] = row["valid"] and row["isolation"] == "counter_verified"
                except Exception as error:
                    # Deliberately do not print error messages/HTTP bodies or private URLs.
                    row.update(valid=False, error_type=type(error).__name__)
                    return report
    report["complete"] = True
    return report


def write_new_report(path, report):
    encoded = json.dumps(report, indent=2, ensure_ascii=False).encode() + b"\n"
    # Never overwrite an existing baseline. Keep local measurements private by default.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(encoded)


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--identity", type=Path, help="Private fixed hardware/model/precision contract JSON; only its hash is exported")
    parser.add_argument("--label", required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    parser.add_argument("--status-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.label):
        parser.error("Use a short lowercase label")
    if not 0 <= args.warmups <= 10 or not 1 <= args.repeats <= 20 or not 0 <= args.seed < 2**31 - 20:
        parser.error("Use 0–10 warm-ups, 1–20 repeats, and a bounded nonnegative seed")
    if not 1 <= args.timeout <= 3600:
        parser.error("Use a 1–3600 second I/O timeout")
    if args.run and (not args.confirm_idle or not args.out):
        parser.error("Live run requires --confirm-idle and a new --out path")
    if args.out and args.out.exists():
        parser.error("Output already exists; refusing to overwrite")
    return args


if __name__ == "__main__":
    try:
        args = arguments()
        report = run(args)
        if args.out:
            write_new_report(args.out, report)
        print(json.dumps(report, ensure_ascii=False))
        raise SystemExit(0 if report["preview_only"] or (report["complete"] and all(r["valid"] for r in report["rows"])) else 2)
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"error_type": type(error).__name__, "detail": "No private input or error body exported; inspect the fixture and local endpoint."}))
        raise SystemExit(2)
