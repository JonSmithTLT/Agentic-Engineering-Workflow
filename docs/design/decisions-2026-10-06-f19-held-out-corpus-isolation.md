# Designer decision of 2026-10-06: held-out corpus isolation for M4-H (F19)

**Status:** Decision record, governing. **Adopted** by the designer on 2026-10-06. It answers the F19 decisions-due item
(how the model arms keep a held-out corpus out of reach while the model runs) and needs no further design document. §1
is the decision recorded as given; §2 says where it is filed and what it means for the evaluation harness as built.

## 1. The decision, recorded as given

> **F19 — CLOSE / ADOPT AS M4-H EXPERIMENT PROTOCOL**
>
> This is not an AEW architecture question. It is an M4-H experimental-validity requirement.
>
> The requirement is:
>
> Held-out corpus material that has not yet been assigned to a trial must not be readable by any model-controlled
> process in either experimental arm.
>
> For M4-H, satisfy that by keeping the private corpus off the model-controlled arm hosts entirely.
>
> The evaluation/operator side retains the corpus and releases only the selected task material at that trial's defined
> start boundary.
>
> Conceptually:
>
> ```
> private held-out corpus
>     |
>     | evaluator selects task
>     v
> selected task material
>     |
>     +--> raw arm
>     |
>     +--> AEW arm
> ```
>
> Neither arm may access unreleased tasks.
>
> This avoids making experimental validity depend on perfect filesystem masking, F23 two-account deployment, F28
> network containment, Windows containment, or other production-hardening mechanisms.
>
> Those mechanisms remain independently useful security work, but they are not prerequisites for M4-H corpus isolation.
>
> Once a task is released, both arms may of course access whatever files/context are legitimately part of that task.
>
> No AEW product feature is required for F19 unless the evaluation harness lacks a way to stage one selected task at a
> time.
>
> Disposition: F19 is closed for design purposes. Treat it as an M4-H experiment-protocol requirement, not a new AEW
> architecture surface.

## 2. Filing (lead developer)

- **Register.** F19 records the protocol requirement and drops "the model arms must meet the same bar while the model
  runs", which this decision replaces for corpus isolation. The F19 decisions-due item is removed. F23 and F28 are
  unchanged: they stay security work and are no longer cited as M4-H prerequisites. Ledger prefix HOC.
- **The evaluation harness does lack the staging, so it gains it (evaluation work, not an AEW product feature).** The
  runner as built (`eval/aew_eval/runner.py`, F19 slices 2 and 3) builds the case's fixture, runs the arm and scores it in
  one process on one host, and that host holds the hidden root, because the oracle and the held-out fixtures are read
  there. Under this decision the arm must run on a host that holds no corpus. So the runner splits in two:
  - **the evaluator side** keeps the corpus, the preregistration, the attempt ledger and the oracle; it selects the
    cell's task, registers the attempt, and releases only that task's material (its fixture snapshot, its task
    statement and the arm's pinned configuration, never an oracle or another case) at the trial's start;
  - **the arm host** receives the released material, runs the arm, and returns the final work tree, which the evaluator
    side scores as today.

  This comes before the `aew` and `raw` arms run any held-out case, and it is the next F19 slice with the arms.
- **What "off the arm host" has to mean (lead developer's reading, for the operator).** The corpus lives in the
  private repository on the operator's workstation. A WSL distribution on a Windows workstation mounts the Windows
  drives under `/mnt/` by default, and a virtual machine can reach a shared folder, so neither is corpus-free just
  because the corpus is not in its home directory. An arm host is corpus-free only when no copy of the corpus is on it
  and none is mounted or shared into it. The arm host's setup records how that holds (for example a virtual machine
  with no shared folder, or a WSL distribution with automount off), and the runner checks that the hidden root is not
  reachable from the arm host before it releases a task.
