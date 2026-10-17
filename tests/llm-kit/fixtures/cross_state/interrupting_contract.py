"""A job contract that asks for approval, then records the resolution it is handed.

First run (no resolution in the environment): write one interrupt request to
the path the runner exports and exit 0, which leaves the job waiting.
Continuation run: copy the resolution document the runner wrote, byte for byte,
onto the log named by ``argv[1]``, framed by a marker line, and exit 0.
"""

import json
import os
import sys

log_path = sys.argv[1]
resolution_path = os.environ.get("JOB_KIT_INTERRUPT_RESOLUTION")
if resolution_path is None:
    request = {
        "schema": "job-kit.interrupt-request/v1",
        "kind": "approval",
        "request_schema": {
            "type": "object",
            "required": ["approved"],
            "properties": {"approved": {"const": True}},
        },
        "payload": {"action": "push release tag"},
    }
    with open(os.environ["JOB_KIT_INTERRUPT_REQUEST"], "w", encoding="utf-8") as handle:
        json.dump(request, handle)
else:
    with open(resolution_path, "rb") as handle:
        raw = handle.read()
    with open(log_path, "ab") as handle:
        handle.write(b"--resolution--\n" + raw + b"\n")
