"""Apply hash-bound corrections to externally distributed benchmark datasets."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_sha256(value: Any) -> str:
    return _sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def apply_corrections(
    rows: Iterable[Dict[str, Any]], manifest_path: Path
) -> List[Dict[str, Any]]:
    """Return corrected rows and reject stale or ambiguous correction targets."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported dataset correction schema")

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
