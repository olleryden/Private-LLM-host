# Private LLM Host — Plan

Moved to Vikunja on 2026-11-17. The goal, ground rules, current state,
phase roadmap, and ordered next steps now live in the self-hosted Vikunja
tracker on this PC (<http://localhost:3456>):

- **Personal Assistant** is the overall goal this PC serves. pLLM is one of
  its sub-projects, next to **Memory bank** (harness-agnostic memory, which
  took over roadmap phase 6) and **Docker management** (an overview of the
  container deployments).
- **Personal Assistant → pLLM**: the project description holds the goal,
  current state, and roadmap; the board holds the backlog, ordered by
  priority. The Kong integration starts at PLLM-1, "Implement Kong in pLLM".

Assistants read and update the board through Vikunja's MCP server; see
`~/Projects/Vikunja-selfhosted/README.md`.

The last Markdown version of this plan is in Git history:
`git show 810c982:PLAN.md`. Exact setup evidence stays in SETUP_LOG.md,
and the current architecture in ARCHITECTURE.md.
