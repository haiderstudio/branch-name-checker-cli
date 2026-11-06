#!/usr/bin/env python3
"""Check git branch names against a team pattern, fail CI on a bad name.

Run: python3 src/branch_name_checker.py feature/add-login
     python3 src/branch_name_checker.py --file examples/branches.txt
     python3 src/branch_name_checker.py --git
     python3 src/branch_name_checker.py --current
     cat branches.txt | python3 src/branch_name_checker.py --stdin

The tool checks each branch name against a pattern (by default
type/short-name, for example feature/add-login, fix/crash-on-start,
docs/readme) and against the rules for a valid git branch name. It
prints PASS or FAIL per branch and a one-line summary. It exits 1
when any branch fails, so it can fail a CI run.

It never renames or deletes a branch, and it never changes a file.
It is report-only and runs fully offline: it sends nothing anywhere
and needs no API key.

Exit codes: 0 when every branch passes, 1 when any branch fails,
2 for a usage or input problem (missing file, bad pattern, bad
config, no branch to check).

Python standard library only.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

VERSION = "1.0.0"

DEFAULT_PATTERN = r"^(feature|fix|docs|chore|refactor|hotfix|release)/[a-z0-9][a-z0-9._-]*$"
DEFAULT_ALLOW = ("main", "master", "develop")
DEFAULT_MAX_LENGTH = 50

# Characters git never allows in a branch name, plus the sequences
# git check-ref-format forbids. Checked before the pattern, so a
# name that git itself would reject gets that reason, not a
# pattern-mismatch reason.
_FORBIDDEN_CHARS = set(" ~^:?*[\\")


def git_name_problem(name):
    """Return a plain-language reason the name is not a valid git
    branch name, or None when git would accept it."""
    if name == "":
        return "empty branch name"
    if name == "@":
        return "a branch name cannot be just '@'"
    if name.startswith("-"):
        return "a branch name cannot start with '-'"
    if name.startswith("/") or name.endswith("/"):
        return "a branch name cannot start or end with '/'"
    if "//" in name:
        return "a branch name cannot contain '//'"
    if ".." in name:
        return "a branch name cannot contain '..'"
    if "@{" in name:
        return "a branch name cannot contain '@{'"
    if name.endswith("."):
        return "a branch name cannot end with '.'"
    if name.endswith(".lock"):
        return "a branch name cannot end with '.lock'"
    for part in name.split("/"):
        if part == "":
            return "a branch name cannot have an empty part"
        if part.startswith("."):
            return "no part of a branch name can start with '.'"
        if part.endswith(".lock"):
            return "no part of a branch name can end with '.lock'"
    for char in name:
        if char in _FORBIDDEN_CHARS:
            return "a branch name cannot contain %r" % char
        if ord(char) < 32 or ord(char) == 127:
            return "a branch name cannot contain control characters"
    return None


def check_name(name, pattern, allow, max_length):
    """Check one branch name. Returns (passed, reason).

    reason is None on a pass, or a plain-language reason on a fail.
    The allow list is checked before the pattern, so a name like
    "main" passes even though it has no type prefix.
    """
    problem = git_name_problem(name)
    if problem is not None:
        return False, problem
    if name in allow:
        return True, None
    if len(name) > max_length:
        return False, "too long: %d characters, limit is %d" % (
            len(name),
            max_length,
        )
    if not pattern.search(name):
        return False, "does not match the pattern"
    return True, None


def load_config(path):
    """Load a JSON config file. Returns (pattern, allow, max_length).

    The file may set "pattern" (a regex), "allow" (a list of names
    that always pass), and "max_length" (a number). Anything missing
    keeps the default. A bad file raises ValueError with a plain
    reason.
    """
    try:
        data = json.loads(Path(path).read_text())
    except OSError as error:
        raise ValueError("cannot read config file %s: %s" % (path, error))
    except json.JSONDecodeError as error:
        raise ValueError(
            "config file %s is not valid JSON: %s" % (path, error)
        )
    if not isinstance(data, dict):
        raise ValueError("config file %s must hold one JSON object" % path)
    pattern_text = data.get("pattern", DEFAULT_PATTERN)
    allow = data.get("allow", list(DEFAULT_ALLOW))
    max_length = data.get("max_length", DEFAULT_MAX_LENGTH)
    if not isinstance(pattern_text, str):
        raise ValueError('config "pattern" must be a string')
    if not isinstance(allow, list) or not all(
        isinstance(item, str) for item in allow
    ):
        raise ValueError('config "allow" must be a list of names')
    if not isinstance(max_length, int) or isinstance(max_length, bool):
        raise ValueError('config "max_length" must be a whole number')
    if max_length < 1:
        raise ValueError('config "max_length" must be at least 1')
    try:
        pattern = re.compile(pattern_text)
    except re.error as error:
        raise ValueError("config pattern is not a valid regex: %s" % error)
    return pattern, tuple(allow), max_length


def compile_pattern(text):
    """Compile a --pattern flag value, raising ValueError on bad regex."""
    try:
        return re.compile(text)
    except re.error as error:
        raise ValueError("pattern is not a valid regex: %s" % error)


def read_branches_from_git():
    """Return all local branch names via git. Raises ValueError when
    git is missing or the folder is not a git repo."""
    try:
        done = subprocess.run(
            ["git", "branch", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise ValueError("git is not installed, so --git cannot run")
    if done.returncode != 0:
        raise ValueError(
            "git branch failed: not a git repo, or git reported an error"
        )
    return [line for line in done.stdout.splitlines() if line.strip()]


def read_current_branch():
    """Return the current branch name via git. Raises ValueError when
    git is missing, the folder is not a git repo, or HEAD is detached."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise ValueError("git is not installed, so --current cannot run")
    if done.returncode != 0:
        raise ValueError(
            "git rev-parse failed: not a git repo, or git reported an error"
        )
    name = done.stdout.strip()
    if name == "HEAD":
        raise ValueError("HEAD is detached: there is no current branch")
    return name


def read_names_from_file(path):
    """Read one branch name per line. Blank lines and lines starting
    with '#' are skipped. Raises ValueError when the file is missing."""
    try:
        text = Path(path).read_text()
    except OSError as error:
        raise ValueError("cannot read file %s: %s" % (path, error))
    names = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            names.append(stripped)
    return names


def build_parser():
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="branch_name_checker",
        description=(
            "Check git branch names against a team pattern. Prints "
            "PASS or FAIL per branch and exits 1 when any branch "
            "fails, so it can fail a CI run. Report-only: it never "
            "renames or deletes a branch."
        ),
    )
    parser.add_argument(
        "names",
        nargs="*",
        metavar="NAME",
        help="Branch name to check. With no name and no other input "
        "flag, the current branch is checked.",
    )
    parser.add_argument(
        "--file",
        metavar="FILE",
        help="Read one branch name per line from FILE. Blank lines "
        "and lines starting with '#' are skipped.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read one branch name per line from standard input.",
    )
    parser.add_argument(
        "--git",
        action="store_true",
        help="Check every local branch in the current git repo.",
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Check only the current branch of the current git repo.",
    )
    parser.add_argument(
        "--pattern",
        metavar="REGEX",
        help="Regex a branch name must match. Default: "
        "%s" % DEFAULT_PATTERN,
    )
    parser.add_argument(
        "--allow",
        metavar="NAMES",
        default=None,
        help="Comma-separated names that always pass, for example "
        "main,master. Default: main,master,develop.",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        metavar="N",
        default=None,
        help="Longest allowed branch name in characters. Default: 50.",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="JSON config file with \"pattern\", \"allow\", and "
        "\"max_length\". Command-line flags override the config.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="branch_name_checker " + VERSION,
    )
    return parser


def run(argv, stdin_text=None, stdout=None, stderr=None):
    """Run the checker. Returns the exit code: 0 all pass, 1 any
    fail, 2 usage or input problem."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    # Settings: config file first, then flags override it.
    try:
        if args.config:
            pattern, allow, max_length = load_config(args.config)
        else:
            pattern = re.compile(DEFAULT_PATTERN)
            allow = DEFAULT_ALLOW
            max_length = DEFAULT_MAX_LENGTH
        if args.pattern:
            pattern = compile_pattern(args.pattern)
        if args.allow is not None:
            allow = tuple(
                item.strip() for item in args.allow.split(",") if item.strip()
            )
        if args.max_length is not None:
            if args.max_length < 1:
                raise ValueError("--max-length must be at least 1")
            max_length = args.max_length
    except ValueError as error:
        print("error: %s" % error, file=err)
        return 2

    # Gather the names to check.
    sources = sum(
        [
            bool(args.names),
            bool(args.file),
            bool(args.stdin),
            bool(args.git),
            bool(args.current),
        ]
    )
    if sources > 1:
        print(
            "error: give branch names only one way: names, --file, "
            "--stdin, --git, or --current",
            file=err,
        )
        return 2
    try:
        if args.file:
            names = read_names_from_file(args.file)
        elif args.stdin:
            text = stdin_text if stdin_text is not None else sys.stdin.read()
            names = [
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        elif args.git:
            names = read_branches_from_git()
        elif args.current:
            names = [read_current_branch()]
        elif args.names:
            names = list(args.names)
        else:
            names = [read_current_branch()]
    except ValueError as error:
        print("error: %s" % error, file=err)
        return 2

    if not names:
        print("error: no branch names to check", file=err)
        return 2

    passed = 0
    failed = 0
    for name in names:
        ok, reason = check_name(name, pattern, allow, max_length)
        if ok:
            print("PASS   %s" % name, file=out)
            passed += 1
        else:
            print("FAIL   %s: %s" % (name, reason), file=out)
            failed += 1
    print(
        "%d checked, %d passed, %d failed" % (len(names), passed, failed),
        file=out,
    )
    return 1 if failed else 0


def main(argv=None):
    """Entry point for the command line."""
    return run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
