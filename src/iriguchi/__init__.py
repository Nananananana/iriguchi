"""iriguchi -- a local governance router for generative AI.

It stands between a person and every model they use, and decides -- locally,
deterministically, and before a single byte leaves the machine -- where each
prompt is allowed to go.

**The domain exists; nothing above it does.** ``iriguchi.domain`` decides a
route from a sensitivity and a complexity, and there is not yet anything that
produces either -- no scanner, no estimator, no CLI. The design is
``docs/proposals/0001-the-design.md`` and the decisions it rests on are in
``docs/adr/``. See ``docs/README.md`` for where the project actually is.

Nothing is re-exported here yet. A top-level name is a promise about a public
API, and the API is not settled until something outside the domain uses it;
until then, import from ``iriguchi.domain`` and expect it to move.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
