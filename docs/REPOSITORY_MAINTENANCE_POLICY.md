# Repository Maintenance Policy

This policy keeps Project Field Mouse easy to navigate without sacrificing recoverable
work or release history. When ownership or purpose is uncertain, preserve the item and
record a decision request before cleanup.

## Primary repository and workspace

- Keep one canonical clone at `Workspaces/project-field-mouse`, normally on `master`.
- Keep unrelated projects in separate top-level directories.
- Use auxiliary worktrees only for concurrent active work. Do not create a second full
  clone when a worktree provides the required isolation.
- Name worktree directories `project-field-mouse-<purpose>` and remove them after their
  branch is merged or deliberately archived.
- Temporary clones belong in an explicitly named temporary location. Record their
  purpose and delete them when the task ends after confirming they contain no unique
  commits or uncommitted files.

## Branch lifecycle

1. Start work from an up-to-date `master` unless a release owner identifies another
   base.
2. Give each branch one documented purpose and owner.
3. Push or otherwise archive any branch whose unique commits must survive loss of the
   local clone.
4. Merge through the normal review and validation process.
5. Delete local and remote branches after verifying the branch tip is an ancestor of
   its target branch and no worktree uses it.

Never delete a branch solely because of age. Preserve branches with unique commits,
uncertain ownership, active review, unreleased work, or unresolved deployment value.

## Branch naming

Use lowercase, hyphenated descriptions with one of these prefixes:

- `feature/<purpose>` for user-facing or platform capability work.
- `fix/<purpose>` for defects.
- `docs/<purpose>` for documentation-only work.
- `admin/<purpose>` for repository and release administration.
- `refactor/<purpose>` for behavior-preserving code cleanup.
- `release/<version>` only while coordinating a release that requires a branch.
- `experiment/<purpose>` for explicitly disposable investigation.

Avoid personal names, generic labels such as `test`, and versionless `integration`
branches whose end condition is unclear.

## Worktrees

- Before removal, verify `git status --porcelain` is empty, including intended ignored
  state, and confirm the branch has no unique work requiring preservation.
- Remove worktrees with `git worktree remove`; do not delete their directories first.
- Run `git worktree prune` after confirmed removals.
- Virtual environments, caches, runtime data, and credentials in a worktree are local
  artifacts and must never be committed.
- Keep the canonical clone as the shared Git object database while any linked worktree
  exists.

## Releases and tags

- Tags are permanent release-history records. Do not move or delete a published tag
  without explicit HQ authorization.
- Use release branches only when stabilization must continue separately from `master`.
- After release, merge the final release branch, verify its tip is contained in
  `master`, then delete the branch locally and remotely.
- Keep validation evidence and release reports under `docs/`; reorganize them only with
  link updates. Do not treat historical evidence as temporary output.

## Archives

- Prefer Git history, tags, and release artifacts over tracked source-tree snapshots.
- Do not commit timestamped copies of source or generated dashboards as informal
  backups.
- If an artifact has continuing audit value, place it under a clearly named release or
  evidence directory with a short README describing origin, retention, and owner.
- Large editable design sources should have an explicit repository policy or external
  artifact home; do not mix them into production assets without review.

## `.gitignore` expectations

- Ignore interpreter caches, virtual environments, test/lint/type-check caches, build
  output, editor metadata, local secrets, databases, recordings, logs, and temporary
  backup files.
- Keep rules repository-local for tools used by the project; do not rely on one
  developer's global ignore file.
- Do not broadly ignore formats such as JSON, CSV, PNG, or Markdown because the
  repository intentionally tracks fixtures, migrations, evidence, and public assets.
- Before adding a file, use `git check-ignore -v <path>` when its status is surprising.

## Scheduled hygiene

After each release and at least quarterly:

1. Fetch/prune remote state and inventory branches, tags, stashes, and worktrees.
2. Confirm every unmerged branch has a purpose and preservation decision.
3. Remove verified merged branches and retired clean worktrees.
4. Review top-level files, large tracked objects, generated artifacts, and empty
   placeholders.
5. Run tests, Ruff, compile checks, documentation-link checks, and `git fsck` after
   repository cleanup.
6. Record removals, retained exceptions, and remaining questions in a hygiene report.
