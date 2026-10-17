"""task_system.dashboard -- the machine-wide, read-only task dashboard.

A detached local HTTP server (``server``), the launcher that starts, reuses,
restarts and stops it (``launcher``), a cached read-only view over every
configured project's task folders (``inventory``), and the static UI under
``static/``. Everything here imports the task system in place; nothing in
``task.py`` or the other ``task_system`` modules imports this package, so the
task verbs run unchanged whether or not a dashboard exists.
"""
