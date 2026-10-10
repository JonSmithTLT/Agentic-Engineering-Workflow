| host | run | input | delivery | posted | step end | delivered (event) | REST 200 | after step end | model requests in between | running tool | requests |
|---|---|---|---|---|---|---|---|---|---|---|---|
| windows | p1-queue-model-1 | Q1 | queue | 4.911 | 15.911 | 15.973 | 16.007 | 0.062 | 1 | - | 3 |
| windows | p1-queue-model-2 | Q1 | queue | 5.158 | 16.158 | 16.214 | 16.277 | 0.056 | 1 | - | 3 |
| windows | p1-queue-model-multi-1 | Q1 | queue | 5.241 | 16.241 | 16.374 | 16.374 | 0.133 | 3 | - | 5 |
| windows | p1-queue-model-multi-2 | Q1 | queue | 5.312 | 16.312 | 16.419 | 16.609 | 0.107 | 3 | - | 5 |
| windows | p1-queue-shell-1 | Q1 | queue | 6.809 | 31.827 | 31.889 | 31.988 | 0.062 | 1 | session.tool.success | 3 |
| windows | p1-queue-shell-2 | Q1 | queue | 7.727 | 32.743 | 32.804 | 32.995 | 0.061 | 1 | session.tool.success | 3 |
| windows | p1-queue-shell-multi-1 | Q1 | queue | 6.445 | 31.499 | 31.616 | 31.78 | 0.117 | 3 | session.tool.success | 5 |
| windows | p1-queue-shell-multi-2 | Q1 | queue | 6.543 | 31.542 | 31.684 | 31.843 | 0.142 | 3 | session.tool.success | 5 |
| windows | p2-steer-model-1 | Q1 | steer | 5.315 | 16.315 | 16.36 | 16.372 | 0.045 | 0 | - | 2 |
| windows | p2-steer-model-2 | Q1 | steer | 5.21 | 16.211 | 16.254 | 16.278 | 0.043 | 0 | - | 2 |
| windows | p2-steer-model-multi-1 | Q1 | steer | 5.33 | 16.33 | 16.373 | 16.492 | 0.043 | 0 | - | 4 |
| windows | p2-steer-model-multi-2 | Q1 | steer | 5.332 | 16.333 | 16.375 | 16.517 | 0.042 | 0 | - | 4 |
| windows | p2-steer-parallel-1 | P1 | steer | 8.959 | 31.95 | 31.996 | 32.032 | 0.046 | 0 | session.tool.success | 3 |
| windows | p2-steer-parallel-2 | P1 | steer | 7.268 | 31.887 | 31.933 | 32.066 | 0.046 | 0 | session.tool.success | 3 |
| windows | p2-steer-shell-1 | Q1 | steer | 6.66 | 31.686 | 31.734 | 31.857 | 0.048 | 0 | session.tool.success | 2 |
| windows | p2-steer-shell-2 | Q1 | steer | 6.88 | 31.91 | 31.955 | 32.078 | 0.045 | 0 | session.tool.success | 2 |
| windows | p2-steer-shell-multi-1 | Q1 | steer | 6.444 | 31.474 | 31.521 | 31.595 | 0.047 | 0 | session.tool.success | 4 |
| windows | p2-steer-shell-multi-2 | Q1 | steer | 6.705 | 31.725 | 31.779 | 31.879 | 0.054 | 0 | session.tool.success | 4 |
| windows | p2-steps-steer-1 | Q1 | steer | 6.822 | 9.845 | 9.893 | 9.97 | 0.048 | 0 | session.tool.success | 5 |
| windows | p2-steps-steer-2 | Q1 | steer | 6.792 | 9.817 | 9.867 | 9.955 | 0.05 | 0 | session.tool.success | 5 |

| host | run | delivered order | statuses | turn | exit |
|---|---|---|---|---|---|
| windows | p3a-held-1 | H1 > H2 | H1=200, H2=200 | ended | 0 |
| windows | p3a-held-2 | H1 > H2 | H1=200, H2=200 | ended | 0 |
| windows | p3a-held-steer-1 | H1 > H2 | H1=200, H2=200 | ended | 0 |
| windows | p3a-held-steer-2 | H1 > H2 | H1=200, H2=200 | ended | 0 |
| windows | p3b-closing-after-1 | C2 | C2=200 | ended | 0 |
| windows | p3b-closing-after-2 | C2 | C2=200 | ended | 0 |
| windows | p3b-closing-inflight-1 | C1 | C1=200 | ended | 0 |
| windows | p3b-closing-inflight-2 | C1 | C1=200 | ended | 0 |
| windows | p3b-closing-inflight-steer-1 | C1 | C1=200 | ended | 0 |
| windows | p3b-closing-inflight-steer-2 | C1 | C1=200 | ended | 0 |
| windows | p3c-busy-noresume-1 | B1 | B1=200 | ended | 0 |
| windows | p3c-busy-noresume-2 | B1 | B1=200 | ended | 0 |
| windows | p3c-idle-noresume-1 | R1 > R2 | R1=200, R2=200 | ended | 0 |
| windows | p3c-idle-noresume-2 | R1 > R2 | R1=200, R2=200 | ended | 0 |
| windows | p3c-idle-noresume-steer-1 | R1 > R2 | R1=200, R2=200 | ended | 0 |
| windows | p3c-idle-noresume-steer-2 | R1 > R2 | R1=200, R2=200 | ended | 0 |
| windows | p4-five-queue-1 | O1 > O2 > O3 > O4 > O5 | O1=200, O2=200, O3=200, O4=200, O5=200 | ended | 0 |
| windows | p4-five-queue-2 | O1 > O2 > O3 > O4 > O5 | O1=200, O2=200, O3=200, O4=200, O5=200 | ended | 0 |
| windows | p4-five-steer-1 | S1 > S2 > S3 > S4 > S5 | S1=200, S2=200, S3=200, S4=200, S5=200 | ended | 0 |
| windows | p4-five-steer-2 | S1 > S2 > S3 > S4 > S5 | S1=200, S2=200, S3=200, S4=200, S5=200 | ended | 0 |
| windows | p4-mixed-1 | M2s > M4s > M1q > M3q > M5q | M1q=200, M2s=200, M3q=200, M4s=200, M5q=200 | ended | 0 |
| windows | p4-mixed-2 | M2s > M4s > M1q > M3q > M5q | M1q=200, M2s=200, M3q=200, M4s=200, M5q=200 | ended | 0 |
| windows | p5-duplicate-1 | X-1 | X-1=200, X-2-same=200, X-3-changed=200, X-4-after-delivery=200, X-5-other-session=409, X-6-assistant-id=409, X-7-idle-id=409, X-8-no-session=404, X-9-bad-id=400 | ended | 0 |
| windows | p5-duplicate-2 | X-1 | X-1=200, X-2-same=200, X-3-changed=200, X-4-after-delivery=200, X-5-other-session=409, X-6-assistant-id=409, X-7-idle-id=409, X-8-no-session=404, X-9-bad-id=400 | ended | 0 |
| windows | p6-render-1 | F1 | F1=200 | ended | 0 |
| windows | p6-render-2 | F1 | F1=200 | ended | 0 |
| windows | p7-kill-1 |  | K1=200 | ended | 1 |
| windows | p7-kill-2 |  | K1=200 | ended | 1 |

| host | run | shell started | tool result at | duration | end marker | result |
|---|---|---|---|---|---|---|
| windows | p9-120-1 | 1.794 | 121.809 | 120.015 | absent |  if the command is expected to take longer.Timed out before completion |
| windows | p9-120-2 | 1.947 | 121.948 | 120.001 | absent |  if the command is expected to take longer.Timed out before completion |
| windows | p9-300-1 | 2.053 | 122.15 | 120.097 | absent |  if the command is expected to take longer.Timed out before completion |
| windows | p9-300-2 | 2.078 | 122.039 | 119.961 | absent |  if the command is expected to take longer.Timed out before completion |
| windows | p9-300-t360-1 | 1.886 | 301.999 | 300.113 | written | slept 300 s (a)  |
| windows | p9-300-t360-2 | 1.803 | 301.915 | 300.112 | written | slept 300 s (a)  |
| windows | p9-600-1 | 2.008 | 121.999 | 119.991 | absent |  if the command is expected to take longer.Timed out before completion |
| windows | p9-600-2 | 1.869 | 121.788 | 119.919 | absent |  if the command is expected to take longer.Timed out before completion |
| windows | p9-600-t0-1 | 1.615 | 604.962 | 603.347 | written | slept 600 s (a)  |
| windows | p9-600-t0-2 | 2.417 | 602.571 | 600.154 | written | slept 600 s (a)  |
| windows | p9-killcheck-1 | 1.664 | 121.704 | 120.04 | absent |  if the command is expected to take longer.Timed out before completion (last heartbeat 116.768 s) |
| windows | p9-killcheck-2 | 1.761 | 121.825 | 120.064 | absent |  if the command is expected to take longer.Timed out before completion (last heartbeat 116.892 s) |
