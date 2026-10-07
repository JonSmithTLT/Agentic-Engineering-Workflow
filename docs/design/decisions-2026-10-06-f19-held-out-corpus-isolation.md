# Designer decision of 2026-10-06: held-out corpus isolation for M4-H (F19)

**Status:** Decision record, governing. **Adopted** by the designer on 2026-10-06. It answers the F19 decisions-due item
(how the model arms keep a held-out corpus out of reach while the model runs) and needs no further design document. §1
is the decision recorded as given; §2 says where it is filed and what it means for the evaluation harness as built;
§3 is the designer's arm-host rule, given the same day in answer to §2.

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
    side scores as today, with the facts only the arm host can observe: whether its AEW checkout was touched
    (`outcome.safety.checkout_untouched`) and its environment. Today the runner records both from the host it runs on,
    which after the split would be the evaluator's, so a run record would describe the wrong host.

  This comes before the `aew` and `raw` arms run any held-out case, and it is the next F19 slice with the arms.
- **What "off the arm host" means** is the designer's arm-host rule, §3. It replaces the lead developer's first reading
  (no copy and nothing mounted or shared into the arm host, checked before release), which §3 confirms and extends.

## 3. Designer clarification of 2026-10-06: the arm-host rule

Given in answer to §2's question about WSL distributions and virtual machines, and recorded as given:

> For the arm-host rule, I'd freeze this:
>
> Before a task is released, no model-controlled process in that arm may have a filesystem, mount, share,
> synchronization path, host-integration path, or other readable route to any unreleased corpus material.
>
> That matters for exactly the WSL/VM cases you found. A WSL distro is not corpus-free merely because `/home/...` lacks
> the corpus if the Windows host holding it is readable through `/mnt/c`, Windows interop, or another mounted path.
> Likewise, a VM is not corpus-free if a host/shared folder exposes the corpus or a parent directory containing it.
>
> I would also make the runner fail closed:
>
> ```
> preflight cannot establish corpus isolation
>     => do not release task
> ```
>
> But I would not turn this into "prove mathematically that the host can never reach the evaluator." That would drag
> F19 back into full containment/network-security design.
>
> So the practical boundary is:
>
> No local copy, no parent directory containing it, no mounted/shared/synced path to it, and no obvious
> host-integration path that can read it.
>
> For WSL specifically, if the Windows host itself stores the hidden corpus, I would treat that WSL instance as
> ineligible by default unless host-drive access/interop is deliberately disabled or otherwise shown not to expose the
> corpus. The cleaner setup is simply keeping the evaluator/corpus on another machine or environment.

**Filing (lead developer).** The split runner's arm-host preflight checks this boundary before every release and
refuses to release the task when it cannot establish it; the refusal happens before the attempt's arm starts and is
recorded with its reason. Ledger HOC-06 to HOC-09 (the rule) and HOC-11 (the preflight).
