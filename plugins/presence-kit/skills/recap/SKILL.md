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
a session, so it holds only the steps; the content lives in `references/` and
each step reads its file only when that text is not already in your context.

Arguments: $ARGUMENTS

The arguments are empty (a bare invocation) or `<trigger> <pid>`. The pid is the
prompt id that a presence-kit hook line or nudge names (`prompt <id>`); use it
exactly as given. Never invent one.

**A long recap is a failed recap.** An away recap is read cold by someone who
saw none of the work: outcomes, not activity, in as few lines as the content
allows.

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
          description: The prompt id the hook line or nudge names; required with a trigger.
      steps:
        - n: 1
          action: >-
            Read the configuration before anything else. An id that is off
            does not apply.
          tool: '"${BOOTSTRAP_PYTHON:?requires bootstrap >= 0.120.0}" "${CLAUDE_PLUGIN_ROOT}/scripts/presence.py" config'
          expected: One JSON object with `behaviors`, `values` and `layers`.
          on_failure: >-
            An `{"error": "config", ...}` object: report its `message` once. If
            you invoked the skill yourself, end here with no state change. If
            the user typed the command, write the recap but skip the
            `recap-done` call, and say so in one line.
        - n: 2
          action: >-
            Only when you invoked the skill yourself: end without changing
            state when the row's id is off, which is `recap-on-return` for
            `return` and `ending-recap` for `afk-ending` and
            `autonomous-done`. The user's own `/presence-kit:recap` always
            runs.
        - n: 3
          action: >-
            Read the session state: `afk_since`, `goal`, `goal_since`,
            `greeted` and `unresolved` feed the window, the row and the
            "Waiting on you" section. Then select the row, its window and its
            closing call from `${CLAUDE_SKILL_DIR}/references/recap-rows.md`;
            skip that read when the table is already in your context. A bare
            invocation takes its row from `presence` and takes the pid from
            this turn's presence-kit hook line.
          tool: '"${BOOTSTRAP_PYTHON:?requires bootstrap >= 0.120.0}" "${CLAUDE_PLUGIN_ROOT}/scripts/presence.py" state get'
          expected: '`{"exists": true|false, "state": {...}}`; `exists` false means the defaults (present, nothing recorded).'
        - n: 4
          action: >-
            Write Phase 1 for the row, over its window, in text only and never
            with AskUserQuestion. Use the template, the content rules and the
            decision-selection rules in
            `${CLAUDE_SKILL_DIR}/references/recap-templates.md`; skip that read
            when it is already in your context. A `return` with `greeted` true
            writes no Phase 1 text. "Waiting on you" lists every `unresolved`
            entry and every parked question. Write it before step 5, which
            clears `unresolved` on a return.
        - n: 5
          action: >-
            Every away row ends here, after the recap text: record it with the
            row's trigger and the pid, then carry on with the user's message.
            If no hook line gave a prompt id, do not invent one: skip this call
            and say so in one line.
          tool: '"${BOOTSTRAP_PYTHON:?requires bootstrap >= 0.120.0}" "${CLAUDE_PLUGIN_ROOT}/scripts/presence.py" recap-done <trigger> <pid>'
          expected: '`{"recorded": "<trigger>", "prompt_id": "<pid>", "state": {...}}`.'
          on_failure: "An `{\"error\": ...}` reply means the recap is not recorded; report its `message` once."
        - n: 6
          action: >-
            If the next user message is a contentless reply, follow
            `${CLAUDE_SKILL_DIR}/references/recap-interview.md` (skip the read
            when it is already in your context). This follows every row,
            `greeted` included.
      gotchas:
        - A return with `greeted` true gets no Phase 1 text, but still gets the `recap-done return <pid>` call and, after a contentless reply, the interview.
        - Recap-shaped prose without `recap-done` satisfies nothing; the Stop hook asks again.
        - Phase 1 is text only; an AskUserQuestion call before a contentless reply removes the reader's option to answer in one sentence.
```
