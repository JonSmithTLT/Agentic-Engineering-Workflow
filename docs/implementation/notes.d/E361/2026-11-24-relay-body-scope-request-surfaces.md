**Follow-on (#551's review, m7): pin the providers' request surfaces the body scope rests on.** `relay.BODY_FIELDS`
and where `relay._ROUTES` reads each model-call route's body for them come from each provider's request reference, as
an implementation choice stated in `relay.py`: no provider's request types are pinned in the repository, as
OpenCode's API is (`tests/fixtures/opencode/openapi-2.2.6.min.json`). Fixtures of each provider's request types
(OpenAI's Responses and Chat Completions, Anthropic's Messages, Google's generateContent), with a test that every
field and place in them that names a stored object, a file by reference or a tool the client does not run is held or
judged not to need it, are the tracked follow-on, so a provider's new field is seen when its pinned surface moves.
Unscheduled; the operator places it.
