#!/usr/bin/env python3
"""Tests for workflow_introspector.py.

The introspector is the shared scaffolding both extracted validators use, so it
gets its own test module. It is loaded by path (the scripts directory is added
to sys.path first so the sibling import inside ci_contract.py / fork_safety.py
resolves). Run with either:

    python3 test_workflow_introspector.py
    python3 -m unittest .test_workflow_introspector
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

_spec = importlib.util.spec_from_file_location("workflow_introspector", SCRIPT_DIR / "workflow_introspector.py")
introspector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(introspector)


class TestGetTriggers(unittest.TestCase):
    def test_string_trigger(self):
        self.assertEqual(introspector.get_triggers({"on": "push"}), {"push": None})

    def test_list_trigger(self):
        self.assertEqual(introspector.get_triggers({"on": ["push", "pull_request"]}),
                         {"push": None, "pull_request": None})

    def test_dict_trigger(self):
        doc = {"on": {"push": {"branches": ["main"]}}}
        self.assertEqual(introspector.get_triggers(doc), {"push": {"branches": ["main"]}})

    def test_boolean_on_key(self):
        # YAML 1.1 parses bare `on:` as True; the loader must accept it.
        self.assertEqual(introspector.get_triggers({True: "push"}), {"push": None})

    def test_absent_trigger(self):
        self.assertEqual(introspector.get_triggers({}), {})


class TestLoadWorkflows(unittest.TestCase):
    def test_dual_index_by_path_and_basename(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "build.yml").write_text("name: Build\non: push\n")
            (Path(d) / "deploy.yaml").write_text("name: Deploy\non: workflow_call\n")
            workflows = introspector.load_workflows(Path(d))
        self.assertIn("build.yml", workflows)
        self.assertIn(f"{d}/build.yml", workflows)
        self.assertIn("deploy.yaml", workflows)
        # Both .yml and .yaml are discovered.
        self.assertEqual(len(workflows), 4)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(introspector.load_workflows(Path(d)), {})


class TestFindCallers(unittest.TestCase):
    def test_only_relative_callers(self):
        workflows = {
            "caller.yml": {"jobs": {"build": {"uses": "./.github/workflows/called.yml"}}},
            "external.yml": {"jobs": {"build": {"uses": "org/repo/.github/workflows/x.yml"}}},
        }
        callers = introspector.find_callers(workflows)
        # find_callers strips the leading `./`, so the key is the bare relative path.
        self.assertEqual(callers.get(".github/workflows/called.yml"), {"caller.yml"})
        self.assertNotIn("./org/repo/.github/workflows/x.yml", callers)

    def test_no_callers(self):
        self.assertEqual(introspector.find_callers({}), {})


class TestIsReachable(unittest.TestCase):
    def _workflows(self, docs):
        return {name: introspector.yaml.safe_load(body) for name, body in docs.items()}

    def test_active_trigger_reachable(self):
        workflows = self._workflows({"build.yml": "on: push\n"})
        self.assertTrue(introspector.is_reachable("build.yml", workflows))

    def test_workflow_call_only_unreachable(self):
        workflows = self._workflows({"called.yml": "on: workflow_call\n"})
        self.assertFalse(introspector.is_reachable("called.yml", workflows))

    def test_reachable_via_caller(self):
        workflows = self._workflows({
            "caller.yml": "on: push\njobs:\n  build:\n    uses: ./called.yml\n",
            "called.yml": "on: workflow_call\n",
        })
        self.assertTrue(introspector.is_reachable("called.yml", workflows))

    def test_missing_workflow_unreachable(self):
        self.assertFalse(introspector.is_reachable("nope.yml", {}))

    def test_cycle_does_not_infinite_loop(self):
        workflows = self._workflows({
            "a.yml": "on: push\njobs:\n  x:\n    uses: ./b.yml\n",
            "b.yml": "on: workflow_call\njobs:\n  y:\n    uses: ./a.yml\n",
        })
        # b is reachable through a (which has push), and the cycle a<->b terminates.
        self.assertTrue(introspector.is_reachable("b.yml", workflows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
