"""Guarded local source-file patching: check, apply, and rollback. Python 3.10+.

The agent authors and tests the patch. This helper never invents changes, runs
commands, downloads code, restarts services, or verifies model quality itself.
Use a trusted, exclusively owned source tree; multi-file changes are not atomic.
State/backups are PRIVATE and must stay outside the source tree and releases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_FILES = 64


class PatchError(Exception):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity_digest(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode())


def fingerprint(value, nullable=False):
    if nullable and value is None:
        return value
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise PatchError("invalid_fingerprint")
    return value


def relative_parts(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise PatchError("unsafe_relative_path")
    parts = value.split("/")
    for part in parts:
        stem = part.split(".", 1)[0].upper()
        if (part in ("", ".", "..") or part.casefold() == ".git"
                or part.endswith((".", " ")) or any(ord(c) < 32 for c in part)
                or stem in {"CON", "PRN", "AUX", "NUL"}
                or re.fullmatch(r"(?:COM|LPT)[1-9]", stem)):
            raise PatchError("unsafe_relative_path")
    return parts


def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def root_path(value):
    path = Path(value)
    if linked(path.lstat()) or not path.is_dir():
        raise PatchError("root_must_be_real_directory")
    return path.resolve(strict=True)


def source_path(root, relative):
    parts = relative_parts(relative)
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if index != len(parts) - 1:
                raise PatchError("parent_directory_missing") from None
            return current
        if linked(info):
            raise PatchError("linked_path_rejected")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise PatchError("parent_not_directory")
        if index == len(parts) - 1 and not stat.S_ISREG(info.st_mode):
            raise PatchError("source_must_be_regular_file")
    return current


def read_bytes(path, limit=MAX_FILE):
    info = path.lstat()
    if linked(info) or not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise PatchError("unsupported_or_oversized_file")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise PatchError("oversized_file")
    return data


def text_bytes(path):
    data = read_bytes(path)
    if b"\x00" in data:
        raise PatchError("binary_payload_rejected")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise PatchError("source_must_be_utf8") from None
    return data


def json_file(path):
    value = json.loads(read_bytes(Path(path), 1024 * 1024))
    if not isinstance(value, dict):
        raise PatchError("json_object_required")
    return value


def current_hash(root, relative):
    path = source_path(root, relative)
    return sha(read_bytes(path)) if path.exists() else None


def unique_files(files):
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise PatchError("invalid_file_count")
    seen = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise PatchError("invalid_file_entry")
        parts = relative_parts(entry.get("path"))
        key = "/".join(parts).casefold()
        # Refuse case aliases even on case-sensitive hosts: manifests are portable.
        if key in seen:
            raise PatchError("duplicate_target")
        seen.add(key)
        fingerprint(entry.get("before_sha256"), nullable=True)
        fingerprint(entry.get("after_sha256"))
        if entry.get("before_sha256") == entry["after_sha256"]:
            raise PatchError("no_op_patch")


def prepare(root, manifest_path, identity_path):
    root = root_path(root)
    manifest = json_file(manifest_path)
    if manifest.get("version") != 1:
        raise PatchError("unsupported_manifest_version")
    expected_identity = fingerprint(manifest.get("identity_sha256"))
    identity = json_file(identity_path)
    if not identity or identity_digest(identity) != expected_identity:
        raise PatchError("identity_mismatch")
    files = manifest.get("files")
    unique_files(files)
    payload_root = Path(manifest_path).resolve(strict=True).parent
    prepared, total = [], 0
    for entry in files:
        path = source_path(root, entry["path"])
        candidate_path = source_path(payload_root, entry.get("candidate"))
        if candidate_path.is_relative_to(root):
            raise PatchError("candidate_must_be_separate_from_target")
        candidate = text_bytes(candidate_path)
        before = text_bytes(path) if path.exists() else None
        mode = stat.S_IMODE(path.stat().st_mode) if before is not None else 0o644
        if mode & ~0o777:
            raise PatchError("special_mode_rejected")
        if (sha(before) if before is not None else None) != entry.get("before_sha256"):
            raise PatchError("baseline_drift")
        if sha(candidate) != entry["after_sha256"]:
            raise PatchError("candidate_drift")
        total += len(candidate) + len(before or b"")
        if total > MAX_TOTAL:
            raise PatchError("patch_memory_budget_exceeded")
        prepared.append({"path": entry["path"], "before": before, "after": candidate,
                         "before_sha256": entry.get("before_sha256"),
                         "after_sha256": entry["after_sha256"], "mode": mode})
    return root, expected_identity, prepared


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def replace_file(path, data, mode):
    fd, name = tempfile.mkstemp(prefix=".speed-lab-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def encode_state(state):
    return json.dumps(state, indent=2, ensure_ascii=False).encode() + b"\n"


def apply_patch(root, manifest, identity, state_dir, confirm_idle=False):
    if not confirm_idle:
        raise PatchError("exclusive_idle_confirmation_required")
    root, contract, entries = prepare(root, manifest, identity)
    state_dir = Path(state_dir)
    state_parent = root_path(state_dir.parent)
    state_dir = state_parent / state_dir.name
    if state_dir.is_relative_to(root) or root.is_relative_to(state_dir):
        raise PatchError("backup_must_be_outside_source_tree")
    # mkdir refuses both existing directories and dangling symlinks; never reuse state.
    state_dir.mkdir(mode=0o700)
    originals = state_dir / "originals"
    originals.mkdir(mode=0o700)
    records = []
    for index, entry in enumerate(entries):
        backup = f"originals/{index:03}.txt" if entry["before"] is not None else None
        if backup:
            write_new(state_dir / backup, entry["before"])
        records.append({key: entry[key] for key in ("path", "before_sha256", "after_sha256", "mode")})
        records[-1]["backup"] = backup
    state = {"version": 1, "status": "prepared", "root": str(root),
             "identity_sha256": contract, "files": records}
    write_new(state_dir / "state.json", encode_state(state))
    # All backups exist before the first source write. On interruption, rollback
    # accepts either each exact original or each exact candidate, never other edits.
    for entry in entries:
        if current_hash(root, entry["path"]) != entry["before_sha256"]:
            raise PatchError("baseline_drift_after_backup")
        replace_file(source_path(root, entry["path"]), entry["after"], entry["mode"])
    if any(current_hash(root, entry["path"]) != entry["after_sha256"] for entry in entries):
        raise PatchError("post_apply_drift")
    state["status"] = "applied"
    replace_file(state_dir / "state.json", encode_state(state), 0o600)
    return {"status": "applied", "files": len(entries), "runtime_restarted": False,
            "quality_or_speed_verified_by_helper": False}


def rollback(root, state_dir, confirm_idle=False):
    if not confirm_idle:
        raise PatchError("exclusive_idle_confirmation_required")
    root, state_dir = root_path(root), root_path(state_dir)
    if state_dir.is_relative_to(root) or root.is_relative_to(state_dir):
        raise PatchError("backup_must_be_outside_source_tree")
    state = json_file(state_dir / "state.json")
    if (state.get("version") != 1 or state.get("root") != str(root)
            or state.get("status") not in ("prepared", "applied", "rolled_back")):
        raise PatchError("state_root_or_version_mismatch")
    entries = state.get("files")
    unique_files(entries)
    planned, total = [], 0
    for index, entry in enumerate(entries):
        mode = entry.get("mode")
        if type(mode) is not int or not 0 <= mode <= 0o777:
            raise PatchError("invalid_backup_mode")
        before = None
        if entry["before_sha256"] is not None:
            expected = f"originals/{index:03}.txt"
            if entry.get("backup") != expected:
                raise PatchError("invalid_backup_path")
            before = text_bytes(source_path(state_dir, expected))
            total += len(before)
            if total > MAX_TOTAL or sha(before) != entry["before_sha256"]:
                raise PatchError("backup_corrupt")
        elif entry.get("backup") is not None:
            raise PatchError("invalid_backup_path")
        current = current_hash(root, entry["path"])
        if current not in (entry["before_sha256"], entry["after_sha256"]):
            raise PatchError("rollback_would_overwrite_new_edits")
        if state["status"] == "rolled_back" and current != entry["before_sha256"]:
            raise PatchError("completed_rollback_state_cannot_be_reused")
        planned.append((entry, current, before))
    for entry, expected, before in reversed(planned):
        if current_hash(root, entry["path"]) != expected:
            raise PatchError("rollback_drift_after_preflight")
        if expected == entry["before_sha256"]:
            continue
        path = source_path(root, entry["path"])
        if before is None:
            path.unlink()  # Only this patch's new, still-exact candidate file.
        else:
            replace_file(path, before, entry["mode"])
    state["status"] = "rolled_back"
    replace_file(state_dir / "state.json", encode_state(state), 0o600)
    return {"status": "rolled_back", "files": len(entries), "backups_retained": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    for mode in ("check", "apply", "rollback"):
        command = modes.add_parser(mode)
        command.add_argument("--root", type=Path, required=True)
        if mode != "rollback":
            command.add_argument("--manifest", type=Path, required=True)
            command.add_argument("--identity", type=Path, required=True)
        if mode != "check":
            command.add_argument("--state-dir", type=Path, required=True)
            command.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "check":
            _, _, entries = prepare(args.root, args.manifest, args.identity)
            result = {"status": "ready", "files": len(entries), "source_modified": False,
                      "identity_check": "declared_contract_only_not_live_hardware"}
        elif args.mode == "apply":
            result = apply_patch(args.root, args.manifest, args.identity, args.state_dir, args.confirm_idle)
        else:
            result = rollback(args.root, args.state_dir, args.confirm_idle)
        print(json.dumps(result))
        return 0
    except (PatchError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error) if isinstance(error, PatchError) else type(error).__name__,
                          "detail": "No private path/content exported. On a failed apply, retain private state for rollback."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
