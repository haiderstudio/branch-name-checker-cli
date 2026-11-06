#!/usr/bin/env python3
"""Tests for branch_name_checker. Standard library unittest only."""

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from branch_name_checker import (  # noqa: E402
    DEFAULT_MAX_LENGTH,
    DEFAULT_PATTERN,
    check_name,
    compile_pattern,
    git_name_problem,
    load_config,
    run,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXAMPLES = ROOT / "examples"


def run_cli(argv, stdin_text=None):
    """Run the CLI in-process and capture stdout/stderr. Returns (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    code = run(argv, stdin_text=stdin_text, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def default_pattern():
    return re.compile(DEFAULT_PATTERN)


class TestGitNameProblem(unittest.TestCase):
    def test_valid_names_have_no_problem(self):
        for name in (
            "feature/add-login",
            "fix/crash-on-start",
            "main",
            "feature/add_login-and-tests",
            "release/1.4.0",
        ):
            self.assertIsNone(git_name_problem(name), name)

    def test_empty_name(self):
        self.assertEqual(git_name_problem(""), "empty branch name")

    def test_just_at_sign(self):
        self.assertEqual(git_name_problem("@"), "a branch name cannot be just '@'")

    def test_leading_dash(self):
        self.assertIn("start with '-'", git_name_problem("-feature/x"))

    def test_leading_and_trailing_slash(self):
        self.assertIn("start or end with '/'", git_name_problem("/feature/x"))
        self.assertIn("start or end with '/'", git_name_problem("feature/"))

    def test_double_slash(self):
        self.assertIn("'//'", git_name_problem("feature//x"))

    def test_double_dot(self):
        self.assertIn("'..'", git_name_problem("feature/a..b"))

    def test_at_brace(self):
        self.assertIn("'@{'", git_name_problem("feature/a@{b"))

    def test_trailing_dot(self):
        self.assertIn("end with '.'", git_name_problem("feature/x."))

    def test_dot_lock(self):
        self.assertIn("'.lock'", git_name_problem("feature/x.lock"))
        self.assertIn("'.lock'", git_name_problem("x.lock/feature"))

    def test_dot_component(self):
        self.assertIn("start with '.'", git_name_problem("feature/.hidden"))

    def test_forbidden_characters(self):
        for bad in ("a b", "a~b", "a^b", "a:b", "a?b", "a*b", "a[b", "a\\b"):
            self.assertIsNotNone(git_name_problem(bad), bad)

    def test_control_character(self):
        self.assertIsNotNone(git_name_problem("a\tb"))


class TestCheckName(unittest.TestCase):
    def test_default_pattern_passes(self):
        for name in (
            "feature/add-login",
            "fix/crash-on-start",
            "docs/readme",
            "chore/clean-up",
            "refactor/split-parser",
            "hotfix/security-patch",
            "release/1.4.0",
        ):
            ok, reason = check_name(name, default_pattern(), ("main",), 50)
            self.assertTrue(ok, "%s should pass: %s" % (name, reason))

    def test_default_pattern_fails(self):
        for name in (
            "BadBranchName",
            "hotfix",
            "feature",
            "Feature/add-login",
            "feature/Add-Login",
            "feature/add login",
            "feat/add-login",
            "bugfix/crash",
            "feature//x",
        ):
            ok, reason = check_name(name, default_pattern(), ("main",), 50)
            self.assertFalse(ok, "%s should fail" % name)
            self.assertIsNotNone(reason)

    def test_allow_list_passes_without_prefix(self):
        for name in ("main", "master", "develop"):
            ok, _reason = check_name(
                name, default_pattern(), ("main", "master", "develop"), 50
            )
            self.assertTrue(ok, name)

    def test_allow_list_does_not_pass_other_names(self):
        ok, _reason = check_name("staging", default_pattern(), ("main",), 50)
        self.assertFalse(ok)

    def test_git_problem_beats_pattern(self):
        ok, reason = check_name("feature/", default_pattern(), ("main",), 50)
        self.assertFalse(ok)
        self.assertIn("start or end with '/'", reason)

    def test_max_length(self):
        long_name = "feature/" + "a" * 43  # 51 characters total
        self.assertEqual(len(long_name), 51)
        ok, reason = check_name(long_name, default_pattern(), (), 50)
        self.assertFalse(ok)
        self.assertIn("too long", reason)
        ok, _reason = check_name(long_name, default_pattern(), (), 60)
        self.assertTrue(ok)

    def test_custom_pattern(self):
        pattern = re.compile(r"^[A-Z]+-\d+-.+$")
        ok, _reason = check_name("ENG-123-add-user", pattern, (), 50)
        self.assertTrue(ok)
        ok, _reason = check_name("feature/add-login", pattern, (), 50)
        self.assertFalse(ok)

    def test_compile_pattern_rejects_bad_regex(self):
        with self.assertRaises(ValueError):
            compile_pattern("[unclosed")


class TestConfig(unittest.TestCase):
    def test_example_config_matches_defaults(self):
        pattern, allow, max_length = load_config(EXAMPLES / "config.json")
        self.assertEqual(pattern.pattern, DEFAULT_PATTERN)
        self.assertEqual(allow, ("main", "master", "develop"))
        self.assertEqual(max_length, 50)

    def test_config_custom_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(
                json.dumps(
                    {
                        "pattern": r"^[A-Z]+-\d+$",
                        "allow": ["main"],
                        "max_length": 20,
                    }
                )
            )
            pattern, allow, max_length = load_config(path)
            self.assertEqual(pattern.pattern, r"^[A-Z]+-\d+$")
            self.assertEqual(allow, ("main",))
            self.assertEqual(max_length, 20)

    def test_config_missing_file(self):
        with self.assertRaises(ValueError):
            load_config(Path("/no/such/config.json"))

    def test_config_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text("{not json")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_config_not_an_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text('["feature/x"]')
            with self.assertRaises(ValueError):
                load_config(path)

    def test_config_bad_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(json.dumps({"pattern": "[unclosed"}))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_config_bad_allow(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(json.dumps({"allow": "main"}))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_config_bad_max_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(json.dumps({"max_length": 0}))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_flags_override_config(self):
        code, out, _err = run_cli(
            [
                "--config",
                str(EXAMPLES / "config.json"),
                "--pattern",
                r"^[A-Z]+-\d+$",
                "ENG-42",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("PASS   ENG-42", out)


class TestCli(unittest.TestCase):
    def test_positional_names_pass_and_fail(self):
        code, out, _err = run_cli(["feature/add-login", "BadBranchName"])
        self.assertEqual(code, 1)
        self.assertIn("PASS   feature/add-login", out)
        self.assertIn("FAIL   BadBranchName: does not match the pattern", out)
        self.assertIn("2 checked, 1 passed, 1 failed", out)

    def test_all_pass_exits_zero(self):
        code, out, _err = run_cli(["feature/add-login", "fix/crash"])
        self.assertEqual(code, 0)
        self.assertIn("2 checked, 2 passed, 0 failed", out)

    def test_file_input(self):
        code, out, _err = run_cli(["--file", str(EXAMPLES / "branches.txt")])
        self.assertEqual(code, 1)
        self.assertIn("9 checked, 6 passed, 3 failed", out)
        self.assertIn("FAIL   feature/: a branch name cannot start or end with '/'", out)

    def test_file_input_missing_file(self):
        code, _out, err = run_cli(["--file", "no-such-file.txt"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read file", err)

    def test_stdin_input(self):
        code, out, _err = run_cli(
            ["--stdin"], stdin_text="feature/add-login\nBadBranch\n# a comment\n\nfix/x\n"
        )
        self.assertEqual(code, 1)
        self.assertIn("3 checked, 2 passed, 1 failed", out)

    def test_allow_flag(self):
        code, out, _err = run_cli(["--allow", "staging", "staging"])
        self.assertEqual(code, 0)
        self.assertIn("PASS   staging", out)

    def test_max_length_flag(self):
        long_name = "feature/" + "a" * 43
        code, _out, _err = run_cli([long_name])
        self.assertEqual(code, 1)
        code, out, _err = run_cli(["--max-length", "60", long_name])
        self.assertEqual(code, 0)
        self.assertIn("PASS", out)

    def test_bad_max_length_flag(self):
        code, _out, err = run_cli(["--max-length", "0", "feature/x"])
        self.assertEqual(code, 2)
        self.assertIn("--max-length must be at least 1", err)

    def test_bad_pattern_flag(self):
        code, _out, err = run_cli(["--pattern", "[unclosed", "feature/x"])
        self.assertEqual(code, 2)
        self.assertIn("not a valid regex", err)

    def test_bad_config_flag(self):
        code, _out, err = run_cli(["--config", "no-such.json", "feature/x"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read config file", err)

    def test_two_sources_is_an_error(self):
        code, _out, err = run_cli(
            ["--file", str(EXAMPLES / "branches.txt"), "feature/x"]
        )
        self.assertEqual(code, 2)
        self.assertIn("only one way", err)

    def test_empty_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.txt"
            path.write_text("# only a comment\n\n")
            code, _out, err = run_cli(["--file", str(path)])
            self.assertEqual(code, 2)
            self.assertIn("no branch names to check", err)

    def test_git_flag_in_temp_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
            subprocess.run(["git", "init", "-q", tmp], check=True, env=env)
            subprocess.run(
                ["git", "-C", tmp, "config", "user.email", "t@example.com"],
                check=True,
                env=env,
            )
            subprocess.run(
                ["git", "-C", tmp, "config", "user.name", "Test"],
                check=True,
                env=env,
            )
            Path(tmp, "f.txt").write_text("x\n")
            subprocess.run(["git", "-C", tmp, "add", "."], check=True, env=env)
            subprocess.run(
                ["git", "-C", tmp, "commit", "-qm", "init"], check=True, env=env
            )
            subprocess.run(
                ["git", "-C", tmp, "checkout", "-qb", "feature/add-login"],
                check=True,
                env=env,
            )
            subprocess.run(
                ["git", "-C", tmp, "checkout", "-qb", "BadBranch"],
                check=True,
                env=env,
            )
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                code, out, _err = run_cli(["--git"])
            finally:
                os.chdir(cwd)
            self.assertEqual(code, 1)
            self.assertIn("PASS   feature/add-login", out)
            self.assertIn("FAIL   BadBranch", out)
            # --current checks only the checked-out branch.
            try:
                os.chdir(tmp)
                code, out, _err = run_cli(["--current"])
            finally:
                os.chdir(cwd)
            self.assertEqual(code, 1)
            self.assertIn("FAIL   BadBranch", out)
            self.assertIn("1 checked, 0 passed, 1 failed", out)

    def test_git_flag_outside_a_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                code, _out, err = run_cli(["--git"])
            finally:
                os.chdir(cwd)
            self.assertEqual(code, 2)
            self.assertIn("not a git repo", err)

    def test_no_input_outside_a_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                code, _out, err = run_cli([])
            finally:
                os.chdir(cwd)
            self.assertEqual(code, 2)
            self.assertIn("not a git repo", err)


class TestExamples(unittest.TestCase):
    def test_sample_output_matches_fresh_run(self):
        code, out, _err = run_cli(["--file", str(EXAMPLES / "branches.txt")])
        self.assertEqual(code, 1)
        committed = (EXAMPLES / "sample-output.txt").read_text()
        self.assertEqual(out, committed)

    def test_run_example_script(self):
        done = subprocess.run(
            ["sh", str(EXAMPLES / "run-example.sh")],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(done.returncode, 0)
        self.assertIn("9 checked, 6 passed, 3 failed", done.stdout)
        self.assertIn("2 checked, 1 passed, 1 failed", done.stdout)

    def test_readme_quoted_output_is_real(self):
        committed = (EXAMPLES / "sample-output.txt").read_text()
        readme = (ROOT / "README.md").read_text()
        for line in (
            "PASS   feature/add-login",
            "FAIL   BadBranchName: does not match the pattern",
            "FAIL   feature/: a branch name cannot start or end with '/'",
            "9 checked, 6 passed, 3 failed",
        ):
            self.assertIn(line, committed)
            self.assertIn(line, readme)


class TestRepoHygiene(unittest.TestCase):
    def test_stdlib_only_imports(self):
        allowed = {
            "argparse",
            "json",
            "re",
            "subprocess",
            "sys",
            "pathlib",
            "io",
            "os",
            "tempfile",
            "unittest",
        }
        for path in list((ROOT / "src").rglob("*.py")) + list(
            (ROOT / "tests").rglob("*.py")
        ):
            for line in path.read_text().splitlines():
                if line.startswith("import "):
                    for name in line[7:].split(","):
                        top = name.strip().split(".")[0].split(" ")[0]
                        self.assertIn(
                            top,
                            allowed | {"branch_name_checker"},
                            "%s in %s" % (top, path),
                        )
                elif line.startswith("from "):
                    top = line.split()[1].split(".")[0]
                    self.assertIn(
                        top,
                        allowed | {"branch_name_checker"},
                        "%s in %s" % (top, path),
                    )

    def test_no_placeholders_or_secrets(self):
        banned = (
            "TODO",
            "FIXME",
            "lorem",
            "coming soon",
            "API_KEY",
            "api_key",
            "password =",
        )
        # The tests directory is excluded from this scan: the test file
        # itself names the banned words in its own check list.
        # The .git directory is excluded too: GitHub's checkout ships
        # sample hooks under .git/hooks/ that contain "TODO" (Day 21
        # CI failure), and those are git's own files, not this repo's.
        shipped = [
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in str(path)
            and ".git" not in path.parts
            and "tests" not in path.parts
        ]
        for path in shipped:
            text = path.read_text(errors="ignore")
            for word in banned:
                self.assertNotIn(word, text, "%s in %s" % (word, path))

    def test_no_absolute_paths(self):
        # Same exclusions as the placeholder scan.
        shipped = [
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in str(path)
            and ".git" not in path.parts
            and "tests" not in path.parts
        ]
        for path in shipped:
            text = path.read_text(errors="ignore")
            self.assertNotIn("/home/hatch", text, "absolute path in %s" % path)
            self.assertNotIn("/tmp/", text, "absolute path in %s" % path)

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")


if __name__ == "__main__":
    unittest.main()
