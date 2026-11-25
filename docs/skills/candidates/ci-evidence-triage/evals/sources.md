# Sources and synthesis

Evaluator-only. Primary sources inspected 2026-10-12; live links can change. Original synthesis, not a market ranking. External skills were research inputs; their installers, tools and orchestration instructions were not executed. Freeze source snapshots and candidate bytes for comparisons.

- [OpenAI gh-fix-ci](https://github.com/openai/skills/blob/main/skills/.curated/gh-fix-ci/SKILL.md): retain concrete check/log inspection; omit its separate fix/approval workflow because this skill observes within existing authority.
- [GitHub CLI run view](https://cli.github.com/manual/gh_run_view): explicit attempts/jobs and metadata separate from logs; a CLI success is not CI qualification.
- [Workflow jobs API](https://docs.github.com/en/rest/actions/workflow-jobs): attempt-specific identity and pagination; do not treat one page as the full matrix.
- [Workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs): attempt archives and redirects; omit automatic mutations and credential collection.
- [Rerun semantics](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs): reruns preserve original event SHA/ref; they do not test a later push.

The supplied Lead evidence packet motivates these hypotheses. It is retrospective, not a controlled trial of this candidate. No project-specific incidents, role states or private identities are copied into runtime guidance.
