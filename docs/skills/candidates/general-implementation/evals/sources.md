# General implementation sources

Consulted 2026-11-27. The accepted AEW Ticket, plan and execution policy
supply local criteria and commands.

| Public primary source | Adopted practice and fit | Adaptation |
| --- | --- | --- |
| [Google Engineering Practices, Small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html), live on the consultation date | Keep each coherent change small enough to check and review. Include the tests for that behavior so a reviewer can assess the change as a unit. | Keep jointly required changes together when a partial change would break a contract. AEW retains its own review and gate policy. |
| [GitHub spec-kit checklist](https://github.com/github/spec-kit/blob/main/templates/checklist-template.md) and [Agent Skills specification](https://agentskills.io/specification), live on the consultation date | Translate requirements into checkable outcomes. Put the essential implementation procedure in the entrypoint with detail behind one link. | Consume AEW's accepted plan. No new plan workflow, commands, or mandatory checklist artifact. |
