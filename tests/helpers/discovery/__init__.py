"""The discovery layer's D2: output and text rules (docs/implementation/vertical-uat.md, §8).

D2 observes; it changes no product code. ``rules`` decides each rule over one output (a CLI answer, a typed-tool
result, a refusal, or a static text); ``capture`` is the pytest plugin that collects the outputs the existing suite
produces; ``static`` gathers the static texts (the Lead's system text and commands, the rendered guide, the operator
guides and the pack templates); ``allowed`` holds the allow-list and decides a run against it; ``modes`` pins each
rule's mode (``shadow`` or ``enforce``), as the page does.
"""
