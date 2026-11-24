"""Probe controls on the qualification branch only."""

import pytest


@pytest.fixture
def known_and_unknown(monkeypatch):
    from aew import doctor
    from aew.errors import HarnessIncompatible
    from aew.harness import registry

    monkeypatch.setenv(registry.ENV, 'sample=not_an_installed_fixture_probe_adapter:Adapter')
    with pytest.raises(HarnessIncompatible):
        registry.load('sample')
    yield
    assert doctor._modules()


def test_see_setup_call_teardown(known_and_unknown):
    import childdiag

    childdiag._main(['-c', 'pass'])
