<!-- Thanks for contributing! Keep PRs focused and secrets out of diffs/fixtures. -->

## What & why

<!-- What does this change, and what problem does it solve? Link any related issue. -->

## Checklist

- [ ] `make lint` passes (`go vet` + web lint)
- [ ] `make test` passes (`go test ./...` + web build)
- [ ] New/changed logic in `internal/azure` or `internal/server` has tests (coverage ≥ 70%)
- [ ] CLI flow changes have a `teatest` interaction test
- [ ] No secrets, real tenant/subscription IDs, or tokens in code, tests, or fixtures
- [ ] Commit messages follow Conventional Commits
- [ ] CHANGELOG.md updated under `[Unreleased]` if user-facing
