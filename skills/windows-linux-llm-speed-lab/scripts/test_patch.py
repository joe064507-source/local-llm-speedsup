"""Isolated source-file behavior tests. No models, devices, network or services."""
import copy
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout

import patch as patcher


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "source"
        self.payloads = self.base / "payloads"
        self.root.mkdir()
        self.payloads.mkdir()
        self.state = self.base / "backup"
        self.identity = self.base / "identity.json"
        self.identity.write_text(json.dumps({"runtime": "synthetic", "contract": "PRIVATE_CONTRACT"}))
        self.old = b"def calculate(value):\n    return value + 1\n"
        self.new = b"def calculate(value):\n    return 1 + value\n"
        (self.root / "engine.py").write_bytes(self.old)
        (self.payloads / "engine.py").write_bytes(self.new)
        self.document = {"version": 1,
            "identity_sha256": patcher.identity_digest(json.loads(self.identity.read_text())),
            "files": [{"path": "engine.py", "candidate": "payloads/engine.py",
                       "before_sha256": patcher.sha(self.old), "after_sha256": patcher.sha(self.new)}]}
        self.manifest = self.base / "patch.json"
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.document))

    def apply(self):
        return patcher.apply_patch(self.root, self.manifest, self.identity, self.state, True)

    def rollback(self):
        return patcher.rollback(self.root, self.state, True)

    def test_check_writes_nothing(self):
        before = {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        _, _, entries = patcher.prepare(self.root, self.manifest, self.identity)
        after = {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(len(entries), 1)
        self.assertFalse(self.state.exists())

    def test_apply_changes_real_source_and_rollback_restores_bytes(self):
        self.assertEqual(self.apply()["status"], "applied")
        self.assertEqual((self.root / "engine.py").read_bytes(), self.new)
        namespace = {}
        exec(compile((self.root / "engine.py").read_bytes(), "synthetic-engine", "exec"), namespace)
        self.assertEqual(namespace["calculate"](41), 42)
        self.assertEqual(self.rollback()["status"], "rolled_back")
        self.assertEqual((self.root / "engine.py").read_bytes(), self.old)
        self.assertTrue((self.state / "originals/000.txt").exists())
        self.assertEqual(self.rollback()["status"], "rolled_back")

    def test_apply_and_rollback_require_confirmation(self):
        with self.assertRaisesRegex(patcher.PatchError, "confirmation"):
            patcher.apply_patch(self.root, self.manifest, self.identity, self.state)
        self.assertFalse(self.state.exists())
        self.apply()
        with self.assertRaisesRegex(patcher.PatchError, "confirmation"):
            patcher.rollback(self.root, self.state)

    def test_wrong_identity_and_changed_candidates_do_not_write(self):
        for mode in ("identity", "candidate"):
            with self.subTest(mode=mode):
                if mode == "identity":
                    self.document["identity_sha256"] = "0" * 64
                    self.save()
                else:
                    self.document["identity_sha256"] = patcher.identity_digest(json.loads(self.identity.read_text()))
                    self.save()
                    (self.payloads / "engine.py").write_text("different")
                with self.assertRaises(patcher.PatchError):
                    self.apply()
                self.assertFalse(self.state.exists())
                self.assertEqual((self.root / "engine.py").read_bytes(), self.old)

    def test_changed_baseline_is_preserved(self):
        (self.root / "engine.py").write_text("later user edits")
        with self.assertRaisesRegex(patcher.PatchError, "baseline_drift"):
            self.apply()
        self.assertEqual((self.root / "engine.py").read_text(), "later user edits")
        self.assertFalse(self.state.exists())

    def test_existing_state_is_not_overwritten(self):
        self.state.mkdir()
        (self.state / "keep").write_text("PRIVATE_BACKUP")
        with self.assertRaises(FileExistsError):
            self.apply()
        self.assertEqual((self.state / "keep").read_text(), "PRIVATE_BACKUP")
        self.assertEqual((self.root / "engine.py").read_bytes(), self.old)

    def test_backup_must_stay_outside_source(self):
        self.state = self.root / "backup"
        with self.assertRaisesRegex(patcher.PatchError, "outside_source"):
            self.apply()
        self.assertFalse(self.state.exists())

    def test_unsafe_and_nonportable_paths_rejected(self):
        for value in ("../escape", "/absolute", "C:/drive", "folder\\file", "a/./b", "a//b",
                      ".git/config", "nested/.GIT/config", "con.py", "lpt1.txt", "trailing. ", ""):
            with self.subTest(value=value), self.assertRaises(patcher.PatchError):
                patcher.relative_parts(value)

    def test_duplicate_case_aliased_targets_rejected(self):
        self.document["files"].append(copy.deepcopy(self.document["files"][0]))
        self.document["files"][-1]["path"] = "ENGINE.py"
        self.save()
        with self.assertRaisesRegex(patcher.PatchError, "duplicate_target"):
            self.apply()
        self.assertFalse(self.state.exists())

    def test_missing_parent_directory_is_not_created(self):
        self.document["files"][0]["path"] = "missing/engine.py"
        self.document["files"][0]["before_sha256"] = None
        self.save()
        with self.assertRaisesRegex(patcher.PatchError, "parent_directory_missing"):
            self.apply()
        self.assertFalse((self.root / "missing").exists())

    def test_linked_source_and_linked_parent_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "file.py").write_bytes(self.old)
        try:
            (self.root / "alias").symlink_to(outside, target_is_directory=True)
            (self.root / "link.py").symlink_to(outside / "file.py")
        except (OSError, NotImplementedError):
            self.skipTest("Host does not permit symlink creation")
        for value in ("alias/file.py", "link.py"):
            with self.subTest(value=value), self.assertRaisesRegex(patcher.PatchError, "linked_path"):
                patcher.source_path(self.root, value)

    def test_binary_and_oversized_payloads_rejected(self):
        for data in (b"\x00binary", b"\xff"):
            (self.payloads / "engine.py").write_bytes(data)
            self.document["files"][0]["after_sha256"] = patcher.sha(data)
            self.save()
            with self.assertRaises(patcher.PatchError):
                self.apply()
        with self.assertRaisesRegex(patcher.PatchError, "oversized"):
            patcher.read_bytes(self.root / "engine.py", limit=1)
        self.assertFalse(self.state.exists())

    def test_memory_budget_is_enforced_before_backup(self):
        with mock.patch.object(patcher, "MAX_TOTAL", 1), self.assertRaisesRegex(patcher.PatchError, "memory_budget"):
            self.apply()
        self.assertFalse(self.state.exists())

    def test_new_file_removed_only_if_it_still_matches(self):
        self.document["files"][0]["path"] = "new.py"
        self.document["files"][0]["before_sha256"] = None
        self.save()
        self.apply()
        self.assertTrue((self.root / "new.py").exists())
        (self.root / "new.py").write_text("user modification")
        with self.assertRaisesRegex(patcher.PatchError, "new_edits"):
            self.rollback()
        (self.root / "new.py").write_bytes(self.new)
        self.rollback()
        self.assertFalse((self.root / "new.py").exists())
        self.assertEqual((self.root / "engine.py").read_bytes(), self.old)

    def test_partial_apply_can_be_rolled_back(self):
        (self.root / "second.py").write_bytes(self.old)
        second = copy.deepcopy(self.document["files"][0])
        second["path"] = "second.py"
        self.document["files"].append(second)
        self.save()
        original_replace = patcher.replace_file
        def fail_second(path, data, mode):
            if path.name == "second.py":
                raise OSError("PRIVATE_ERROR")
            return original_replace(path, data, mode)
        with mock.patch.object(patcher, "replace_file", side_effect=fail_second), self.assertRaises(OSError):
            self.apply()
        self.assertEqual((self.root / "engine.py").read_bytes(), self.new)
        self.assertEqual((self.root / "second.py").read_bytes(), self.old)
        self.assertEqual(json.loads((self.state / "state.json").read_text())["status"], "prepared")
        self.rollback()
        self.assertEqual((self.root / "engine.py").read_bytes(), self.old)

    def test_corrupt_backup_blocks_all_rollback_writes(self):
        self.apply()
        (self.state / "originals/000.txt").write_text("corrupt")
        with self.assertRaisesRegex(patcher.PatchError, "backup_corrupt"):
            self.rollback()
        self.assertEqual((self.root / "engine.py").read_bytes(), self.new)

    def test_wrong_root_cannot_use_another_backups_state(self):
        self.apply()
        alternate = self.base / "different-source"
        alternate.mkdir()
        (alternate / "engine.py").write_bytes(self.new)
        with self.assertRaisesRegex(patcher.PatchError, "state_root"):
            patcher.rollback(alternate, self.state, True)
        self.assertEqual((alternate / "engine.py").read_bytes(), self.new)

    def test_rollback_preserves_later_source_edits(self):
        self.apply()
        (self.root / "engine.py").write_text("new independent work")
        with self.assertRaisesRegex(patcher.PatchError, "new_edits"):
            self.rollback()
        self.assertEqual((self.root / "engine.py").read_text(), "new independent work")

    def test_original_mode_preserved_and_state_private_on_posix(self):
        if os.name != "posix":
            self.skipTest("POSIX mode assertion; Windows needs ACL validation")
        os.chmod(self.root / "engine.py", 0o750)
        self.apply()
        self.assertEqual(stat.S_IMODE((self.root / "engine.py").stat().st_mode), 0o750)
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.state / "state.json").stat().st_mode), 0o600)
        self.rollback()
        self.assertEqual(stat.S_IMODE((self.root / "engine.py").stat().st_mode), 0o750)

    def test_cli_check_and_errors_do_not_export_private_inputs(self):
        output = io.StringIO()
        args = ["check", "--root", str(self.root), "--manifest", str(self.manifest), "--identity", str(self.identity)]
        with redirect_stdout(output):
            self.assertEqual(patcher.main(args), 0)
        self.assertNotIn(str(self.base), output.getvalue())
        self.assertNotIn("PRIVATE", output.getvalue())
        with mock.patch.object(patcher, "prepare", side_effect=OSError("PRIVATE_ERROR")), redirect_stdout(output):
            self.assertEqual(patcher.main(args), 2)
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_no_op_and_reapplying_same_manifest_rejected(self):
        self.apply()
        with self.assertRaisesRegex(patcher.PatchError, "baseline_drift"):
            self.apply()
        self.document["files"][0]["before_sha256"] = patcher.sha(self.new)
        self.save()
        with self.assertRaisesRegex(patcher.PatchError, "no_op"):
            patcher.prepare(self.root, self.manifest, self.identity)


if __name__ == "__main__":
    unittest.main()
