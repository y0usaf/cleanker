# cleanker

Removes comments, Python docstrings, unreferenced markdown prose, and (when opted in) provably-unit tests, and enforces that policy at `pre-commit` and `pre-push`.

## Dependencies

- Python 3
- `ast-grep` on `PATH` (or built via `nix` on demand)
- `git`

## Commands

- `cleanker dry-run [PATH...]` — preview changes (`--check` exits 1 if changes are pending, `--file PATH`, `--format`, `--force`, `--strip-tests`)
- `cleanker clean [PATH...]` — rewrite files in place
- `cleanker status` — list enforced and unenforced repositories under `~/dev`
- `cleanker enroll [PATH...]` / `cleanker disenroll [PATH...]` — set or unset `cleanker.policy`
- `cleanker hook` / `cleanker pre-push` — git hook entry points (`CLEANKER_SKIP=1` or `--no-verify` bypasses)

## Configuration

- `cleanker.policy` (`true`/`false`) — local or global enrollment toggle
- `cleanker.owners` — origin owners enrolled automatically
- `cleanker.roots` — local root paths for repositories without `origin`
- `cleanker.strip-tests` (`true`/`false`) — opt-in removal of provably-unit tests
- `.cleankerignore` — per-repository glob exclusions
