# CLAUDE.md — bfwp-spec

## What this is
Design docs and contracts for the Bella Flora Water Project. No application code except
`tools/validate.py`.

## Rules
- This repo **defines** contracts; other repos consume them. A change here can break four
  apps — keep changes deliberate, explained, and logged in `CHANGELOG.md`.
- Every schema change needs a matching example in `contracts/examples/v1/` and a passing
  `python3 tools/validate.py`.
- Keep docs and schemas consistent: if you edit a field in a schema, update
  `docs/02-message-contract.md` in the same commit.
- Breaking changes bump the major version (`v2` folders); never silently edit `v1` once tagged.
- Unresolved decisions go in `docs/open-questions.md`, not buried in prose.
