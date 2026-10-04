# W05 independent review corrections

The independent main-line review of source `405c836` completed the investigation on desktop and phone and requested changes for F1/F2, with F3/F4 as minor UI findings. The reviewer independently rebuilt and re-checked `e875e81` and recorded **ACCEPT** for all four fixes, conditional on regenerating the incorrectly attributed correction evidence. That condition is fulfilled by the clean detached-commit rebuild and browser evidence in `web/docs/w05-review-fixes-evidence/`. The report and its supplied screenshots are archived in `web/docs/w05-independent-review/`; implementer tests do not replace the independent review.

| Finding | Implemented correction | Regression evidence |
|---|---|---|
| F1: story result vocabulary | Story Evidence uses accepted lowercase `fail`/`pass`. An explicit `FUTURE_RESULT` remains in the unknown case. Evidence IDs, artifact hashes and existing Journal/Investigation wire models remain unchanged. | Canonical vocabulary unit test and all three story records exercised through the UI. |
| F2: artifact mount steals tab focus | Only an explicit artifact pick or phone Detail action requests heading focus. Returning to Artifacts through the tabs does not request focus. The request is consumed when the selected detail mounts. | With a preselected artifact: Right/Left/Home/End retain the selected tab's focus after data loads. Explicit artifact picking still focuses its heading. Desktop/phone, worker/HTTP paths. |
| F3: duplicate binding error | A shared list/selected-artifact validation failure has one visible alert and Retry action, placed outside the phone's hidden list. Retry revalidates both failed requests. Distinct errors remain separately visible. | One alert and Retry for binding-mismatch on desktop and phone. |
| F4: absent artifact called off-page | A failed selected-artifact lookup says `unavailable`. The off-page note requires a successfully supplied selected association. | Missing-artifact deep link reports unavailable, never off-page, on desktop and phone. |

The review packet now explains Ubuntu WSL's native Docker builder and the stateful HTTP refresh-failure scenarios. The optional whole-artifact coverage note was not added: the existing byte range and separately labeled integrity statements remain accurate.

The original frozen evidence remains historical at `web/docs/w05-evidence/`. Current correction source, commands, results, screenshots and hashes are recorded separately in `web/docs/w05-review-fixes-evidence/`. The preview schema digest remains unchanged; the fixture manifest changes because story result values were corrected.

The re-review is complete. Current frontend acceptance is recorded in `web/docs/w05-frontend-acceptance.json`. Backend adoption and live integration remain separately pending. W04 acceptance remains preserved.
