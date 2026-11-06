# branch-name-checker-cli

Check branch names against your team pattern, fail CI on a bad name.

[![CI](https://github.com/haiderstudio/branch-name-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/branch-name-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`branch_name_checker` checks git branch names against a pattern
your team sets, and against the rules for a valid git branch name.
It prints `PASS` or `FAIL` per branch, plus a one-line summary, and
exits 1 when any branch fails — so it can fail a CI run.

- The default pattern is `type/short-name`, with the types
  `feature`, `fix`, `docs`, `chore`, `refactor`, `hotfix`, and
  `release`. The short name is lowercase letters, digits, dots,
  underscores, and hyphens. `feature/add-login` passes;
  `BadBranchName` fails.
- Names in the allow list always pass, even with no type prefix.
  The default allow list is `main`, `master`, and `develop`.
- The longest allowed name is 50 characters by default
  (`--max-length` changes it).
- A name git itself would reject gets that reason, not a
  pattern-mismatch reason: spaces, `..`, `//`, a leading or
  trailing slash, a trailing dot, `.lock`, `@{`, and the other
  characters git forbids.
- It reads names five ways: as arguments, from a file
  (`--file`), from standard input (`--stdin`), every local branch
  (`--git`), or just the current branch (`--current`). With no
  names and no flag, it checks the current branch.
- `--pattern` sets your own regex, and `--config` reads a JSON
  file with `pattern`, `allow`, and `max_length`. Command-line
  flags override the config file.
- It is report-only and runs fully offline: it never renames or
  deletes a branch, sends nothing anywhere, and needs no API key.

## What it does NOT do

- It does not rename, delete, or create branches. A bad name is
  reported; fixing it is your job.
- It does not check commit messages, pull request titles, or
  anything else about a branch — names only.
- It does not talk to GitHub, GitLab, or any remote. `--git`
  reads only the local branches in the folder you run it in.
- It does not enforce a pattern it was not given. The default
  pattern is a starting point: if your team uses ticket numbers
  or a different separator, pass your own `--pattern` or config
  file.

## Who it is for

Any team that wants branch names to stay readable and
searchable: a developer adding a CI step that fails the build on
a badly named branch, a team lead who keeps finding branches
called `test123` or `final-FINAL`, or anyone who wants one small
check instead of a naming rule buried inside a big CI setup. If
every name passes, you get a clean report; if one fails, the
report says which name and why.

## How this differs from similar tools

Branch-naming rules today live inside bigger tools. The closest
names on GitHub are small and mostly unstarred: the quoted search
for `"branch-name-checker"` returns 2 results, both 0 stars
(shell scripts from 2014 and 2023), and the unquoted search
returns 6 results, all 0 stars — a TypeScript CLI
(tamasmarton/git-branch-checker), a JavaScript remote scanner
(stealth-alpha/branchpol), and an orphaned GitHub Action
(funk-team/branch-naming-check). The best-known checker,
branch-name-lint, is an npm package: it needs Node and an
install, checks one branch at a time, and lives in a hook or a
GitHub Action. Other tools in the space do a different job:
gibr generates branch names from issue trackers instead of
checking them, and `git check-ref-format` only checks whether
git accepts a name, not whether it follows your team's pattern.

This tool does a narrower job: a Python standard-library-only
CLI that checks one name, a list, or every local branch against
your team's pattern, reports the exact reason per failure, and
exits 1 for CI — no install beyond Python, no Node, no hook,
no remote.

## Install

Python standard library only — no packages to download. Clone
the repo and run it in place:

```sh
git clone https://github.com/haiderstudio/branch-name-checker-cli.git
cd branch-name-checker-cli
```

Python 3.10 or newer. Git is only needed for `--git` and
`--current`; checking names from arguments, a file, or standard
input works without git.

## Usage

Check one name:

```sh
python3 src/branch_name_checker.py feature/add-login
```

Real output:

```text
PASS   feature/add-login
1 checked, 1 passed, 0 failed
```

The command exits 0.

Check a good name and a bad name together:

```sh
python3 src/branch_name_checker.py feature/add-login BadBranchName
```

Real output:

```text
PASS   feature/add-login
FAIL   BadBranchName: does not match the pattern
2 checked, 1 passed, 1 failed
```

The command exits 1, because one name failed.

Check a list from a file:

```sh
python3 src/branch_name_checker.py --file examples/branches.txt
```

Real output:

```text
PASS   feature/add-login
PASS   fix/crash-on-start
PASS   docs/readme
FAIL   BadBranchName: does not match the pattern
FAIL   feature/: a branch name cannot start or end with '/'
FAIL   hotfix: does not match the pattern
PASS   feature/add_login-and-tests
PASS   chore/clean-up-old-code
PASS   main
9 checked, 6 passed, 3 failed
```

The command exits 1, because three names failed. The same output
is saved in `examples/sample-output.txt`.

Check every local branch in the current repo:

```sh
python3 src/branch_name_checker.py --git
```

Check only the current branch:

```sh
python3 src/branch_name_checker.py --current
```

Check names from a pipe:

```sh
printf 'feature/add-login\nBadBranch\n' | python3 src/branch_name_checker.py --stdin
```

Real output:

```text
PASS   feature/add-login
FAIL   BadBranch: does not match the pattern
2 checked, 1 passed, 1 failed
```

Use your own pattern, for ticket-style names:

```sh
python3 src/branch_name_checker.py --pattern '^[A-Z]+-\d+-.+$' ENG-123-add-user
```

Real output:

```text
PASS   ENG-123-add-user
1 checked, 1 passed, 0 failed
```

Use a config file (the bundled `examples/config.json` holds the
defaults):

```sh
python3 src/branch_name_checker.py --config examples/config.json --file examples/branches.txt
```

The output is the same as the file check above. A config file is
JSON with `pattern`, `allow`, and `max_length`:

```json
{"allow":["main","master","develop"],"max_length":50,"pattern":"^(feature|fix|docs|chore|refactor|hotfix|release)/[a-z0-9][a-z0-9._-]*$"}
```

## Examples

### 1. Fail CI on a badly named branch

```sh
python3 src/branch_name_checker.py --current
echo $?
```

```text
1
```

The exit code is 1 when the current branch fails. Put the same
command in CI and the build fails until the branch is renamed.
With a good branch name the same command prints `PASS` and
exits 0.

### 2. A name git itself would reject

```sh
python3 src/branch_name_checker.py 'feature//x'
```

```text
FAIL   feature//x: a branch name cannot contain '//'
1 checked, 0 passed, 1 failed
```

The reason names the git rule, not the pattern — so you know
the name is invalid for git, not just off-pattern.

### 3. Your team's own pattern in a config file

```sh
python3 src/branch_name_checker.py --config examples/config.json --file examples/branches.txt
```

```text
PASS   feature/add-login
PASS   fix/crash-on-start
PASS   docs/readme
FAIL   BadBranchName: does not match the pattern
FAIL   feature/: a branch name cannot start or end with '/'
FAIL   hotfix: does not match the pattern
PASS   feature/add_login-and-tests
PASS   chore/clean-up-old-code
PASS   main
9 checked, 6 passed, 3 failed
```

One config file, shared in the repo, gives every developer and
every CI run the same rule.

## How it is tested

```sh
python3 tests/test_branch_name_checker.py
```

52 tests, standard library `unittest` only — no third-party
packages. They cover: the git-validity rules (empty names,
slashes, `..`, `@{`, `.lock`, forbidden characters, control
characters), the default pattern (passes and failures, allow
list, max length, custom patterns), the config file (good and
bad: bad JSON, bad regex, wrong types, missing file), the CLI
(file, stdin, positional names, `--git` and `--current` in a
real temporary git repo, `--git` outside a repo, two input
sources, empty input, bad flags), the bundled examples (the
committed `examples/sample-output.txt` is compared against a
fresh run, the example script, and every line the README quotes
is checked against the real output), and a check that the code
and the tests import standard library only.

The bundled example is a real run, not made-up output:

```sh
sh examples/run-example.sh
```

It checks the sample list, one good and one bad name, and the
same list with the example config. The check runs exit 1 on
purpose, because three example names fail — that is the expected
result here.

## Contributing

Small, focused improvements are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

Built from scratch for this repo. The git-validity rules follow
`git check-ref-format` as documented by git; no code was copied
from any existing branch checker.
