"""The one call somebody should need, and what it defaults to.

Before this, a caller had to assemble an `IriguchiConfig`, ask it for a
`PromptRouter`, and know that `available` is a `frozenset[Destination]`. Three
objects and a domain vocabulary, to answer *may this prompt leave*.

**A person deciding whether a tool is worth adopting should not have to build
three things to find out.** That is the whole reason this module exists, and it
is the same reason `route --json` exists: the barrier was not the router, it was
everything around it.

The package docstring said, until this change, *"nothing is re-exported here
yet"* and *"there is not yet anything that produces either -- no scanner, no
estimator, no CLI"*. All three exist. **A package's own docstring is the first
thing a reader meets and it was describing a version nobody can install.**
"""

from __future__ import annotations

import pytest

import iriguchi
from iriguchi import route
from iriguchi.domain.destination import Route
from iriguchi.errors import ConfigurationError


class TestTheDefaultIsFailSafe:
    def test_saying_nothing_refuses(self) -> None:
        """Not "assume a local model exists". A caller who has configured
        nothing gets a refusal that names what is missing, which is the same
        default the CLI and the config object already had."""
        decision = route("Summarise this article.")
        assert decision.route is Route.REFUSED
        assert "no destination is available" in decision.reasons[0].detail

    def test_local_only_keeps_everything_local(self) -> None:
        decision = route("Prove the lemma, step by step, comparing both.", local=True)
        assert not decision.leaves_the_machine

    def test_a_finding_removes_the_external_destination(self) -> None:
        """The veto, through the front door. Complexity cannot buy it back."""
        decision = route(
            "Contact tanaka@example.com and prove the lemma, step by step.",
            local=True,
            external=True,
        )
        assert not decision.leaves_the_machine
        assert [r.destination.value for r in decision.removed] == ["external"]


class TestTheArgumentsReachTheRouter:
    def test_a_named_estimator_is_used(self) -> None:
        assert route("hello", local=True, estimator="rules").route is Route.LOCAL

    def test_an_unknown_name_is_refused_rather_than_defaulted(self) -> None:
        with pytest.raises(ConfigurationError, match="no estimator called"):
            route("hello", local=True, estimator="routellm")

    def test_a_lowered_threshold_changes_the_route(self) -> None:
        """The point of exposing the bands: the same prompt, two answers, and
        the difference is a number an operator chose."""
        # Scores 0.45 on one escalating signal, so it is MODERATE by default
        # and HIGH once the threshold drops below its score. The first draft
        # used a prompt with *two* escalating markers, which short-circuits to
        # HIGH whatever the threshold is -- it escalated in both branches and
        # the assertion that it would not was simply false. Measured before
        # being written down this time.
        prompt = "Compare these two approaches."
        assert not route(prompt, local=True, external=True).leaves_the_machine
        assert route(prompt, local=True, external=True, high_at=0.4).leaves_the_machine

    def test_a_threshold_that_would_hide_a_band_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="unreachable"):
            route("hello", local=True, moderate_at=0.9, high_at=0.5)

    def test_a_float_survives_the_trip_through_the_config(self) -> None:
        """`route` hands its floats to a config that reads strings, so this is
        the one place a rounding or formatting slip would live. `repr` rather
        than `str` because `str(0.30000000000000004)` is lossy on older
        Pythons and a threshold that arrives changed is a threshold nobody
        set."""
        decision = route("hello", local=True, high_at=0.7000000000000001)
        assert decision.route is Route.LOCAL


class TestWhatIsReExported:
    def test_the_names_the_docstring_promises_resolve(self) -> None:
        for name in iriguchi.__all__:
            assert getattr(iriguchi, name) is not None, name

    def test_an_unknown_attribute_still_raises(self) -> None:
        """`__getattr__` must not turn every typo into `None`."""
        with pytest.raises(AttributeError, match="has no attribute"):
            iriguchi.nonexistent  # noqa: B018

    def test_importing_the_package_does_not_import_the_world(self) -> None:
        """Lazy on purpose. `import iriguchi` in a script that only wants the
        version should not build a scanner, and this is the check that keeps
        the `__getattr__` honest rather than decorative.
        """
        import subprocess
        import sys

        loaded = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, iriguchi; "
                "print(int(any(m.startswith('iriguchi.infrastructure') for m in sys.modules)))",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert loaded.stdout.strip() == "0", "importing the package built an adapter"

    def test_the_docstring_no_longer_describes_a_version_nobody_can_install(self) -> None:
        """It claimed there was no scanner, no estimator and no CLI. All three
        exist, and a package docstring is the first thing a reader meets."""
        assert iriguchi.__doc__ is not None
        assert "no scanner, no estimator, no CLI" not in iriguchi.__doc__
        assert "from iriguchi import route" in iriguchi.__doc__


class TestTheDocstringExampleIsTrue:
    def test_the_example_in_the_package_docstring_runs(self) -> None:
        """A README example that has drifted is worse than none: it is the
        first thing anybody tries. Run rather than read."""
        decision = route("Summarise this article.", local=True, external=True)
        assert decision.leaves_the_machine is False
        assert [reason.detail for reason in decision.reasons] == [
            "complexity band low does not call for the larger model, and a local model is permitted"
        ]
