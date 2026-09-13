"""Offline behavior tests; fake transports only, never a serving model."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.request

import bench
import compare


def fixture():
    return {"version": 1, "cases": [{"id": "math", "request": {
        "messages": [{"role": "user", "content": "PRIVATE_PROMPT"}],
        "tools": [{"type": "function", "function": {"name": "terminal"}}],
        "temperature": 1.0, "top_p": .95,
        "chat_template_kwargs": {"enable_thinking": True, "preserve_thinking": True},
    }, "expect": {"text_exact": "3961"}}]}


def stream(text="3961", finish="stop", done=True, usage=True, calls=None):
    events = [
        {"choices": [{"index": 0, "delta": {"reasoning_content": "PRIVATE_REASONING"}}]},
        {"choices": [{"index": 0, "delta": {"content": text, **({"tool_calls": calls} if calls else {})}}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
    ]
    if usage:
        events.append({"choices": [], "usage": {"completion_tokens": 20}})
    raw = b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)
    return raw + (b"data: [DONE]\n\n" if done else b"")


class FakeOpener:
    def __init__(self, body=None, status=None):
        self.body = body or stream()
        self.requests = []
        self.posts = 0
        self.status = status

    def open(self, request, timeout=None):
        self.requests.append(request)
        if request.data is None:
            value = self.status(self.posts) if self.status else {
                "active_requests": 0, "waiting_requests": 0, "models_loading": 0,
                "total_requests": self.posts,
            }
            return io.BytesIO(json.dumps(value).encode())
        self.posts += 1
        return io.BytesIO(self.body)


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "private.json"
        self.path.write_text(json.dumps(fixture()))

    def args(self, **changes):
        args = dict(fixture=self.path, base_url="http://127.0.0.1:12345/v1", model="local-model",
                    label="test", warmups=1, repeats=3, seed=7, run=True, confirm_idle=True,
                    status_url=None, api_key_env=None, timeout=5)
        args.update(changes)
        return SimpleNamespace(**args)

    def test_loopback_urls_only_and_no_credential_query(self):
        self.assertEqual(bench.local_url("http://localhost:1234/v1/"), "http://127.0.0.1:1234/v1")
        self.assertEqual(bench.local_url("http://[::1]:1234/v1"), "http://[::1]:1234/v1")
        for url in ("https://example.com/v1", "http://192.168.1.2/v1", "file:///tmp/x",
                    "http://127.0.0.1@evil.example/v1", "http://key@localhost/v1",
                    "http://localhost/v1?key=SECRET", "http://localhost/v1#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                bench.local_url(url)

    def test_redirects_and_environment_proxies_not_used(self):
        self.assertIsNone(bench.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))
        with patch.dict(os.environ, {"http_proxy": "http://example.com:9999"}):
            opener = bench.make_opener()
        self.assertFalse(any(isinstance(h, urllib.request.ProxyHandler) and h.proxies for h in opener.handlers))

    def test_preview_never_opens_or_reads_key(self):
        transport = FakeOpener()
        report = bench.run(self.args(run=False, api_key_env="NONEXISTENT_KEY"), transport)
        self.assertTrue(report["preview_only"])
        self.assertEqual(transport.requests, [])
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_explicit_live_confirmation_required(self):
        transport = FakeOpener()
        with self.assertRaises(ValueError):
            bench.run(self.args(confirm_idle=False), transport)
        self.assertEqual(transport.requests, [])

    def test_model_mismatch_refuses_before_network(self):
        with self.assertRaises(ValueError):
            bench.payload_for({"request": {"model": "different"}}, "local-model", 7)

    def test_payload_preserves_thinking_sampling_full_schemas_and_input(self):
        original = fixture()["cases"][0]
        snapshot = copy.deepcopy(original)
        payload = bench.payload_for(original, "local-model", 7)
        for key in ("messages", "tools", "temperature", "top_p", "chat_template_kwargs"):
            self.assertEqual(payload[key], original["request"][key])
        self.assertEqual(original, snapshot)

    def test_complete_run_private_outputs_and_scheduled_warmups(self):
        transport = FakeOpener()
        report = bench.run(self.args(status_url="http://127.0.0.1:12345/api/status"), transport)
        self.assertEqual(transport.posts, 4)
        self.assertEqual([r["stage"] for r in report["rows"]], ["warmup", "warm", "warm", "warm"])
        self.assertEqual([r["seed"] for r in report["rows"]], [7, 7, 8, 9])
        self.assertTrue(all(r["valid"] and r["isolation"] == "counter_verified" for r in report["rows"]))
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertTrue(all(r["thinking_emitted"] for r in report["rows"]))

    def test_missing_usage_never_invents_token_rate(self):
        report = bench.run(self.args(), FakeOpener(stream(usage=False)))
        self.assertTrue(report["rows"][0]["valid"])
        self.assertIsNone(report["rows"][0]["completion_tokens"])
        self.assertIsNone(report["rows"][0]["end_to_end_tps"])
        self.assertEqual(report["rows"][0]["isolation"], "unknown")

    def test_incomplete_truncated_wrong_answer_all_invalid(self):
        for body in (stream(done=False), stream(finish="length"), stream(text="3962")):
            with self.subTest(body=body[-50:]):
                report = bench.run(self.args(), FakeOpener(body))
                self.assertTrue(all(not r["valid"] for r in report["rows"]))

    def test_structured_tool_call_is_checked_never_executed(self):
        calls = [{"index": 0, "function": {"name": "terminal", "arguments": '{"command":"PRIVATE_TOOL"}'}}]
        result = bench.parse_stream(io.BytesIO(stream(text="", finish="tool_calls", calls=calls)), 0, clock=lambda: 1)
        expected = {"tool_call": {"name": "terminal", "arguments": {"command": "PRIVATE_TOOL"}}}
        clean = bench.clean_result(result, expected)
        self.assertTrue(clean["valid"])
        self.assertFalse(clean["tools_executed"])
        self.assertNotIn("PRIVATE", json.dumps(clean))
        self.assertFalse(bench.screen(result, {"text_exact": "3961"}))

    def test_busy_preflight_stops_without_submission(self):
        transport = FakeOpener(status=lambda n: {"active_requests": 1, "waiting_requests": 0, "models_loading": 0})
        report = bench.run(self.args(status_url="http://127.0.0.1:1/status"), transport)
        self.assertEqual(transport.posts, 0)
        self.assertFalse(report["complete"])
        self.assertFalse(report["rows"][0]["valid"])

    def test_overlap_is_invalid_not_a_fast_success(self):
        transport = FakeOpener(status=lambda n: {"active_requests": 0, "waiting_requests": 0,
                                                 "models_loading": 0, "total_requests": n * 2})
        report = bench.run(self.args(status_url="http://127.0.0.1:1/status"), transport)
        self.assertTrue(all(r["isolation"] == "contaminated" and not r["valid"] for r in report["rows"]))

    def test_transport_error_does_not_export_private_detail(self):
        class Broken:
            def open(self, *args, **kwargs):
                raise ValueError("PRIVATE_PAYLOAD_CREDENTIAL_ERROR")
        report = bench.run(self.args(), Broken())
        self.assertFalse(report["complete"])
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_output_is_new_private_file_never_overwritten(self):
        output = Path(self.directory.name) / "out.json"
        bench.write_new_report(output, {"ok": True})
        with self.assertRaises(FileExistsError):
            bench.write_new_report(output, {"overwritten": True})
        self.assertEqual(json.loads(output.read_text()), {"ok": True})
        if os.name == "posix":
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_private_identity_is_fingerprinted_not_exported(self):
        identity = Path(self.directory.name) / "identity.json"
        identity.write_text(json.dumps({"weights_revision": "PRIVATE_IDENTITY"}))
        report = bench.run(self.args(run=False, identity=identity), FakeOpener())
        self.assertEqual(len(report["identity_sha256"]), 64)
        self.assertNotIn("PRIVATE", json.dumps(report))


def comparison_report(seconds=2):
    return {"version": 1, "preview_only": False, "complete": True, "model": "test",
            "fixture_sha256": "fixture", "warmups": 0, "repeats": 3, "seed": 1,
            "rows": [{"case": "case", "stage": "warm", "trial": i, "seed": i,
                      "request_sha256": f"request-{i}", "valid": True, "seconds": seconds,
                      "isolation": "counter_verified"} for i in (1, 2, 3)]}


class ComparisonTests(unittest.TestCase):
    def test_two_pairs_show_individual_gains_without_universal_claim(self):
        result = compare.compare([(comparison_report(2), comparison_report(1)),
                                  (comparison_report(2.2), comparison_report(1.1))])
        self.assertTrue(result["two_pairs_three_repeats_minimum"])
        self.assertEqual(result["cases"]["case"]["pairs"][0]["time_reduction_percent"], 50)
        self.assertIn("not established", result["quality_caveat"])

    def test_copied_or_renamed_reports_are_not_new_evidence(self):
        first = (comparison_report(2), comparison_report(1))
        for renamed in (False, True):
            second = copy.deepcopy(first)
            if renamed:
                for report in second:
                    report["label"] = "a-new-label-is-not-a-new-run"
            with self.subTest(renamed=renamed), self.assertRaises(ValueError):
                compare.compare([first, second])

    def test_baseline_cannot_be_reused_across_pairs(self):
        first = (comparison_report(2), comparison_report(1))
        second = (copy.deepcopy(first[0]), comparison_report(.9))
        with self.assertRaises(ValueError):
            compare.compare([first, second])

    def test_same_report_cannot_be_both_before_and_after(self):
        report = comparison_report()
        with self.assertRaises(ValueError):
            compare.compare([(report, copy.deepcopy(report))])

    def test_single_pair_cases_do_not_count_as_repeated_evidence(self):
        first = (comparison_report(2), comparison_report(1))
        second = (comparison_report(4), comparison_report(3))
        for report in second:
            report["fixture_sha256"] = "other-fixture"
            for row in report["rows"]:
                row["case"] = "other-case"
        result = compare.compare([first, second])
        self.assertFalse(result["two_pairs_three_repeats_minimum"])
        self.assertEqual(set(result["cases"]), {"case", "other-case"})

    def test_declared_warmups_must_be_present_once(self):
        first = (comparison_report(2), comparison_report(1))
        for report in first:
            report["warmups"] = 3
            warmups = copy.deepcopy(report["rows"])
            for row in warmups:
                row["stage"] = "warmup"
            report["rows"] = warmups + report["rows"]
        self.assertEqual(len(compare.compare([first])["cases"]), 1)
        for mode in ("missing-one", "missing-all", "duplicate"):
            pair = copy.deepcopy(first)
            for report in pair:
                if mode == "missing-one":
                    report["rows"].pop(0)
                elif mode == "missing-all":
                    report["rows"] = report["rows"][3:]
                else:
                    report["rows"].append(copy.deepcopy(report["rows"][0]))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                compare.compare([pair])

    def test_trial_stage_and_indices_must_match_declared_schedule(self):
        for field, value in (("stage", "typo"), ("trial", 99), ("trial", True)):
            pair = (comparison_report(2), comparison_report(1))
            for report in pair:
                report["rows"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                compare.compare([pair])

    def test_regression_visible(self):
        result = compare.compare([(comparison_report(1), comparison_report(2))])
        self.assertFalse(result["cases"]["case"]["improved_in_every_pair"])
        self.assertFalse(result["two_pairs_three_repeats_minimum"])

    def test_fixture_model_settings_and_request_mismatches_rejected(self):
        for field in ("fixture_sha256", "model", "seed", "repeats", "warmups"):
            a, b = comparison_report(), comparison_report()
            b[field] = "different"
            with self.subTest(field=field), self.assertRaises(ValueError):
                compare.compare([(a, b)])
        a, b = comparison_report(), comparison_report()
        b["rows"][0]["request_sha256"] = "different"
        with self.assertRaises(ValueError):
            compare.compare([(a, b)])

    def test_failed_trials_and_failed_warmups_not_dropped(self):
        for stage in ("warm", "warmup"):
            a, b = comparison_report(), comparison_report()
            b["rows"].append({"stage": stage, "valid": False})
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                compare.compare([(a, b)])

    def test_missing_and_duplicate_repetitions_rejected(self):
        for mode in ("missing", "duplicate"):
            a, b = comparison_report(), comparison_report()
            if mode == "missing":
                b["rows"].pop()
            else:
                b["rows"].append(b["rows"][0])
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                compare.compare([(a, b)])

    def test_unknown_isolation_is_not_verified(self):
        a, b = comparison_report(), comparison_report()
        a["rows"][0]["isolation"] = "unknown"
        result = compare.compare([(a, b)])
        self.assertFalse(result["measured_trial_overlap_counter_verified"])

    def test_identity_mismatch_or_missing_fingerprint_rejected(self):
        a, b = comparison_report(), comparison_report()
        b["identity_sha256"] = "different-hardware-or-model"
        with self.assertRaises(ValueError):
            compare.compare([(a, b)])
        a, b = comparison_report(), comparison_report()
        del a["rows"][0]["request_sha256"]
        del b["rows"][0]["request_sha256"]
        with self.assertRaises(ValueError):
            compare.compare([(a, b)])


class LoopbackIntegrationTests(unittest.TestCase):
    def test_real_http_transport_against_temporary_fake_server(self):
        """Only an ephemeral local fixture, never the user's inference server."""
        class Handler(BaseHTTPRequestHandler):
            posts = 0

            def log_message(self, *args):
                pass

            def do_GET(self):
                data = json.dumps({"active_requests": 0, "waiting_requests": 0,
                                   "models_loading": 0, "total_requests": Handler.posts}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if payload["model"] != "fixture-model" or not payload["chat_template_kwargs"]["enable_thinking"]:
                    self.send_error(400)
                    return
                Handler.posts += 1
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(stream())

        with HTTPServer(("127.0.0.1", 0), Handler) as server, tempfile.TemporaryDirectory() as directory:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                private = Path(directory) / "fixture.json"
                private.write_text(json.dumps(fixture()))
                base = f"http://127.0.0.1:{server.server_port}"
                args = SimpleNamespace(fixture=private, base_url=base + "/v1", model="fixture-model",
                                       label="http-test", warmups=1, repeats=3, seed=1, run=True,
                                       confirm_idle=True, status_url=base + "/status", api_key_env=None, timeout=3)
                report = bench.run(args)
                self.assertTrue(report["complete"])
                self.assertEqual(Handler.posts, 4)
                self.assertTrue(all(r["valid"] and r["isolation"] == "counter_verified" for r in report["rows"]))
            finally:
                server.shutdown()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
