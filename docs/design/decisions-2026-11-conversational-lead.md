# Amendment: the conversational Lead (A-58), 2026-11-09

**Status:** Decision record, governing for what it decides. Approved by the operator, 2026-11-09: "Adopt it".

## What changes

A Lead rests idle and AEW wakes it. Every new signal is a wake reason, in one list. `harness_wait` returns those same reasons, and is only for waits of seconds or where wakes can't reach. It gets no features of its own.

- **The Lead rests.** Where these documents have the Lead wait with `harness wait` as its idle loop, it now ends its turn, and AEW wakes it.
- **One list, two deliveries.** Where they name a lane in `aew harness wait --any` as the only route for a signal, that signal is a reason on the one list, delivered by a wake and by the wait.

## What doesn't change

The wait stays, and still returns each reason apart from `quiet`, the backstop, which is the wake's alone, including on every route a wake can't reach. So a `stalled` return, when it's built, is still a return from the wait as well. The edge trigger, the confidence rule and "never terminates" stand. A wake grants nothing. `MIC-10` stands: E7's notifier stays the operator's, no model polls, and the broker's wake thread isn't a second notifier in its sense, since it's the Lead's one route, with the list as its one owner.

## Which documents this amends

The run health projection design §7 and §8, and its implementation note §6. The cross-feature integration design §11.1, §18 and its W6 row. The decisions of 2026-10-10 (evening), D5, and of 2026-10-11, §3.3's S3. The Lead-worker messaging amendment §15. Each carries a pointer here.

## Decision

Approved by the operator, 2026-11-09: "Adopt it". The position is A-58, `CL-`, in the design workspace.
