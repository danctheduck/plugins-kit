# task-kit

File-backed task tracking for Claude Code: a task owns a folder, documents
reference it, and every verb names its task explicitly.

## What it does

The `task` skill drives one CLI over task folders (`tmp/<stub>` for
ephemeral work, `dev/tasks/<stub>` for version-controlled work): create,
list, show, validate, work, review, summarize, close, reopen, archive,
delete, and move (which rewrites every `task_list` reference to the moved
folder). The skill routes a natural-language request ("start a task for X",
"what tasks are open here?", "archive the closet task") to the right verb and
states what the agent, rather than the script, must do with the output.

The skill's entry point, verb contracts, and design documents are in
[skills/task/SKILL.md](skills/task/SKILL.md) and
[skills/task/design/task-system-design.md](skills/task/design/task-system-design.md).

## Install

```
/plugin marketplace add kitaekatt/plugins-kit
/plugin install task-kit@plugins-kit
```

task-kit declares dependencies on `bootstrap` (venv provisioning),
`skills-kit` (the `skills_kit_lib` schema engine the task CLI imports), and
`awesome-kit` (the `work` verb emits `Skill(awesome-kit:orchestrate)` as its
always-required baseline skill). Installing task-kit installs all three.

## Try this first

Ask for a task: "start a task for tidying the closet", or invoke the skill
as `task-kit:task`.

## When not to use it

Claude Code's native task tracking (TaskCreate / TodoWrite) is a different
system; task-kit is for work that outlives a session.
