# Copyright 2026 Maxence Faldor
"""A stand-in for Claude Code in print mode, for testing the runner without a model.

The stand-in copies the script named by ``FAKE_SOLUTION`` to the path the prompt asks
for, and reports on standard output the way ``claude -p --output-format stream-json``
does.
"""

import json
import os
import re
import shutil
import sys


def main() -> None:
    prompt = sys.argv[sys.argv.index("-p") + 1]
    match = re.search(r"`(models/\w+\.py)`", prompt)
    if match is None:
        sys.exit("the prompt names no models/<name>.py")
    target = match.group(1)
    shutil.copy(os.environ["FAKE_SOLUTION"], target)
    build = {
        "type": "tool_use",
        "name": "Bash",
        "input": {"command": f"uv run bricky build {target}"},
    }
    events = [
        {"type": "system", "subtype": "init"},
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Building."}, build]},
        },
        {
            "type": "result",
            "subtype": "success",
            "num_turns": 3,
            "total_cost_usd": 0.12,
        },
    ]
    for event in events:
        sys.stdout.write(json.dumps(event) + "\n")


if __name__ == "__main__":
    main()
