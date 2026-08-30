"""iriguchi -- a local governance router for generative AI.

It stands between a person and every model they use, and decides -- locally,
deterministically, and before a single byte leaves the machine -- where each
prompt is allowed to go.

**Nothing is implemented yet.** This package is the scaffold. The design is
``docs/proposals/0001-the-design.md`` and the decisions it rests on are in
``docs/adr/``. See ``docs/README.md`` for where the project actually is.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
