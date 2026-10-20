---
name: recap
description: "Use when the user asks for a recap, returns from afk, or an afk or autonomous run ends: a recap fit to its trigger. Do NOT use to summarize documents or code."
argument-hint: "[return|afk-ending|autonomous-done <pid>]"
skill-type: technique-skill
---

# recap

A recap shaped by what triggered it, then recorded so the Stop hook can see
it. The model (presence, return, while away) is
`${CLAUDE_PLUGIN_ROOT}/references/presence.md`. This skill fires repeatedly in
a session, so the procedure lives in one reference document that you read once
and then follow from context on every later firing.

Arguments: $ARGUMENTS

```yaml
technique_skill:
  _schema_version: "1"
  identity: Write the recap that fits the trigger, record every away recap with recap-done, and interview only after a contentless reply.
  scope:
    covers:
      - a bare recap from a present user
      - the return recap, the afk ending recap and the autonomous-done recap
    excludes:
      - summarizing a document, a codebase, or a diff (that is ordinary summarization)
      - reflecting the user's stakes, preferences, or working agreements back at them
      - deciding the blocking questions on the user's behalf
  techniques:
    - id: recap_by_trigger
      name: Recap by trigger
      keywords: [recap, return recap, afk ending, autonomous done, what got done, pending decisions, neutral reply, batched interview]
      goal: The reader learns what finished, what was decided for them and what waits on them, in the shape the trigger calls for, and an away recap is recorded.
      arguments:
        - name: trigger
          required: false
          description: "`return`, `afk-ending` or `autonomous-done`; omit for a bare invocation."
        - name: pid
          required: false
          description: The prompt id the hook line or nudge names; required with a trigger. Use it exactly as given and never invent one.
      steps:
        - n: 1
          action: >-
            Follow `${CLAUDE_SKILL_DIR}/references/recap-procedure.md` with the
            arguments above. Read it first, unless its text is already in your
            context this session.
          tool: Read
          expected: The recap is written for the trigger and, on an away row, recorded with `recap-done`.
      gotchas:
        - Recap-shaped prose without the `recap-done` call the procedure ends with satisfies nothing; the Stop hook asks again.
```
