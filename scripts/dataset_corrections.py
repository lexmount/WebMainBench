"""Apply hash-bound corrections to externally distributed benchmark datasets."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


_DECISION_CONTRACTS = {
    "main-content-reference": {
        "changed_field": "groundtruth_content",
        "required_source_evidence": ["task_contract", "frozen_html", "original_reference"],
    },
    "feature-scope-annotation": {
        "changed_field": "meta",
        "required_source_evidence": ["task_contract", "frozen_html", "original_metadata"],
    },
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_sha256(value: Any) -> str:
    return _sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _validate_population(rows: List[Dict[str, Any]], binding: Dict[str, Any], label: str) -> None:
    ids = [row.get("track_id") or row.get("id") for row in rows]
    if len(rows) != binding.get("row_count"):
        raise ValueError(f"{label} dataset row count mismatch")
    if any(not isinstance(track_id, str) or not track_id for track_id in ids):
        raise ValueError(f"{label} dataset contains a row without an ID")
    if len(set(ids)) != len(ids):
        raise ValueError(f"{label} dataset contains duplicate track IDs")
    if _json_sha256(ids) != binding.get("ordered_track_ids_sha256"):
        raise ValueError(f"{label} dataset order or IDs changed")
    if _json_sha256(rows) != binding.get("rows_sha256"):
        raise ValueError(f"{label} dataset content changed")


def _validate_decision_basis(correction: Dict[str, Any]) -> None:
    """Require correction authority that does not depend on method outcomes."""
    common = {"track_id", "url", "html_sha256", "decision_contract", "rationale"}
    reference = {"original_groundtruth_sha256", "replacement_file", "replacement_sha256"}
    metadata = {"original_meta_sha256", "replacement_meta"}
    allowed = common | reference | metadata
    if set(correction) - allowed:
        raise ValueError("Dataset correction contains undeclared decision inputs")
    contract = correction.get("decision_contract")
    policy = _DECISION_CONTRACTS.get(contract)
    expected_key = {
        "groundtruth_content": "replacement_file",
        "meta": "replacement_meta",
    }.get(policy and policy["changed_field"])
    if expected_key is None or expected_key not in correction:
        raise ValueError("Dataset correction decision_basis does not match its changed field")
    rationale = correction.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("Dataset correction requires an evidence-based rationale")


def apply_corrections(
    rows: Iterable[Dict[str, Any]], manifest_path: Path
) -> List[Dict[str, Any]]:
    """Return corrected rows and reject stale or ambiguous correction targets."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 3:
        raise ValueError("Unsupported dataset correction schema")
    if manifest.get("decision_contracts") != _DECISION_CONTRACTS:
        raise ValueError("Dataset correction decision contracts changed")

    rows = list(rows)
    _validate_population(rows, manifest["input_population"], "Input")

    corrections = {item["track_id"]: item for item in manifest["corrections"]}
    if len(corrections) != len(manifest["corrections"]):
        raise ValueError("Dataset corrections contain duplicate track IDs")

    applied = set()
    result = []
    for original in rows:
        row = dict(original)
        track_id = row.get("track_id") or row.get("id")
        correction = corrections.get(track_id)
        if correction is not None:
            _validate_decision_basis(correction)
            if track_id in applied:
                raise ValueError(f"Dataset contains duplicate corrected track ID: {track_id}")
            if row.get("url") != correction["url"]:
                raise ValueError(f"URL changed for corrected track ID: {track_id}")
            if "html_sha256" in correction:
                html = row.get("html")
                if not isinstance(html, str) or _sha256(html) != correction["html_sha256"]:
                    raise ValueError(f"HTML changed for corrected track ID: {track_id}")
            changed = False
            if "replacement_file" in correction:
                groundtruth = row.get("groundtruth_content")
                if not isinstance(groundtruth, str):
                    raise ValueError(f"Missing groundtruth_content for corrected track ID: {track_id}")
                if _sha256(groundtruth) != correction["original_groundtruth_sha256"]:
                    raise ValueError(f"Ground truth changed for corrected track ID: {track_id}")
                replacement_path = manifest_path.parent / correction["replacement_file"]
                replacement = replacement_path.read_text(encoding="utf-8")
                if _sha256(replacement) != correction["replacement_sha256"]:
                    raise ValueError(f"Replacement hash mismatch for corrected track ID: {track_id}")
                row["groundtruth_content"] = replacement
                changed = True
            if "replacement_meta" in correction:
                if _json_sha256(row.get("meta")) != correction["original_meta_sha256"]:
                    raise ValueError(f"Metadata changed for corrected track ID: {track_id}")
                row["meta"] = correction["replacement_meta"]
                changed = True
            if not changed:
                raise ValueError(f"Correction has no replacement for track ID: {track_id}")
            applied.add(track_id)
        result.append(row)

    missing = corrections.keys() - applied
    if missing:
        raise ValueError(f"Dataset is missing corrected track IDs: {sorted(missing)}")
    _validate_population(result, manifest["output_population"], "Output")
    return result


def correct_jsonl(input_path: Path, output_path: Path, manifest_path: Path) -> int:
    """Apply a correction manifest to a JSONL file and return its row count."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    rows = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines()]
    corrected = apply_corrections(rows, manifest_path)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in corrected),
        encoding="utf-8",
    )
    return len(corrected)
