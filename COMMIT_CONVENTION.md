# Commit Message Convention

This project follows Conventional Commits (https://www.conventionalcommits.org/).

## Format

    <type>(<scope>): <short summary>

## Types

| Type       | When to use                              |
|------------|------------------------------------------|
| feat       | New feature                              |
| fix        | Bug fix                                  |
| refactor   | Code change that is neither fix nor feat |
| test       | Adding or fixing tests                   |
| chore      | Build process, dependency updates        |
| docs       | Documentation only                       |
| style      | Formatting, no logic change              |
| perf       | Performance improvement                  |

## Scopes

auth, transactions, budgets, dashboard, api, db, deps, ci

## Examples

    feat(auth): add JWT refresh token endpoint
    fix(transactions): correct negative balance calculation
    refactor(services): extract budget calculation to helper
    test(auth): add duplicate email registration test
    chore(deps): bump fastapi to 0.112.0
    docs(readme): update local dev instructions

## Rules

- Use imperative mood: "add feature" not "added feature"
- No capital first letter in summary
- No period at end of summary
- Keep summary under 72 characters
- Reference issues at the end: feat(budgets): add monthly rollover (#42)
