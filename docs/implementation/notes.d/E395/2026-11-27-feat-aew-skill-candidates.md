# Frontend Engineer role proposal for designer sign-off

Proposed card version 1. Staff this implementer for scoped web UI work with
material visual, interaction, accessibility, or design system requirements.
Its implementation follows the accepted Ticket plan and maintained design and
API contracts. The designer can approve or revise the staffing boundary,
capabilities, and foundational skill fit before installation.

```yaml
schema: aew/role/v1
role: frontend_engineer
display_name: Frontend Engineer
version: 1
extends: implementer
purpose: Implement or refine web interfaces within an accepted Ticket and the project's design and behavior contracts.
use_when:
  - the Ticket materially changes web UI layout, interaction, accessibility, or design system components
responsibilities:
  - follow the project's design system, accessibility requirements, and accepted API and behavior contracts
  - use project-supported checks for changed behavior, normal interaction states, and relevant accessibility requirements
  - report browser checks as not run with the reason when the necessary capability or preview is unavailable
skills: [frontend-design]
required_capabilities: [exact_code_search, source_mutation, targeted_test_execution]
optional_capabilities: [browser_testing]
outputs: [implementation_report]
```

This extends the existing implementer archetype and adds no operations.
The ordinary implementation capabilities remain required. Browser access
and preview access come from project execution policy. The optional browser
capability requires an available display or headless driver and authorized
network access to the preview when the task needs it. Browser tooling and MCP
are deployment decisions. Complete available checks when browser verification
is unavailable and report the affected checks as “not run” with a reason.

The proposed candidate is [frontend-design 0.3.1](../../../skills/candidates/frontend-design/SKILL.md).
Its entrypoint is 8,375 UTF-8 bytes, with 25,644 bytes in the full runtime
bundle including Apache 2.0 terms. Its evidence guidance covers visual checks,
responsive layout, behavior, and accessibility. See the candidate's
[research notes](../../../skills/candidates/frontend-design/evals/sources.md).

**What remains.** After sign-off, validate the card, explicitly rehash and package the approved
candidate, and render the Lead guide. Measure the messaging-on and
messaging-off Lead context pools against 40,000 bytes and the operator
reserve, and include the staffing delta in the installation pull request.
Verify the card can be selected, loaded, and report a browser check as not run
in a contained environment that lacks it. E395 stays open pending the designer's decision.
