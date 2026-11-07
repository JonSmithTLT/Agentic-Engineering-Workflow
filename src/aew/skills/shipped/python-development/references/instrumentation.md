# Instrumentation hygiene

Read for AST transforms, import interception, or audit-hook work.

Treat parser structure, source positions, and stdlib signatures as versioned behavior. Probe the supported minimum interpreter with the actual construct being transformed, including f-strings and non-ASCII source when relevant. Do not infer positional precision or API availability from a newer local runtime. Keep any unsupported-runtime result explicit.

Instrumentation must preserve application name resolution and declared side-effect boundaries. Choose injected identifiers that avoid collisions and Python class-private name mangling; test transformed code inside a class as well as at module scope. Double-leading-underscore helpers can be mangled in class bodies even when the injected global is not.

Where instrumentation promises no filesystem mutation, prevent incidental bytecode-cache writes in the controlled interpreter and inspect effects in an isolated fixture. A no-bytecode setting does not prevent other import side effects. Preserve import-loader contracts and test repeated imports, exceptions, and cleanup.

Audit hooks affect the interpreter globally and are not a security sandbox. Run hook experiments in owned disposable interpreters; do not assume a Python audit hook can be unregistered after a test. Ensure the observer does not recursively trigger itself, swallow failures outside its contract, or change the behavior it claims to measure.
