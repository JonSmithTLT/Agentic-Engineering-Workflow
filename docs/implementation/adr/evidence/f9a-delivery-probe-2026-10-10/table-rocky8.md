| host | run | input | delivery | posted | step end | delivered (event) | REST 200 | after step end | model requests in between | running tool | requests |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rocky8-bwrap | p1-queue-model-1 | Q1 | queue | 5.606 | 16.594 | 16.715 | 16.717 | 0.121 | 1 | - | 3 |
| rocky8-bwrap | p1-queue-model-2 | Q1 | queue | 5.598 | 16.596 | 16.706 | 16.727 | 0.11 | 1 | - | 3 |
| rocky8-bwrap | p1-queue-model-multi-1 | Q1 | queue | 5.761 | 16.762 | 17.018 | 17.085 | 0.256 | 3 | - | 5 |
| rocky8-bwrap | p1-queue-model-multi-2 | Q1 | queue | 5.878 | 16.875 | 17.103 | 17.208 | 0.228 | 3 | - | 5 |
| rocky8-bwrap | p1-queue-shell-1 | Q1 | queue | 7.018 | 32.004 | 32.091 | 32.196 | 0.087 | 1 | session.tool.success | 3 |
| rocky8-bwrap | p1-queue-shell-2 | Q1 | queue | 6.828 | 31.814 | 31.943 | 31.972 | 0.129 | 1 | session.tool.success | 3 |
| rocky8-bwrap | p1-queue-shell-multi-1 | Q1 | queue | 7.637 | 32.598 | 32.808 | 32.811 | 0.21 | 3 | session.tool.success | 5 |
| rocky8-bwrap | p1-queue-shell-multi-2 | Q1 | queue | 7.06 | 32.021 | 32.213 | 32.272 | 0.192 | 3 | session.tool.success | 5 |
| rocky8-bwrap | p2-steer-model-1 | Q1 | steer | 5.714 | 16.717 | 16.796 | 16.796 | 0.079 | 0 | - | 2 |
| rocky8-bwrap | p2-steer-model-2 | Q1 | steer | 5.589 | 16.586 | 16.651 | 16.701 | 0.065 | 0 | - | 2 |
| rocky8-bwrap | p2-steer-model-multi-1 | Q1 | steer | 5.785 | 16.785 | 16.855 | 16.913 | 0.07 | 0 | - | 4 |
| rocky8-bwrap | p2-steer-model-multi-2 | Q1 | steer | 5.696 | 16.727 | 16.8 | 16.857 | 0.073 | 0 | - | 4 |
| rocky8-bwrap | p2-steer-parallel-1 | P1 | steer | 6.898 | 31.865 | 31.908 | 31.997 | 0.043 | 0 | session.tool.success | 3 |
| rocky8-bwrap | p2-steer-parallel-2 | P1 | steer | 6.764 | 31.724 | 31.764 | 31.894 | 0.04 | 0 | session.tool.success | 3 |
| rocky8-bwrap | p2-steer-shell-1 | Q1 | steer | 6.973 | 31.923 | 31.97 | 32.029 | 0.047 | 0 | session.tool.success | 2 |
| rocky8-bwrap | p2-steer-shell-2 | Q1 | steer | 6.774 | 31.757 | 31.804 | 31.935 | 0.047 | 0 | session.tool.success | 2 |
| rocky8-bwrap | p2-steer-shell-multi-1 | Q1 | steer | 6.787 | 31.76 | 31.806 | 31.92 | 0.046 | 0 | session.tool.success | 4 |
| rocky8-bwrap | p2-steer-shell-multi-2 | Q1 | steer | 6.905 | 31.894 | 31.947 | 31.947 | 0.053 | 0 | session.tool.success | 4 |
| rocky8-bwrap | p2-steps-steer-1 | Q1 | steer | 6.957 | 9.939 | 9.988 | 10.065 | 0.049 | 0 | session.tool.success | 5 |
| rocky8-bwrap | p2-steps-steer-2 | Q1 | steer | 6.928 | 9.927 | 9.975 | 10.035 | 0.048 | 0 | session.tool.success | 5 |

| host | run | delivered order | statuses | turn | exit |
|---|---|---|---|---|---|
| rocky8-bwrap | p3a-held-1 | H1 > H2 | H1=200, H2=200 | ended | 0 |
| rocky8-bwrap | p3a-held-2 | H1 > H2 | H1=200, H2=200 | ended | 0 |
| rocky8-bwrap | p3a-held-steer-1 | H1 > H2 | H1=200, H2=200 | ended | 0 |
| rocky8-bwrap | p3a-held-steer-2 | H1 > H2 | H1=200, H2=200 | ended | 0 |
| rocky8-bwrap | p3b-closing-after-1 | C2 | C2=200 | ended | 0 |
| rocky8-bwrap | p3b-closing-after-2 | C2 | C2=200 | ended | 0 |
| rocky8-bwrap | p3b-closing-inflight-1 | C1 | C1=200 | ended | 0 |
| rocky8-bwrap | p3b-closing-inflight-2 | C1 | C1=200 | ended | 0 |
| rocky8-bwrap | p3b-closing-inflight-steer-1 | C1 | C1=200 | ended | 0 |
| rocky8-bwrap | p3b-closing-inflight-steer-2 | C1 | C1=200 | ended | 0 |
| rocky8-bwrap | p3c-busy-noresume-1 | B1 | B1=200 | ended | 0 |
| rocky8-bwrap | p3c-busy-noresume-2 | B1 | B1=200 | ended | 0 |
| rocky8-bwrap | p3c-idle-noresume-1 | R1 > R2 | R1=200, R2=200 | ended | 0 |
| rocky8-bwrap | p3c-idle-noresume-2 | R1 > R2 | R1=200, R2=200 | ended | 0 |
| rocky8-bwrap | p3c-idle-noresume-steer-1 | R1 > R2 | R1=200, R2=200 | ended | 0 |
| rocky8-bwrap | p3c-idle-noresume-steer-2 | R1 > R2 | R1=200, R2=200 | ended | 0 |
| rocky8-bwrap | p4-five-queue-1 | O1 > O2 > O3 > O4 > O5 | O1=200, O2=200, O3=200, O4=200, O5=200 | ended | 0 |
| rocky8-bwrap | p4-five-queue-2 | O1 > O2 > O3 > O4 > O5 | O1=200, O2=200, O3=200, O4=200, O5=200 | ended | 0 |
| rocky8-bwrap | p4-five-steer-1 | S1 > S2 > S3 > S4 > S5 | S1=200, S2=200, S3=200, S4=200, S5=200 | ended | 0 |
| rocky8-bwrap | p4-five-steer-2 | S1 > S2 > S3 > S4 > S5 | S1=200, S2=200, S3=200, S4=200, S5=200 | ended | 0 |
| rocky8-bwrap | p4-mixed-1 | M2s > M4s > M1q > M3q > M5q | M1q=200, M2s=200, M3q=200, M4s=200, M5q=200 | ended | 0 |
| rocky8-bwrap | p4-mixed-2 | M2s > M4s > M1q > M3q > M5q | M1q=200, M2s=200, M3q=200, M4s=200, M5q=200 | ended | 0 |
| rocky8-bwrap | p5-duplicate-1 | X-1 | X-1=200, X-2-same=200, X-3-changed=200, X-4-after-delivery=200, X-5-other-session=409, X-6-assistant-id=409, X-7-idle-id=409, X-8-no-session=404, X-9-bad-id=400 | ended | 0 |
| rocky8-bwrap | p5-duplicate-2 | X-1 | X-1=200, X-2-same=200, X-3-changed=200, X-4-after-delivery=200, X-5-other-session=409, X-6-assistant-id=409, X-7-idle-id=409, X-8-no-session=404, X-9-bad-id=400 | ended | 0 |
| rocky8-bwrap | p6-render-1 | F1 | F1=200 | ended | 0 |
| rocky8-bwrap | p6-render-2 | F1 | F1=200 | ended | 0 |
| rocky8-bwrap | p7-kill-1 |  | K1=200 | ended | -9 |
| rocky8-bwrap | p7-kill-2 |  | K1=200 | ended | -9 |

| host | run | shell started | tool result at | duration | end marker | result |
|---|---|---|---|---|---|---|
| rocky8-bwrap | p9-120-1 | 2.531 | 122.591 | 120.06 | absent |  if the command is expected to take longer.Timed out before completion |
| rocky8-bwrap | p9-120-2 | 1.981 | 122.095 | 120.114 | absent |  if the command is expected to take longer.Timed out before completion |
| rocky8-bwrap | p9-300-1 | 2.807 | 122.907 | 120.1 | absent |  if the command is expected to take longer.Timed out before completion |
| rocky8-bwrap | p9-300-2 | 2.89 | 122.962 | 120.072 | absent |  if the command is expected to take longer.Timed out before completion |
| rocky8-bwrap | p9-300-t360-1 | 2.226 | 302.345 | 300.119 | written | slept 300 s (a)  |
| rocky8-bwrap | p9-300-t360-2 | 2.174 | 302.256 | 300.082 | written | slept 300 s (a)  |
| rocky8-bwrap | p9-600-1 | 1.997 | 122.061 | 120.064 | absent |  if the command is expected to take longer.Timed out before completion |
| rocky8-bwrap | p9-600-2 | 2.086 | 122.158 | 120.072 | absent |  if the command is expected to take longer.Timed out before completion |
| rocky8-bwrap | p9-600-t0-1 | 1.936 | 602.049 | 600.113 | written | slept 600 s (a)  |
| rocky8-bwrap | p9-600-t0-2 | 2.032 | 602.201 | 600.169 | written | slept 600 s (a)  |
| rocky8-bwrap | p9-killcheck-1 | 2.067 | 122.135 | 120.068 | absent |  if the command is expected to take longer.Timed out before completion (last heartbeat 117.2 s) |
| rocky8-bwrap | p9-killcheck-2 | 2.066 | 122.128 | 120.062 | absent |  if the command is expected to take longer.Timed out before completion (last heartbeat 117.183 s) |
