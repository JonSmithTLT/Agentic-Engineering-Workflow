# Questions for multi-step plans

- **Interface.** Which caller changes first? What contract and data version
  does each intermediate state admit? What happens to already stored data?
- **Order.** What artifact or approval does the next owner consume? Can they
  identify it, and is it available by the stated milestone?
- **Partial failure.** What can commit before a later step fails? What makes
  a retry safe or a recovery step sufficient?
- **Verification.** What behavior must a check observe, in which environment
  and at what revision? Could it pass while the requirement is broken?
- **Triggers.** Which observable event calls for a stop, escalation, or
  decision, and who receives the evidence?
- **Scope.** Does a linked adopted contract answer the question? Is a
  remaining choice delegated and reversible within the approved scope?

Cite the exact relevant text for each material concern. If a check belongs
to a later actor, review its design and ownership on paper.
