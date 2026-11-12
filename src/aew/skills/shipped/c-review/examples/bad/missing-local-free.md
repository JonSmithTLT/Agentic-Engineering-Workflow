# Bad example: the same allocation as [the good example](../good/replace-buffer-leak.md)

Synthetic bad: call the same allocation a leak merely because this function has no `free`, even though its success path transfers ownership to a documented consumer. Follow the transfer and failure paths separately; a missing local release alone is not evidence of a lost owner.
