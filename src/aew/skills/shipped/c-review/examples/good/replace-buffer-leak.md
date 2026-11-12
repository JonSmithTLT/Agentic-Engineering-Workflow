# Good example

Synthetic good: `replace_buffer` returns an owned buffer on success and leaves the caller's old buffer untouched on failure. A caller assigns its result directly over the sole old pointer, then returns on failure. Trace the failed allocation and lost old owner to support a leak. If the old pointer is retained separately and freed on that branch, reject that witness. Do not assume these semantics for a similarly named real API.
