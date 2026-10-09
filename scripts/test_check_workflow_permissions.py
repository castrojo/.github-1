#!/usr/bin/env python3
"""Tests for check-workflow-permissions.py.

The script is dependency-free (no PyYAML), so these tests import it by path and
exercise its parser and CLI directly. Run with either:

    python3 test_check_workflow_permissions.py
    python3 -m unittest scripts.test_check_workflow_permissions
"""
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = SCRIPT_DIR / "check-workflow-permissions.py"

_spec = importlib.util.spec_from_file_location(
    "check_workflow_permissions", str(SCRIPT_PATH)
)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


class TestHasTopLevelPermissions(unittest.TestCase):
    def test_present_with_children(self):
        doc = "name: CI\npermissions:\n  contents: read\njobs:\n  build:\n    runs-on: x\n"
        self.assertTrue(check._has_top_level_permissions(doc))

    def test_present_multiple_scopes(self):
        doc = "permissions:\n  contents: write\n  packages: write\n"
        self.assertTrue(check._has_top_level_permissions(doc))

    def test_missing(self):
        doc = "name: CI\njobs:\n  build:\n    runs-on: x\n"
        self.assertFalse(check._has_top_level_permissions(doc))

    def test_empty_mapping(self):
        doc = "permissions:\njobs:\n  build:\n"
        self.assertFalse(check._has_top_level_permissions(doc))

    def test_empty_inline_map(self):
        doc = "permissions: {}\n"
        self.assertFalse(check._has_top_level_permissions(doc))

    def test_comment_only_block(self):
        doc = "permissions:\n  # TODO add scopes\n"
        self.assertFalse(check._has_top_level_permissions(doc))

    def test_job_level_only_is_not_top_level(self):
        doc = "jobs:\n  ste:\n    permissions:\n      contents: read\n"
        self.assertFalse(check._has_top_level_permissions(doc))

    def test_inline_scalar_declares_intent(self):
        doc = "permissions: read\n"
        self.assertTrue(check._has_top_level_permissions(doc))

    def test_workflow_call_inputs_then_permissions(self):
        doc = (
            "on:\n  workflow_call:\n    inputs:\n      app-id:\n        type: string\n"
            "permissions:\n  contents: read\n"
        )
        self.assertTrue(check._has_top_level_permissions(doc))

    def test_permissions_before_on(self):
        doc = "permissions:\n  contents: read\non:\n  push:\n"
        self.assertTrue(check._has_top_level_permissions(doc))


class TestIterDocuments(unittest.TestCase):
    def test_single_document(self):
        docs = list(check._iter_documents("permissions:\n  contents: read\n"))
        self.assertEqual(len(docs), 1)

    def test_multi_document(self):
        text = (
            "permissions:\n  contents: read\n"
            "---\n"
            "name: other\n"
        )
        docs = list(check._iter_documents(text))
        self.assertEqual(len(docs), 2)
        self.assertTrue(check._has_top_level_permissions(docs[0]))
        self.assertFalse(check._has_top_level_permissions(docs[1]))


class TestCheckFile(unittest.TestCase):
    def test_missing_file_reports_violation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "ci.yml").write_text("jobs:\n  build:\n    runs-on: x\n")
            violations = check.check_file(Path(d) / "ci.yml")
        self.assertEqual(len(violations), 1)
        self.assertIn("missing top-level", violations[0])

    def test_present_file_reports_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "ci.yml").write_text("permissions:\n  contents: read\n")
            self.assertEqual(check.check_file(Path(d) / "ci.yml"), [])

    def test_empty_block_is_violation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "ci.yml").write_text("permissions:\n")
            self.assertEqual(len(check.check_file(Path(d) / "ci.yml")), 1)


class TestFindWorkflowFiles(unittest.TestCase):
    def test_finds_and_sorts_yml_and_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "b.yml").write_text("")
            (Path(d) / "a.yaml").write_text("")
            (Path(d) / "not-a-workflow.txt").write_text("")
            files = check.find_workflow_files(Path(d))
        self.assertEqual(
            [f.name for f in files],
            ["a.yaml", "b.yml"],
        )

    def test_missing_directory_reports_error(self):
        files = check.find_workflow_files(Path("/no/such/dir/here"))
        self.assertEqual(len(files), 1)
        self.assertIn("no such directory", files[0])


class TestMain(unittest.TestCase):
    def _write_dir(self, **files):
        d = tempfile.mkdtemp()
        for name, content in files.items():
            (Path(d) / name).write_text(content)
        return d

    def test_exit_zero_when_compliant(self):
        d = self._write_dir(**{"ci.yml": "permissions:\n  contents: read\n"})
        self.assertEqual(check.main([d]), 0)

    def test_exit_one_when_violation(self):
        d = self._write_dir(**{"ci.yml": "jobs:\n  build:\n    runs-on: x\n"})
        self.assertEqual(check.main([d]), 1)

    def test_json_output(self):
        d = self._write_dir(**{"ci.yml": "jobs:\n  build:\n"})
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = check.main([d, "--json"])
        self.assertEqual(rc, 1)
        payload = json.loads(buf.getvalue())
        self.assertEqual(len(payload["violations"]), 1)

    def test_quiet_suppresses_output(self):
        d = self._write_dir(**{"ci.yml": "jobs:\n  build:\n"})
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = check.main([d, "--quiet"])
        self.assertEqual(rc, 1)
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
