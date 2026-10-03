# W02-1 fixing diff and retest

Disposition: fixed locally; Lead diff check and green PR CI remain required for W02 frontend acceptance. Live integration remains F20.2–F20.6.

Source freeze: `7a18fa3a17b0d9d8d28732663e9e1df9b140c4cc` on `feat/aew-dashboard-w02`. Review only this source fix with `git diff b9c233a 7a18fa3`; the original frozen W02 source was `0e64b31`. The [main-line review](w02-review-main-line.md) is retained unchanged.

History `depends_on` and `moved_to` targets now resolve as Work, so explicit expansion requests `/work/{id}` for hot or archived work. `audit_finding` remains History; invocations, evidence and terminal references retain their mappings. The current-projection/historical-snapshot warning remains unchanged.

Graph Work anchors open `/work?selected={id}`. Crossing from History retains demo identity but drops the History filters and selection; other entity destinations retain their existing behavior.

The composed regression expands both a dependency and a moved-to hot parent, asserts Work requests and absence of History requests for those targets, checks audit-finding classification, and follows the parent's Work workspace anchor. The compiled-browser regression expands F3's hot `S-0001`, confirms its loaded Work projection and request route, and follows its anchor into the workspace.

## Verification

- Final offline Node 22 gate: empty modules, networking disabled, 395-package install, accepted-contract/generated-artifact consistency, typecheck, lint, **117 tests in 14 files**, production mock exclusion, production and demo builds: PASS.
- Compiled W02 browser checks: **10 groups**, including the new hot-parent regression: PASS.
- Existing W01 browser checks: **16 groups**: PASS.
- Contract 0.1.2 digest and dependency lock remain unchanged. No Engine suite or real-server acceptance is claimed. No workflow changes are included in this fixing diff.

Reports, offline command log, browser command log, screenshot and source/build identities are retained in [review-fix evidence](w02-review-fixes-evidence/result.json). Original W02 evidence is preserved separately.

The first browser regression attempt loaded the correct Work projection but timed out on its anchor after a full-page screenshot; that capture reset the inspector graph. Moving the capture after navigation allowed the actual pointer-click flow to pass. The failed report and trace are retained, rather than suppressing the failure.

Commands, from the repository root unless stated otherwise:

```bash
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh
# From web/, using the staged host Node launcher and pinned Chromium:
W02_BROWSER_OUTPUT=output/playwright-w02-review-fix W02_DEMO_PORT=4224 W02_PRODUCTION_PORT=4225 /home/jon/.local/bin/node scripts/browser-w02.mjs
W01_BROWSER_OUTPUT=output/playwright-w02-review-fix-w01 W01_DEMO_PORT=4226 W01_PRODUCTION_PORT=4227 /home/jon/.local/bin/node scripts/ci-browser.mjs
```

Local execution used the existing permission-authorized Docker/browser path. Git worktree metadata was restored to the existing W02 branch after its administrative directory was missing; no main checkout files or running Engine tests were changed. The branch has not been pushed and GitHub CI has not been run by this fix.
