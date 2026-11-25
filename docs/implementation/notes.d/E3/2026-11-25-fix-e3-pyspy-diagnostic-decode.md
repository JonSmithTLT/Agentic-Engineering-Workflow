The first attempt of validation-selector PR #570 stopped the Linux adversarial lane during a periodic worker
snapshot. `py-spy dump` emitted a malformed UTF-8 byte. Python's strict text-mode subprocess decoding raised
`UnicodeDecodeError` out of the sampler and the lane supervisor exited. Assurance subsequently reported required
tests that never ran, and the evidence check reported that the death had no kind marker.

The existing `py-spy` attach boundary now decodes UTF-8 diagnostic streams with replacement. Readable stack
frames still go through the existing evidence parser. A failed command still reports only its exit and OS error
codes. The regression uses real subprocess pipes with malformed bytes on stdout and stderr in separate cases.

[Original lane](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/45592084186/job/139131318240) ·
[Assurance](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/45592084186/job/139162979020) ·
[Evidence check](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/45592084090/job/139163981119)
