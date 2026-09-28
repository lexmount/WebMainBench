import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.dataset_corrections import apply_corrections, correct_jsonl


def sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_sha256(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def fixture(tmp_path):
    replacement = "# Visible article\n\nOne canonical copy.\n"
    (tmp_path / "replacement.md").write_text(replacement, encoding="utf-8")
    original = "# Visible article\n\n```\nOne canonical copy.\n```\n\nOne canonical copy.\n"
    manifest = {
        "schema_version": 1,
        "corrections": [
            {
                "track_id": "duplicate-editor-buffer",
                "url": "https://example.test/article",
                "original_groundtruth_sha256": sha256(original),
                "replacement_file": "replacement.md",
                "replacement_sha256": sha256(replacement),
                "html_sha256": sha256("<article>One canonical copy.</article>"),
            }
        ],
    }
    manifest_path = tmp_path / "corrections.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    row = {
        "track_id": "duplicate-editor-buffer",
        "url": "https://example.test/article",
        "html": "<article>One canonical copy.</article>",
        "groundtruth_content": original,
    }
    return row, replacement, manifest_path


class DatasetCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_correction_replaces_only_the_bound_reference(self):
        row, replacement, manifest_path = fixture(self.path)
        untouched = {"track_id": "other", "groundtruth_content": "Other"}
        result = apply_corrections([row, untouched], manifest_path)
        self.assertEqual(result[0]["groundtruth_content"], replacement)
        self.assertEqual(result[1], untouched)

    def test_correction_rejects_changed_source_or_reference(self):
        for field in ["url", "html", "groundtruth_content"]:
            with self.subTest(field=field):
                row, _, manifest_path = fixture(self.path)
                row[field] += " changed"
                with self.assertRaises(ValueError):
                    apply_corrections([row], manifest_path)

    def test_jsonl_correction_preserves_population(self):
        row, replacement, manifest_path = fixture(self.path)
        input_path = self.path / "input.jsonl"
        output_path = self.path / "output.jsonl"
        input_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        self.assertEqual(correct_jsonl(input_path, output_path, manifest_path), 1)
        corrected = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(corrected["groundtruth_content"], replacement)

    def test_metadata_correction_is_hash_bound(self):
        meta = {"code": ["interline"], "language": "en"}
        manifest = {
            "schema_version": 1,
            "corrections": [{
                "track_id": "wrong-code-label",
                "url": "https://example.test/plain",
                "original_meta_sha256": json_sha256(meta),
                "replacement_meta": {"code": [], "language": "en"},
            }],
        }
        path = self.path / "meta.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        row = {
            "track_id": "wrong-code-label",
            "url": "https://example.test/plain",
            "groundtruth_content": "Plain text",
            "meta": meta,
        }
        corrected = apply_corrections([row], path)[0]
        self.assertEqual(corrected["meta"]["code"], [])
        row["meta"]["code"] = ["inline"]
        with self.assertRaises(ValueError):
            apply_corrections([row], path)

    def test_repository_manifest_and_replacement_are_bound(self):
        root = Path(__file__).parent.parent
        manifest_path = root / "data/corrections/WebMainBench_545.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertGreaterEqual(len(manifest["corrections"]), 1)
        correction = next(
            item for item in manifest["corrections"]
            if item["track_id"] == "f080fbec-9ec6-43c6-9bc6-0846c70cbe8d"
        )
        replacement = (manifest_path.parent / correction["replacement_file"]).read_text(
            encoding="utf-8"
        )
        self.assertEqual(sha256(replacement), correction["replacement_sha256"])
        self.assertFalse(replacement.lstrip().startswith("```"))
        self.assertEqual(replacement.count("# 南生运营的理念（商用）"), 1)


if __name__ == "__main__":
    unittest.main()
