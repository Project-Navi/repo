# Elective Packs Design

Date: 2026-02-25

## Build Order

1. **security-scanning + github-templates** — low complexity, high value, independent
2. **review-system, quality-gates, code-hygiene** — sweep remaining low-complexity packs
3. **release-pipeline** — last, highest complexity (Docker conditionals, SBOM, git-cliff)

## Design Pattern

All elective packs follow the base pack pattern:
- `packs/<name>/manifest.yaml` — engine + agent-workflow fields
- `packs/<name>/templates/` — Jinja2 templates
- Hybrid defaults via `| default()` — zero spec changes required for basic use
- `dependencies: [base]` — base pack runs first

## Pack 1: security-scanning

```
packs/security-scanning/
├── manifest.yaml
└── templates/
    └── workflows/
        ├── codeql.yml.j2
        └── scorecard.yml.j2
```

- **CodeQL**: language matrix from `spec.recon.codeql_languages | default([spec.language])`, triggers on push/PR/weekly, permissions locked to minimum
- **Scorecard**: runs on ubuntu-latest, `spec.recon.scorecard_publish | default(false)` for public repo opt-in
- **Action SHAs**: github/codeql-action (init, autobuild, analyze), ossf/scorecard-action, actions/upload-artifact, plus checkout + harden-runner
- **Conditions**: both conditional on `spec.features.ci`

## Pack 2: github-templates

```
packs/github-templates/
├── manifest.yaml
└── templates/
    ├── ISSUE_TEMPLATE/
    │   ├── config.yml.j2
    │   ├── bug-report.yml.j2
    │   └── feature-request.yml.j2
    └── PULL_REQUEST_TEMPLATE.md.j2
```

- **Bug report**: description, reproduction steps, expected/actual, environment. Category dropdown from `spec.github.bug_categories | default(["Bug", "Performance", "Security", "Documentation", "Developer Experience"])`
- **Feature request**: problem, solution, alternatives, contribution. Categories from `spec.github.feature_categories | default(["New Feature", "Enhancement", "Integration", "Developer Experience", "Documentation"])`
- **PR template**: checklist with spec-aware lint/test commands, type-of-change checkboxes
- **Config**: `blank_issues_enabled: false`, optional docs URL from `spec.github.docs_url`
- **No action SHAs, no conditions** — all templates always render

## Reference

- Base pack pattern: `packs/base/manifest.yaml`
- navi-os reference: `/home/ndspence/GitHub/navi-os/.github/`
- Unified design: `docs/plans/2026-02-25-unified-design.md`
