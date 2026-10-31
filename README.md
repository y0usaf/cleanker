# cleanker

Removes comments and unreferenced prose from source trees, then keeps them gone.

One rule, applied uniformly: source carries no comments except machine-read directives
(`#!`, `# noqa`, `@ts-expect-error`, `// SAFETY:`, licences, bundler pragmas) and doc
comments, and a repository's only prose files are `README*` and `AGENTS.md`, plus any
markdown a build, test, or CI configuration actually reads.

## Commands

```
cleanker dry-run [PATH...]     report what would change; --check exits 1 when work is pending
cleanker clean   [PATH...]     rewrite files in place
cleanker status                which repositories are policed, and why
cleanker enroll  [PATH...]     set cleanker.policy=true on a clone
cleanker disenroll [PATH...]   set cleanker.policy=false
cleanker hook                  the git pre-commit entry point
```

Paths default to the current repository. `clean` never commits.

## How a repository becomes policed

| Rule | Source |
| --- | --- |
| `cleanker.policy=true/false` in the clone | local git config, wins outright |
| `origin` owner listed in `cleanker.owners` | global git config |
| no `origin`, checkout under `cleanker.roots` | global git config |

## What it will not touch

Doc comments, machine-read directives, legal notices, markdown referenced by a build
or CI file, vendored trees, and repositories the ladder above does not select.

## Packages

| Path | What it is |
| --- | --- |
| `cleanker.py` | the tool, Python 3, no dependencies beyond itself and `ast-grep` |
| `pi-cleanker/` | pi harness extension: cleans the workspace at `agent_end` |
| `omp-cleanker/` | omp harness extension, same shape |

## License

AGPL-3.0-only. See [LICENSE](./LICENSE).
