"""Offline billing, recovery and Batch result-mapping tests. No paid requests."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import struct
import tempfile
import unittest
import urllib.error
import zlib
from pathlib import Path
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "generate_images", Path(__file__).parents[1] / "scripts" / "generate_images.py")
images = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(images)


def png_bytes(value=0):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    header = struct.pack(">IIBBBBB", 1024, 1024, 8, 0, 0, 0, 0)
    pixels = (b"\0" + bytes([value]) * 1024) * 1024
    return images.PNG + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


def response(value=0, usage=True):
    data = {"data": [{"b64_json": base64.b64encode(png_bytes(value)).decode()}]}
    if usage:
        data["usage"] = {"output_tokens": 1000, "input_tokens": 100,
                         "input_tokens_details": {"text_tokens": 100, "image_tokens": 0}}
    return data


class ImagePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.config = {"model": images.MODEL, "quality": "max", "size": "1024x1024", "background": "opaque"}
        self.state = images.load_state(self.out, ["one", "two"], self.config)
        self.out.mkdir()

    def test_default_preview_needs_no_key_and_creates_no_output(self):
        prompts = self.root / "prompts.txt"
        prompts.write_text("one\n\ntwo\n")
        new_out = self.root / "preview"
        with patch.dict(os.environ, {}, clear=True), patch.object(images.Client, "request") as call:
            self.assertEqual(images.main([str(prompts), "--out", str(new_out)]), 0)
        call.assert_not_called()
        self.assertFalse(new_out.exists())

    def test_exact_requested_body_and_sizes(self):
        self.assertEqual(images.validate_size("3840x2160"), (3840, 2160))
        body = images.image_body("one", self.config)
        self.assertEqual((body["model"], body["quality"], body["n"], body["output_format"]),
                         (images.MODEL, "max", 1, "png"))
        for size in ("1672x941", "0x1024", "4096x2160", "512x512", "3840x1024"):
            with self.assertRaises(ValueError):
                images.validate_size(size)

    def test_blank_bom_and_unicode_prompt_input(self):
        path = self.root / "prompts.txt"
        path.write_text("\ufeffLyra 海\n\nsecond\n", encoding="utf-8")
        self.assertEqual(images.read_prompts(path), ["Lyra 海", "second"])

    def test_reference_png_uses_edits_endpoint_and_pins_source(self):
        path = self.root / "map.png"
        path.write_bytes(png_bytes())
        self.config["references"] = images.references([path])
        body = images.image_body("island", self.config)
        self.assertEqual(images.endpoint(self.config), "/images/edits")
        self.assertNotIn("references", body)
        self.assertEqual(base64.b64decode(body["images"][0]["image_url"].split(",")[1]), png_bytes())
        path.write_bytes(png_bytes(1))
        with self.assertRaisesRegex(ValueError, "changed"):
            images.image_body("island", self.config)

    def test_batch_reference_payload_routes_to_edits(self):
        path = self.root / "map.png"
        path.write_bytes(png_bytes())
        self.config["references"] = images.references([path])
        client = Mock()
        client.upload.return_value = {"id": "file-input"}
        client.request.return_value = {"id": "batch-edit", "status": "validating"}
        images.submit_batch(client, self.out, self.state, [1])
        row = json.loads(client.upload.call_args.args[0].decode())
        self.assertEqual(row["url"], "/v1/images/edits")
        self.assertEqual(client.request.call_args.args[2]["endpoint"], "/v1/images/edits")

    def test_bad_reference_is_refused(self):
        path = self.root / "not-a-map.png"
        path.write_bytes(b"not PNG")
        with self.assertRaisesRegex(ValueError, "PNG"):
            images.references([path])

    def test_rate_limit_backoff_and_credit_stop(self):
        limit = urllib.error.HTTPError(images.API, 429, "rate", {}, io.BytesIO(
            b'{"error":{"code":"rate_limit_exceeded","message":"slow"}}'))
        ok = Mock()
        ok.__enter__ = Mock(return_value=ok)
        ok.__exit__ = Mock(return_value=False)
        ok.read.return_value = b'{"ok":true}'
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), \
             patch.object(images.urllib.request, "urlopen", side_effect=[limit, ok]) as call, \
             patch.object(images.time, "sleep") as sleep:
            self.assertTrue(images.Client().request("POST", "/images/generations", {})["ok"])
            self.assertEqual(call.call_count, 2)
            sleep.assert_called_once()
        credit = urllib.error.HTTPError(images.API, 429, "credits", {}, io.BytesIO(
            b'{"error":{"code":"credit_balance_exhausted"}}'))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), \
             patch.object(images.urllib.request, "urlopen", side_effect=credit) as call, \
             patch.object(images.time, "sleep") as sleep:
            with self.assertRaises(images.APIError) as exc:
                images.Client().request("POST", "/images/generations", {})
            self.assertEqual(exc.exception.code, "credit_balance_exhausted")
            self.assertEqual(call.call_count, 1)
            sleep.assert_not_called()

    def test_network_failure_not_replayed_and_uncertainty_persisted(self):
        client = Mock()
        client.request.side_effect = urllib.error.URLError("timed out")
        with self.assertRaises(urllib.error.URLError):
            images.generate(client, self.out, self.state, [1])
        state = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual(state["items"]["1"]["status"], "requesting")
        with self.assertRaisesRegex(ValueError, "requesting"):
            images.generate(client, self.out, state, [1])
        self.assertEqual(client.request.call_count, 1)

    def test_download_streams_to_file_with_org_headers(self):
        payload = b'{"custom_id":"image-0001"}\n' * 100
        stream = io.BytesIO(payload)
        target = self.out / "download.jsonl"
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_ORG_ID": "org-test",
                                     "OPENAI_PROJECT_ID": "proj-test"}), \
             patch.object(images.urllib.request, "urlopen", return_value=stream) as call:
            images.Client().download("/files/test/content", target)
        self.assertEqual(target.read_bytes(), payload)
        request = call.call_args.args[0]
        self.assertEqual(request.get_header("Openai-organization"), "org-test")
        self.assertEqual(request.get_header("Openai-project"), "proj-test")
        self.assertFalse(target.with_suffix(".jsonl.part").exists())

    def test_success_must_not_be_overwritten_by_batch_error(self):
        client = self.submit()
        images.save_image(self.out, self.state, 1, response(), True)
        client.request.return_value = {"status": "completed", "output_file_id": "good"}
        row = {"custom_id": "image-0001", "error": {"code": "batch_error"}}
        client.download.side_effect = lambda path, target: target.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, "completed image"):
            images.collect_batches(client, self.out, self.state)

    def test_png_receipt_resume_and_actual_cost(self):
        images.save_image(self.out, self.state, 1, response(), False)
        item = self.state["items"]["1"]
        self.assertEqual(item["cost"]["output_tokens"], 1000)
        self.assertAlmostEqual(item["cost"]["output_cost_usd"], 0.03)
        self.assertAlmostEqual(item["cost"]["estimated_total_usd"], 0.0305)
        self.assertFalse((self.out / "0001.response.json").exists())
        state = images.load_state(self.out, ["one", "two"], self.config)
        self.assertEqual(images.pending(state, None), [2])
        self.assertAlmostEqual(images.usage_cost(response()["usage"], True)["output_cost_usd"], 0.015)

    def test_missing_usage_is_unknown_not_zero(self):
        images.save_image(self.out, self.state, 1, response(usage=False), False)
        self.assertIsNone(self.state["items"]["1"]["cost"]["output_cost_usd"])

    def test_spooled_success_recovers_without_another_request(self):
        images.atomic_json(self.out / "0001.response.json",
                           {"response": response(), "batch": False, "request_id": "req-1"})
        self.state["items"]["1"] = {"status": "requesting"}
        client = Mock()
        images.generate(client, self.out, self.state, [1])
        client.request.assert_not_called()
        self.assertEqual(self.state["items"]["1"]["status"], "done")

    def test_changed_prompts_and_modified_output_refused(self):
        images.save_image(self.out, self.state, 1, response(), False)
        with self.assertRaisesRegex(ValueError, "differ"):
            images.load_state(self.out, ["changed", "two"], self.config)
        (self.out / "0001.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            images.load_state(self.out, ["one", "two"], self.config)

    def test_foreign_numbered_output_refused(self):
        (self.out / "0001.png").write_bytes(b"foreign")
        with self.assertRaisesRegex(ValueError, "without a manifest"):
            images.load_state(self.out, ["one", "two"], self.config)

    def test_dimension_mismatch_keeps_response_and_does_not_write_png(self):
        self.state["config"]["size"] = "3840x2160"
        with self.assertRaisesRegex(ValueError, "dimensions"):
            images.save_image(self.out, self.state, 1, response(), False)
        self.assertTrue((self.out / "0001.response.json").exists())
        self.assertFalse((self.out / "0001.png").exists())

    def submit(self):
        client = Mock()
        client.upload.return_value = {"id": "file-input"}
        client.request.return_value = {"id": "batch-test", "status": "validating"}
        images.submit_batch(client, self.out, self.state, [1, 2])
        payload = client.upload.call_args.args[0].decode().splitlines()
        self.assertEqual([json.loads(x)["custom_id"] for x in payload], ["image-0001", "image-0002"])
        self.assertEqual(client.request.call_args.args[2]["endpoint"], "/v1/images/generations")
        self.assertEqual(self.state["batches"][0]["id"], "batch-test")
        return client

    def test_batch_submission_is_persisted_and_not_repeated(self):
        client = self.submit()
        with self.assertRaisesRegex(ValueError, "unresolved"):
            images.submit_batch(client, self.out, self.state, [1, 2])
        self.assertEqual(client.upload.call_count, 1)

    def test_unordered_batch_results_match_numbered_prompts(self):
        client = self.submit()
        client.request.return_value = {"status": "completed", "output_file_id": "file-output"}
        rows = [{"custom_id": f"image-{i:04d}", "response": {
            "status_code": 200, "request_id": f"req-{i}", "body": response(i)}} for i in (2, 1)]
        client.download.side_effect = lambda path, target: target.write_text(
            "\n".join(json.dumps(row) for row in rows))
        self.assertEqual(images.collect_batches(client, self.out, self.state), 0)
        self.assertEqual((self.out / "0001.png").read_bytes(), png_bytes(1))
        self.assertEqual((self.out / "0002.png").read_bytes(), png_bytes(2))
        self.assertTrue(self.state["batches"][0]["collected"])
        self.assertFalse((self.out / "batch-test-output_file_id.jsonl").exists())
        calls = client.request.call_count
        images.collect_batches(client, self.out, self.state)
        self.assertEqual(client.request.call_count, calls)

    def test_partial_batch_preserves_success_and_surfaces_credit_error(self):
        client = self.submit()
        client.request.return_value = {"status": "expired", "output_file_id": "good", "error_file_id": "bad"}
        rows = {"/files/good/content": {"custom_id": "image-0001", "response": {
            "status_code": 200, "body": response()}}, "/files/bad/content": {
                "custom_id": "image-0002", "error": {"code": "credit_balance_exhausted"}}}
        client.download.side_effect = lambda path, target: target.write_text(json.dumps(rows[path]))
        with self.assertRaisesRegex(ValueError, "credit_balance_exhausted"):
            images.collect_batches(client, self.out, self.state)
        self.assertTrue((self.out / "0001.png").exists())
        self.assertEqual(self.state["items"]["2"]["status"], "failed")
        self.assertEqual(client.upload.call_count, 1)
        with self.assertRaisesRegex(ValueError, "credit_balance_exhausted"):
            images.collect_batches(client, self.out, self.state)

    def test_running_batch_returns_pending_without_polling(self):
        client = self.submit()
        client.request.return_value = {"status": "in_progress"}
        self.assertEqual(images.collect_batches(client, self.out, self.state), 3)
        client.download.assert_not_called()

    def test_output_directory_exclusive_lock(self):
        with images.run_lock(self.out):
            with self.assertRaisesRegex(ValueError, "Another process"):
                with images.run_lock(self.out):
                    self.fail("second writer admitted")


if __name__ == "__main__":
    unittest.main()
