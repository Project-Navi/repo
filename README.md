# navi-bootstrap

Jinja2 rendering engine and template packs for bootstrapping projects to navi-os-grade posture.

```bash
# Apply base pack to existing project
nboot apply --spec project.json --pack ./packs/base --target ./my-project

# Render a new project from spec
nboot render --spec project.json --pack ./packs/base --out ./my-project
```
