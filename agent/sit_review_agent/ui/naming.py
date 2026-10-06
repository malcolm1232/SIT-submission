"""The name the page shows for the agent.

"SIT" by default. ``SIT_DISPLAY_NAME`` names it otherwise, for example for a screenshot:
``SIT_DISPLAY_NAME="Design Review Agent" dra ui``. Only the words on the page change; the code, the
commands (``dra``) and the environment variables keep their names.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

ENV = "SIT_DISPLAY_NAME"


def names(env: Mapping[str, str] = os.environ) -> dict[str, str]:
    """The forms the page needs: the rail brand, the diagram's agent label, and the name inside a
    sentence (``agent_the``) and at its start (``agent_The``)."""
    custom = env.get(ENV, "").strip()
    if not custom:
        return {"brand": "SIT review", "agent_label": "SIT agent", "agent_the": "SIT", "agent_The": "SIT"}
    return {"brand": custom, "agent_label": custom, "agent_the": "the " + custom, "agent_The": "The " + custom}
