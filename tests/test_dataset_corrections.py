import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.dataset_corrections import apply_corrections, correct_jsonl
from scripts.dataset_corrections import _DECISION_CONTRACTS


def sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_sha256(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def fixture(tmp_path):
    replacement = "# Visible article\n\nOne canonical copy.\n"
    (tmp_path / "replacement.md").write_text(replacement, encoding="utf-8")
    original = "# Visible article\n\n```\nOne canonical copy.\n```\n\nOne canonical copy.\n"
    row = {
        "track_id": "duplicate-editor-buffer",
        "url": "https://example.test/article",
        "html": "<article>One canonical copy.</article>",
        "groundtruth_content": original,
    }
    corrected = {**row, "groundtruth_content": replacement}
    manifest = {
        "schema_version": 3,
        "decision_contracts": _DECISION_CONTRACTS,
        "input_population": population([row]),
        "output_population": population([corrected]),
        "corrections": [
            {
                "track_id": "duplicate-editor-buffer",
                "url": "https://example.test/article",
                "original_groundtruth_sha256": sha256(original),
                "replacement_file": "replacement.md",
                "replacement_sha256": sha256(replacement),
                "html_sha256": sha256("<article>One canonical copy.</article>"),
                "decision_contract": "main-content-reference",
                "rationale": "The editor buffer duplicates the selected article body.",
            }
        ],
    }
    manifest_path = tmp_path / "corrections.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return row, replacement, manifest_path


def population(rows):
    ids = [row.get("track_id") or row.get("id") for row in rows]
    return {
        "row_count": len(rows),
        "ordered_track_ids_sha256": json_sha256(ids),
        "rows_sha256": json_sha256(rows),
    }


def rebind_manifest(path, input_rows, output_rows):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["input_population"] = population(input_rows)
    manifest["output_population"] = population(output_rows)
    path.write_text(json.dumps(manifest), encoding="utf-8")


class DatasetCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_correction_replaces_only_the_bound_reference(self):
        row, replacement, manifest_path = fixture(self.path)
        untouched = {"track_id": "other", "groundtruth_content": "Other"}
        corrected = {**row, "groundtruth_content": replacement}
        rebind_manifest(manifest_path, [row, untouched], [corrected, untouched])
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

    def test_correction_rejects_method_outcome_as_decision_authority(self):
        row, _, manifest_path = fixture(self.path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["corrections"][0]["method_score"] = {"before": 0.1, "after": 0.9}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "undeclared decision inputs"):
            apply_corrections([row], manifest_path)

    def test_correction_requires_source_and_contract_evidence(self):
        row, _, manifest_path = fixture(self.path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["decision_contracts"]["main-content-reference"][
            "required_source_evidence"
        ] = ["original_reference"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "decision contracts changed"):
            apply_corrections([row], manifest_path)

    def test_correction_rejects_changes_to_untouched_population(self):
        row, replacement, manifest_path = fixture(self.path)
        untouched = {"track_id": "other", "groundtruth_content": "Other"}
        corrected = {**row, "groundtruth_content": replacement}
        rebind_manifest(manifest_path, [row, untouched], [corrected, untouched])
        mutations = [
            [row, {**untouched, "groundtruth_content": "Changed"}],
            [row],
            [row, untouched, untouched],
            [untouched, row],
        ]
        for rows in mutations:
            with self.subTest(rows=[item["track_id"] for item in rows]):
                with self.assertRaises(ValueError):
                    apply_corrections(rows, manifest_path)

    def test_metadata_correction_is_hash_bound(self):
        meta = {"code": ["interline"], "language": "en"}
        manifest = {
            "schema_version": 3,
            "decision_contracts": _DECISION_CONTRACTS,
            "corrections": [{
                "track_id": "wrong-code-label",
                "url": "https://example.test/plain",
                "original_meta_sha256": json_sha256(meta),
                "replacement_meta": {"code": [], "language": "en"},
                "decision_contract": "feature-scope-annotation",
                "rationale": "The frozen source contains no selected code structure.",
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
        corrected_row = {**row, "meta": {"code": [], "language": "en"}}
        manifest["input_population"] = population([row])
        manifest["output_population"] = population([corrected_row])
        path.write_text(json.dumps(manifest), encoding="utf-8")
        corrected = apply_corrections([row], path)[0]
        self.assertEqual(corrected["meta"]["code"], [])
        row["meta"]["code"] = ["inline"]
        with self.assertRaises(ValueError):
            apply_corrections([row], path)

    def test_repository_manifest_and_replacement_are_bound(self):
        root = Path(__file__).parent.parent
        manifest_path = root / "data/corrections/WebMainBench_545.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(manifest["input_population"]["row_count"], 545)
        self.assertEqual(manifest["output_population"]["row_count"], 545)
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
