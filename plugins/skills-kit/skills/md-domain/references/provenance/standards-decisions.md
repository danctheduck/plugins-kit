# standards decisions

Decision provenance for the per-artifact standards docs in
`references/standards/`. Each record follows the surface / finding /
follow-up convention (${CLAUDE_PLUGIN_ROOT}/CLAUDE.md, conventions). The
canonical rule text lives in the standards doc it amended; this file records
why the rule was tightened so the decision can be rewound.

```yaml
claude_md:
  _schema_version: "1"
  scope:
    directory: skills/md-domain/references/standards
    covers:
      - decisions that tightened or amended a standards-doc criterion
    excludes:
      - the criteria themselves (live in the standards docs)
      - framework-vocabulary decisions (skill-authoring-decisions.md)
  insights:
    - id: a3_provenance_path_rule
      keywords: [provenance path, origin field, tmp path, gitignored citation, ephemeral artifact, A-3, run disagreement, idempotency]
      summary: "A-3 amended 2026-08-03: a provenance field citing an untracked path (e.g. tmp/...) is a decisive FIX (drop the path, keep description/date/ids), never an accepted historical pattern."
      detail: |
        Surface: back-to-back full audits of plugins/skills-kit (2026-08-03,
        detect lanes then pinned opus/high) disagreed on skills_kit_lib/CLAUDE.md line
        175 -- run 1 classified the gitignored tmp/ citation in an origin:
        field SILENT ("accepted structural pattern"), run 2 FAILed it as a
        broken reference. Finding: both readings were defensible under the
        old A-3 text, so the outcome depended on per-run judgment. Follow-up:
        the criterion now decides it -- cite ephemeral work by description,
        date, and finding ids; a path-form citation to an untracked location
        is a loss-free FIX. Rule text: claude-md-standards.md A-3.
      origin: Adjudicated 2026-08-03 after the run-1/run-2 disagreement; user directed that run disagreements be settled by tightening criteria.
      added: "2026-08-03"
    - id: h9_annotation_ceiling_test
      keywords: [H-9, pointer map, annotation ceiling, embedded documentation, error driver, routing payload, surface map, run disagreement]
      summary: "H-9 amended 2026-08-03: a pointer-map annotation may exceed one line only for constraint/error-driver lines not stated at the target; lines summarizing the target's own content/structure trip H-9 regardless of the map's routing value."
      detail: |
        Surface: the same back-to-back audits disagreed on the
        plugin_surface_overview map in ${CLAUDE_PLUGIN_ROOT}/CLAUDE.md -- run 1
        passed H-9 ("the map is the file's declared routing payload, so it
        earns the annotation"), run 2 FAILed it (multi-line recaps of the
        targets' own layout and config format re-embed deferred
        documentation). Finding: "earns the annotation" was a vibe, not a
        test, so the whole map's fate flipped per run. Follow-up: H-9 now
        carries a per-annotation test -- keep lines stating a constraint or
        agent-error driver absent at the target; collapse lines recapping the
        target's structure. Blanket load-bearing claims are explicitly not an
        exemption. Rule text: claude-md-standards.md H-9.
      origin: Adjudicated 2026-08-03 after the run-1/run-2 disagreement; applied to ${CLAUDE_PLUGIN_ROOT}/CLAUDE.md in the same change.
      added: "2026-08-03"
    - id: count_typing_exact_vs_illustrative
      keywords: [count claim, exact enumeration, illustrative magnitude, P_stale_factual_claim scope, CD-4 narrowed, counted magnitudes, enumerate not comment, stale comment confirms doc]
      summary: "Counts typed 2026-08-07: exact-enumeration counts are contractual and verified by enumerating the code; illustrative magnitudes stay exempt. P_stale_factual_claim's scope grew from classic-only to include code-directory files for exact-enumeration counts."
      detail: |
        Surface: an md-domain audit of a project left "the eleven native
        systems" standing against 19 actual registrations, and "13 tests"
        against 16 definitions, in files it had read and edited. Finding: two
        causes, both structural. (1) Those files were dimension
        code-directory, and P_stale_factual_claim was scoped to "a classic
        (non-code-directory) CLAUDE.md", so the only criterion that could see
        a wrong count was not eligible; the CD dimension that DID apply says
        "counted magnitudes are illustrative, not contractual" (section 3.4)
        and CD-4 says "never FAIL on the number", which correctly exempts
        "a 7200-line god object" but wrongly also exempted a count a reader
        relies on as a complete list. (2) P appeared only in the detect
        lane's taxonomy enum and its step-8 mapping line -- no operative
        instruction ever told a lane to look for count-shaped claims, which
        is why it effectively never fired.
        Follow-up: A-3 now types counts (exact-enumeration vs
        illustrative-magnitude, ambiguity resolved as illustrative) and
        extends P to code-directory files for the exact-enumeration kind
        only, at JUDGMENT severity so nothing new gates; 3.4 and CD-4 are
        narrowed IN PLACE rather than overturned, each naming the exception;
        and claude-md-detect.js gained step 4.5, the missing operative
        instruction. Encoded with it, because it is the part that makes the
        check worthless if forgotten: verification is by ENUMERATING
        registrations/definitions/entries, never against adjacent prose --
        the stale "eleven" was echoed in the source's own comment above the
        registration site, so a fact-check against the nearest human-readable
        text CONFIRMS a wrong doc. Rule text: claude-md-standards.md A-3
        ("Count claims"), section 3.4, CD-4, and the P row in 5.2.
      validation: |
        Measured before publishing, 2026-08-07.
        Regression (flecs-ecs, the corpus the criteria were designed against):
        recall 3/4 on the pre-registered count key with every value derived
        correctly; 6/6 answer-key rows across both criteria; all four negative
        controls silent; the stale-comment trap (a wrong figure echoed in the
        source's own comment) defeated by the enumerate-not-adjacent-prose
        clause. One blocking defect found and fixed: enumeration depth was
        unspecified while the disposition is an APPLIED FIX, so a lane could
        write a NEW wrong number (12 rather than 19) into the doc.
        Precision (a large C#/C++ game corpus, HELD OUT): 4 true positives,
        2 false positives, 6 correct suppressions. Both false positives were in
        the ENUMERATION half and produced the closed-set and unit-ambiguity
        gates now in the rule -- membership decided by template / attribute /
        reflection dispatch is not enumerable, and a count is not wrong if any
        defensible unit makes it right. CD-2b needed no change, but its
        "document RIGHT, code WRONG" framing was corrected: an incomplete
        catalog is an equally valid reading, so both resolutions are reported
        and the choice is a human's.
        ACCEPTED LIMITATION (decided 2026-08-08, not an open item): measured on
        C, Python, C# and C++ only. TypeScript / Rust / Go will not be tested --
        no corpus is at hand, and a gate nobody can satisfy erodes the whole
        discipline rather than raising it. Do not describe these criteria as
        validated across languages, and do not re-file this as pending work.
        The enumeration half assumes a greppable closed registration site; it
        broke twice already (C++ trait dispatch, C# partial classes), and the
        closed-set / unit-ambiguity gates are the general defence. A future
        false positive from an unmeasured idiom is a bug report against those
        gates -- widen the unverifiable category, never guess a number.
      origin: Diagnosis of a clean audit coexisting with drifted counts, 2026-08-07 (mechanism M4 of that investigation); both independent reviewers converged on the same type distinction.
      added: "2026-08-07"
    - id: cd2b_invariant_violated_by_code
      keywords: [CD-2b, H2_inverted_absence extended, stated invariant, doc right code wrong, SERIOUS not FAIL, reported never gated, verbatim quote gate, remediation owner code author]
      summary: "CD-2b added 2026-08-07: an invariant the corpus states, violated by cited code, is reported under H2_inverted_absence as SERIOUS at JUDGMENT severity -- above the verdict, never gating, remediation owned by the code author."
      detail: |
        Surface: a root CLAUDE.md stating "No silent fallbacks" sat beside a
        registration function that silently no-ops on an unknown name, and a
        doc stating "Comparability is never assumed" sat beside code failing
        OPEN on missing comparability. Both passed. Finding: H-11 checks a
        subject doc against an ancestor's declared convention (doc vs doc);
        nothing checked CODE against an invariant the corpus states. The
        class was already named -- H2_inverted_absence's remediation says
        "the fix is in the code/repo, not the CLAUDE.md" -- but only for a
        requires-absent ANCHOR, not for a stated invariant.
        Follow-up: extend H2 rather than add a rule-id family. The
        specification the first review of this idea lacked is now explicit:
        subject (a stated invariant vs the code it governs); severity
        JUDGMENT with disposition SERIOUS, never FIX; remediation owner the
        code author, never a doc edit; and two gates -- the invariant must be
        quotable VERBATIM from the subject or a supplied ancestor (H-11
        posture) and the violation must be demonstrable at a cited code
        location. The verdict question is the load-bearing one: a correct doc
        beside a violated invariant has no document defect, so marking it
        NON-COMPLIANT would be false, but dropping the finding loses the most
        important thing on the page. Resolved with the EXISTING precedent
        rather than new vocabulary -- SERIOUS findings are reported above the
        verdict and survive review mode's attributability filter -- giving
        the rule "reported, never gated". Rule text: claude-md-standards.md
        CD-2b (section 3.6), the H2 rows in 3.6 and 5.2, and the
        reported-but-not-gated note in 5.3; operative instruction at
        claude-md-detect.js step 6.5.
      origin: Diagnosis of a clean audit coexisting with code-violated invariants, 2026-08-07 (mechanism M5 of that investigation); the earlier version of this proposal was rejected for leaving subject, severity, verdict interaction, and remediation owner undefined.
      added: "2026-08-07"
    - id: coverage_criteria_desk_validated_precision_unmeasured
      keywords: [coverage criteria, negative controls, validation, held-out corpus, precision unmeasured, accepted limitation, judgment enforcement, MB_HAZARD_CAP]
      summary: The eight coverage criteria satisfy all four of coverage-gap.md's negative controls BY CONSTRUCTION -- each control maps to a fail-severity criterion -- but empirical precision was NOT measured, because no held-out corpus exists. Shipped with the limitation recorded, per the documented rule.
      detail: |
        Control-to-criterion map, each verified by reading the criterion text
        against the control text (coverage-gap.md:173-188):
        (1) a correctly non-ambient fact must not be relocated ->
            no-cross-apply-placement, whose example IS the control's seed-variable
            case: the destination must be an ancestor of every file the fact
            governs AND of no file it does not, so a sibling placement is refused.
        (2) already-ambient facts must not be re-proposed ->
            already-ambient-suppressed, stated absolutely, trigger sites included.
        (3) good prose must not be flagged as low-value ->
            present-content-not-re-audited. Also structural: coverage proposes
            only ABSENT facts and has no verdict capable of flagging present prose.
        (4) the documented near miss must stay silent -> loud-failure-excluded,
            which keys on whether the failure is SILENT (documented AND loud AND
            test-enforced), not on the shape of the construct -- the exact
            inversion the control exists to catch. MB_HAZARD_CAP / MB_MAX_CHARS
            is excluded TWICE, since being documented in the ambient chain also
            trips already-ambient-suppressed. Redundancy on the sharpest control
            is deliberate.
        WHAT THIS DOES NOT ESTABLISH, and the reason to write it down. Every
        criterion is enforcement: judgment, so a passed desk control shows the
        criterion TEXT would direct a correct assessor to reject. It does not
        show that a model applying the text does. The controls were also read
        while authoring the criteria, so passing them is close to recall against
        the deriving corpus -- which the standing rule says means nothing alone.
        WHY IT SHIPPED ANYWAY. Precision on a corpus the criteria were NOT
        designed against was not measured because no such corpus is available:
        flecs-ecs is simultaneously the corpus the criteria were derived from and
        under a standing do-not-touch. The documented rule for exactly this case
        is SHIP and record the limitation rather than block (coverage-gap.md,
        "Scope of the rule"). This entry is that record. The first coverage run
        on any unfamiliar subtree is the real first measurement, and should be
        read as such rather than as a routine result.
      origin: |
        Authoring the coverage criteria, 2026-08-08. Surface: the criteria item
        required validation against the four negative controls before shipping.
        Finding: all four are satisfied by construction, and no held-out corpus
        exists to measure precision. Follow-up: treat the first run on an
        unfamiliar subtree as the measurement, and revisit if it produces
        candidates any of the four controls should have suppressed.
      added: "2026-08-08"
    - id: sr_criteria_skill_reference_subject
      keywords: [SR-1, SR-2, SR-3, SR-4, skill reference, section 10, second subject shape, claim carve-out retired, held-out precision, scope guard, O_broken_inbound_anchor, P_internal_contradiction, Q_overstated_claim, R_maintainer_only_material]
      summary: "skill-standards.md gained section 10 (2026-08-09): the audit_skill lane's SECOND subject shape, a skill's references/*.md, with four prose criteria. Shipped in the same change that dropped the code-review kits' `!**/skills/*/references/*.md` claim exclusion."
      detail: |
        Surface: no md-domain lane read a skill reference document's prose.
        audit_skill audited the owning SKILL.md's contract and load graph;
        audit_project_doc's PD-1 declined anything inside a skills tree and
        returned NOT-AUDITED. Both code-review kits therefore carved the shape
        out of their claim globs so it fell back to the generic reviewers -- a
        placeholder, with the condition written into the kits' reference doc:
        drop the exclusion in the SAME change that ships real criteria.
        Finding: an opus generic reviewer on one changed reference document
        (2026-07-28) found five defects no lane could reach -- a renamed heading
        that broke six citing files, a self-contradicting paragraph, an
        overstated claim, temporal deixis, non-ASCII lines. Only the first three
        needed new criteria: temporal deixis and non-ASCII are already covered
        by the H-11 ancestor-convention check and the classifier's built-in
        universal-convention FIX, which run on any subject the lane audits, so
        section 10.2 NAMES them rather than restating them (summarize-and-
        reference). SR-4 (reader fit) was added beyond the five: it is the one
        criterion that reaches the root CLAUDE.md's OP-1 concern about
        maintainer-only material on a published plugin surface, which that
        insight had recorded as unreachable precisely BECAUSE of the carve-out.
        WHAT THE CRITERIA DO NOT COVER, deliberately: the SKILL.md contract rows
        (no frontmatter, no type, no schema on a reference), CCP/CRP placement
        (the L2->L3 split belongs to the owning SKILL.md's audit, which sees both
        sides), reachability (owned by the SKILL.md subject), and hygiene
        thresholds (a reference being long is the point of L3). Enumerated in
        10.1 so the next reader does not add them back.
        HELD-OUT MEASUREMENT, and it changed the rules twice. Two precision runs
        on seven reference documents from four plugins the criteria were NOT
        derived against (unreal-kit, hue-kit, content-pipeline-kit,
        awesome-kit), each run by a fresh assessor reading only section 10.
        Run 1: 9 findings, 7 false positives (~22% precision), with three
        distinct causes -- SR-1 fired on informal prose pointers that resolved
        unambiguously (4 of its 6 findings); SR-3 fired on a principles
        document's core structural device, where the Principle / Why /
        Embodied-by genre is neither a claim nor an instruction and so fell
        through a binary guard; SR-4's Rule sentence read wider than its Test,
        so an assessor anchoring on the Rule would flag guidance about the
        DESCRIBED SYSTEM as maintainer-only. All three were fixed in the
        criterion text: SR-1 now grades only anchor links and verbatim heading
        quotes as FAIL and names the unambiguous prose pointer as explicitly not
        a violation; SR-3 has a three-genre guard admitting only claims; SR-4's
        Rule is bounded to the document's own production pipeline.
        Run 2 (post-fix, four documents, one of them new): SR-1 zero findings,
        SR-4 zero findings, SR-3's principles document went from a systematic
        misfire surface to zero, and SR-2 produced the run's one TRUE POSITIVE
        -- a real self-contradiction four lines apart in
        unreal-kit script-execution.md about whether every .py in
        Content/Python/ auto-runs or only init_unreal.py. Residual: 3 SR-3
        findings the assessor itself judged as ones a maintainer would not act
        on, which produced the CONSEQUENCE BAR (raise only when a reader
        believing the claim as stated could act wrongly). That third fix is
        NOT itself measured -- iteration stopped at two rounds.
        LIMITATIONS, recorded rather than left as pending actions.
        (a) SR-1 tests RESOLVABILITY, not APTNESS: run 2 found a citation
        pointing at a section that exists but is the wrong one for the capability
        citing it, and SR-1 is blind to it by construction. Judging aptness is a
        different and much noisier criterion; not attempted.
        (b) Every criterion is enforcement: judgment. A passed desk control shows
        the criterion TEXT directs a correct assessor; it does not show the
        production lane, at its own model and effort pin, applies it the same way.
        (c) The corpus is this repo. It is held out from the DERIVATION (a
        different plugin, a different author, documents chosen after the criteria
        were written) but it is not an unfamiliar codebase, and all seven
        documents share this repo's conventions.
        (d) SR-2's "quote both passages" bar is the only mechanically checkable
        guard in the set, and it is the one that demonstrably worked in both runs
        -- it suppressed four one-sided suspicions and admitted the one true
        positive. Prefer that shape when adding a fifth criterion.
      origin: |
        2026-08-09, task item `skill-references-lane`. Surface: the 2026-07-28
        routing gap left direction 2 (real criteria) unbuilt while directions 1
        (the carve-out) and 3 (the NOT-AUDITED verdict) shipped, so the claim
        exclusion was a standing placeholder. Finding: the two held-out precision
        runs above, which rewrote three of the four criteria before they shipped.
        Follow-up: SR-1's aptness blindness and the unmeasured consequence bar are
        limitations (a) and above, not action items.
      added: "2026-08-09"
    - id: potential_defects_broadened_v1_to_v2
      keywords: [CLAUDE-potential-defects.md, potential defects schema, source field, verified field, why_deferred, why_not_ambient, schema v2, deferred defect, admission route, hazard-durability, deferred-defects.md]
      summary: "potential_defects schema amended v1 -> v2: the sidecar's purpose broadened from a single coverage-lane hazard-durability residue to a general known-defects-deliberately-deferred pattern admitting several routes (coverage-lane, triage, review, ordinary work). File-level status dropped for per-entry source + verified; why_not_ambient renamed why_deferred."
      detail: |
        Surface: two verbatim user rulings. Purpose: "The purpose of this
        pattern is to record known defects/gotchas that are severe enough
        that they should be addressed, but which we are not addressing at
        this time." Placement: "The rule is there needs to be a CLAUDE.md in
        the same directory that references it. Create this file in the most
        relevant directory associated with each defect."
        Finding: the prior "hand-off" section in capability-boundaries.md
        scoped the pattern to exactly one route (a coverage run's
        hazard-durability rejection), stated as "the one place md-domain
        emits anything defect-shaped" and gated by "admission to it requires
        this criterion to have rejected the fact first." Its schema matched
        that narrow scope and nothing wider: file-level `status: unverified`
        and entry-level `why_not_ambient` both assumed every entry arrived
        the same way, for the same reason, at the coverage lane's hand. Both
        assumptions are false once triage, review, and ordinary-work
        observations are admitted on the same footing -- entries can arrive
        from different processes, at different times, with independent
        verification states.
        Follow-up: the primary definition moved to the dedicated
        `references/deferred-defects.md` (capability-boundaries.md no longer
        fit once the pattern stopped being scoped to the
        md-domain/code-review/code-audit split; it keeps only the
        code-audit-consumption fact and points to deferred-defects.md for the
        file's own contract). Schema changes, each minimal: `status` dropped
        (file-wide, but verification is a per-entry fact, not a file-wide
        one); `source` added per entry (deliberately open free text --
        `coverage-lane:hazard-durability`, `triage`, `review`,
        `ordinary-work`, or any other named process; the set of processes
        that can responsibly defer a real defect is open-ended, so a closed
        enum would either reject a legitimate route or invite a false fit
        into the nearest existing tag); `verified` added per entry (boolean,
        `false` at creation always -- flipping it is the code-audit
        capability's job, never the reporter's); `why_not_ambient` renamed
        `why_deferred` (the old name presumed every entry was rejected FROM a
        CLAUDE.md draft, true only for the coverage-lane route -- for every
        other route there was no draft to reject the fact from, only a
        defect noticed and set aside); `_schema_version` moved "1" -> "2" so
        a v1-only reader does not silently misread a v2 file. The coverage
        lane's own route (hazard-durability, coverage-standards.md;
        generation-lane.md's write mechanics; claude-md-generate.js's
        agent-result schema) kept its narrow, still-true description with the
        old exclusivity language ("the one place," "requires this criterion
        to have rejected the fact first") removed, since other routes
        exist alongside it. Placement enforcement: the coverage lane's write
        instructions were tightened so a sidecar is never written without a
        co-located CLAUDE.md carrying the required pointer in the same turn
        -- a non-empty `potentialDefects` takes the null branch off the
        table for that directory, forcing a pointer-only CLAUDE.md when the
        directory's own code otherwise earns no ambient cost. Current-state
        contract: deferred-defects.md.
      origin: User-directed broadening of the CLAUDE-potential-defects.md pattern from the coverage-lane-only release valve to a general deferred-known-defects pattern with multiple admission routes.
      added: "2026-09-25"
    - id: coverage_criteria_configurable_by_id
      keywords: [coverage criteria, rules off, already-ambient-suppressed, plugin-opinion razor, rule_catalog optional bucket, shipped_dir, resolve_standards, coverage-detect disabledCriteria, seam not register entry, config resolution step]
      summary: "Coverage criteria made configurable by id 2026-10-02: the eight coverage-standards.md ids are registered in rule_catalog.py's optional bucket and disableable via rules: {<id>: off}. The obstacle was a missing resolution step in the coverage lane, not the criterion. Loading shipped standards through resolve()'s shipped_dir was rejected because enabling it raises and refuses every audit."
      detail: |
        Surface: an md-domain audit of a 2026-10-02 skills-kit change raised a
        plugin-opinion-razor finding. coverage-standards.md's
        `already-ambient-suppressed` criterion sat at severity fail while its own
        text conceded that a competent team disputes it, and no seam disabled it.
        plugins/CLAUDE.md's razor requires every workflow opinion to be
        configurable with a default or registered as a deliberate stance. An
        earlier documentation pass had removed a false "disable-able or tunable"
        promise without adding the seam, and the document had come to assert that
        the criterion has no supported seam and to register the stance as
        deliberate. The user ruled between the two razor remedies: "Build the
        seam". The register-entry route was ruled out.
        Finding: the obstacle was not the criterion but the absence of a
        resolution step. The coverage lane had no config-resolution step at all,
        unlike the audit lane, so there was nothing to thread a disabled list
        through. The route taken registers the eight criterion ids in
        rule_catalog.py's optional bucket, which needs no change to
        standards_resolve.py; coverage-lane.md gained a once-per-run
        scripts/resolve_standards.py call, and coverage-detect.js reads
        input.disabledCriteria and injects a suppression clause. The default is
        ON. A second candidate route, loading the shipped standards documents as
        an authored layer through resolve()'s `shipped_dir` parameter (documented
        as unused until M5), was REJECTED on evidence. Executing it makes
        resolve() raise before returning: the `*-standards.md` glob matches
        shipped documents that carry no `standards_set:` block, and
        coverage-standards.md's `applies_to: code_subtree` (renamed
        `code_directory` in 0.86.0) was not one of the four file-type
        primitives. audit-lane.md treats resolve_standards.py's
        non-zero exit as STOP, so enabling that route would refuse every skill,
        claude-md and project-doc audit in every project. This is the most
        reusable finding of the entry: `shipped_dir` is fatal to enable as it
        stands. skills-kit 0.86.0 recognised the `code_directory` composition id
        as an `applies_to` name, which removed the `applies_to` cause. 0.87.0
        brings that cause back: under `shipped_dir`, coverage-standards.md's
        `applies_to: code_directory` (its `standards_set` block,
        coverage-standards.md:54-60) raises via `APPLIES_TO_NOT_CONSUMED`,
        in addition to the error from the documents that carry no
        `standards_set:` block. Both make `shipped_dir` fatal.
        Follow-up: none for the seam itself. `shipped_dir` remains unused.
        Prerequisites to any future use of it: (1) narrow its glob; (2) exclude
        coverage-standards.md, or wire the coverage lane to consume authored
        sets and remove `code_directory` from `APPLIES_TO_NOT_CONSUMED`. The
        0.86.0 widening of `applies_to` was narrowed for authored sets in
        0.87.0.
        Superseded note: "`shipped_dir` remains unused" stopped being true in
        skills-kit 0.92.0, which enables it on a dedicated directory rather
        than through either prerequisite; see shipped_standards_layer_enabled.
        Verification was behavioural, not a prompt-string assertion: the same
        fixture assessed with the criterion enabled returned COVERAGE-ASSESSED
        with no candidates, and with the id disabled returned GAPS-FOUND with the
        suppressed fact proposed. Consumer-facing text: configuring-standards.md,
        "Worked example: disable a coverage criterion". Criterion text:
        coverage-standards.md.
      origin: Surface, finding and follow-up above; the user's ruling was "Build the seam", 2026-10-02.
      added: "2026-10-02"
    - id: audit_block_fix_mode
      keywords: [audit block, fix_mode, apply propose, FIX = apply, AUDIT_KEYS, _validate_audit, remediate lanes guard, args.fixMode, fails open, single-file inline edit, review mode not reusable, behaviour setting not rule id, plugin-opinion razor]
      summary: "A fourth validated top-level config block, audit:, added 2026-10-02 with one key, fix_mode: apply | propose (default apply). propose reports FIX findings as proposals and edits nothing. The guard is code-enforced only on the multi-file fan-out path and, as originally decided, failed open when args.fixMode was not threaded; both limits were deliberate. Limitation (2) was reversed from skills-kit 0.88.0: see silent_noops_fail_loudly."
      detail: |
        Surface: the same 2026-10-02 razor audit. md-domain's audit applied FIX
        findings as edits with no per-finding decision (audit-lane.md step 5,
        "FIX = apply"), and review mode, the only mode that applies nothing, is
        scoped to gating a change rather than to a standing preference. A consumer
        who wanted audit results and never an edit had no supported setting. The
        user ruled "Build the seam"; the register-entry route was ruled out.
        Finding: there is no Python applier to gate. "FIX = apply" lives in prose
        and in the generated lane prompts, so the only code-owned chokepoint is
        the remediate lanes (generated from scripts/gen_workflow_js.py). Review
        mode's no-apply path is not reusable: it is entangled with pre-image
        materialization through VCS calls, the model-judged attributability filter
        and the DIFF-CLEAN relabel, and is rejected in combination with `fast`.
        The key is a behaviour setting rather than a rule id, so it went into a
        fourth validated top-level block (AUDIT_KEYS and _validate_audit in
        standards_resolve.py, following the ADAPTER_KEYS allowlist pattern)
        rather than into the `rules:` namespace. The value is surfaced through
        resolve_standards.py's JSON and enforced by a guard in the four
        *-remediate.js lanes that returns before any agent() call.
        Follow-up: two known limitations, both deliberate.
        (1) The guard is code-enforced only on the fan-out path for two or more
        files. The single-file path is an agent making an inline Edit, with no
        script to guard, so there it is enforced by a shipped instruction in
        audit-lane.md step 5. A seam that silently stopped working below a
        file-count threshold would be a fake gate, so the instruction covers it;
        the asymmetry is real.
        (2) The guard reads args.fixMode threaded by the main loop, so it fails
        OPEN when the loop omits it. This matches the existing disabledCriteria
        threading, which defaults to "apply every criterion" when omitted, so it
        is a property of the lane-args design rather than something this change
        introduced. A fail-closed variant would need an args.configResolved
        sentinel and a changed lane contract across four lanes; it was judged not
        worth that while the sibling mechanism fails open the same way.
        Reversal note (2026-10-02): limitation (2) was reversed in skills-kit
        0.88.0, together with the disabledCriteria fail-open it cited; see
        silent_noops_fail_loudly below. Limitation (1) stands.
        Consumer-facing text, including both limitations: configuring-standards.md,
        "Audit behaviour (audit:)".
      origin: Surface, finding and follow-up above; the user's ruling was "Build the seam", 2026-10-02.
      added: "2026-10-02"
    - id: silent_noops_fail_loudly
      keywords: [reversal, fails open, fail closed, required lane input, fixMode required, disabledCriteria required, pyyaml unavailable, StandardsUnavailableError, --primitive code_directory, usage error, silent no-op, accepted then ignored, thresholds consumed]
      summary: "2026-10-02 (skills-kit 0.88.0): four inputs that were accepted and then ignored fail loudly. This REVERSES limitation (2) of audit_block_fix_mode above: fixMode and disabledCriteria are required workflow inputs, and an absent value throws."
      detail: |
        Surface: an audit of skills-kit for silent no-ops, following the 0.86.0
        regression in which widening `applies_to` turned a loud
        StandardsConfigError into a silently ignored standards file. User
        ruling: an error that is silently swallowed must never be deferred.
        Finding, per case.
        (1) fixMode. audit_block_fix_mode recorded the fail-open as deliberate,
        on the reasoning that disabledCriteria failed open the same way and a
        fail-closed variant would need a sentinel. Both lanes are fixed
        together, so the parity argument no longer holds, and no sentinel was
        needed: fixMode must be "apply" or "propose", and anything else,
        absence included, throws in the generated remediate template before
        any dispatch. Limitation (1), the single-file inline path, stands.
        (2) disabledCriteria. The four detect lanes (claude-md, skill,
        project-doc, coverage) required no list and read absence as "nothing
        disabled". From 0.88.0 the list is required; an empty array is the explicit
        "nothing disabled". The guard is one shared chunk pinned by
        gen_workflow_js.py's check_shared_chunks.
        (3) pyyaml unavailable. resolve() returned empty defaults plus a note,
        and resolve_standards.py exited 0, so every config and standards file
        was ignored while the output read like "nothing configured". resolve()
        raises StandardsUnavailableError (a StandardsConfigError), naming
        the skills-kit venv. emit_audit_jobs.resolve_admitted_endpoints catches
        it by name, but re-raises (main exits 5) when any config or
        *-standards.md layer file exists on disk, because narrowing then
        silently ignores a configured admitted_endpoints. It returns the empty
        admission, with no message, only when no layer file exists. Every other
        caller stops, except the audit's shipped-layer path, which degrades to
        deferred judgment-required rows (see shipped_standards_layer_enabled,
        ruling 5).
        (4) `--primitive code_directory`. The answer was always `[]`, because
        authored code_directory sets are rejected at load. A --primitive in
        APPLIES_TO_NOT_CONSUMED, or an unknown name, is a usage error.
        Not a silent no-op: `thresholds`. Every accepted key is a key of
        audit.THRESHOLDS, every one is read by audit.py, and audit.py runs
        under --config in the skill and claude-md detect lanes. Thresholds are
        not scoped per lane, so no key can be configured that no consumer
        reads; the coverage lane's not reading them drops nothing a user set
        for it. Nothing changed for this case.
        Follow-up: callers outside skills-kit that dispatch the detect lanes
        must thread disabledCriteria (git-kit's and p4-kit's
        md-domain-review.md references).
      origin: Surface, finding and follow-up above; user ruling 2026-10-02.
      added: "2026-10-02"
    - id: shipped_standards_layer_enabled
      keywords: [shipped_dir enabled, layer 0, SHIPPED_STANDARDS_DIR, defaults/standards, SKILL-standards.md, MECHANICAL_EVALUATORS, desc-160-char, desc_max_chars, criterion-declared threshold, duplicate criterion id, mechanical without evaluator, M5]
      summary: "skills-kit 0.92.0 enables resolve()'s shipped_dir on a dedicated directory, skills_kit_lib/defaults/standards/, holding only SKILL-standards.md. desc-160-char, desc-directive-form and desc-exclusion-clause moved out of rule_catalog.RULES into that file as mechanical criteria evaluated by audit.MECHANICAL_EVALUATORS; the 160 default moved into the criterion. Supersedes \"shipped_dir remains unused\" in coverage_criteria_configurable_by_id."
      detail: |
        Surface: the three description-hygiene rows were hard-coded in
        audit.check_universal, with the 160 limit in audit.THRESHOLDS and the
        statements in rule_catalog.RULES. The schema already allowed
        `enforcement: mechanical`, but nothing evaluated an authored mechanical
        criterion, so the standards file was not the source of truth its owner
        doc claimed.
        Finding: coverage_criteria_configurable_by_id showed pointing
        shipped_dir at references/standards/ is fatal (documents without a
        standards_set block; coverage-standards.md's code_directory). A
        dedicated directory holding only SKILL-standards.md avoids both causes
        without narrowing the glob, which would silently skip a user file that
        lost its block. The directory sits inside skills_kit_lib/ because
        bootstrap's shared_libs step copies only that package, the same reason
        defaults/lane_models.yaml lives there.
        Rulings (orchestrator D0-D2 plus a cross-check's amendments):
        (1) resolve() defaults shipped_dir to SHIPPED_STANDARDS_DIR; None opts
        out; a missing directory or SKILL-standards.md raises, and every SKILL.md
        audit exits 1. (2) The default lives in the criterion
        (`threshold: {name: desc_max_chars, default: 160}`); overrides are
        validated against audit.THRESHOLDS plus criterion-declared thresholds;
        a declaration that is malformed, not the one its evaluator reads, on a
        non-mechanical criterion, equal to a built-in threshold, or declared
        twice raises. (3) A criterion id repeated within a list, across files,
        layers or subjects, or equal to any rule_catalog id raises, naming both
        sources. (4) A mechanical criterion with no registered evaluator
        raises. (5) Without pyyaml the audit verifies the shipped file exists
        and emits one deferred judgment-required row per registered evaluator,
        assuming no severity or default; --config stays loud. Standards are
        resolved only after the CLAUDE.md / AGENTS.md dispatch. (6) A plain
        audit (no --config) applies the shipped layer alone, so its output
        depends on the install only. (7) resolve_standards.py keeps shipped
        files out of its `standards` map, so the detect lanes do not apply the
        mechanical criteria a second time; emit_audit_jobs opts out with
        shipped_dir=None; evidence_pack propagates a configuration or
        shipped-file error and degrades only on a missing pyyaml.
        A consequence of (7): with the shipped layer opted out, a config that
        disables desc-160-char or tunes desc_max_chars must still resolve, so
        every registered evaluator's id and threshold name is accepted as a
        knob whether or not its layer was read.
        Follow-up: skill-type-tag and skill-type-valid stay in the catalog;
        they are the next candidates. Verification: the golden corpus stayed
        byte-identical, and the shipped-standards regression test fails when a
        criterion is removed from a copy of the shipped file.
      origin: Surface, finding and follow-up above; milestone M5 of the configurable-standards work.
      added: "2026-10-16"
    - id: skill_type_criteria_shipped
      keywords: [skill-type-tag, skill-type-valid, SkillContext, applies gate, MechanicalEvaluator, evaluator context, frontmatter hygiene, deferred row, no pyyaml, M6, shipped standards]
      summary: "skills-kit 0.93.0 moves skill-type-tag and skill-type-valid out of audit.check_universal and rule_catalog.RULES into the shipped SKILL-standards.md as mechanical criteria. An evaluator receives a SkillContext (frontmatter, body, skill dir) and carries an applies gate that decides whether the criterion has a row for the document. Extends shipped_standards_layer_enabled."
      detail: |
        Surface: the two skill-type rows were hard-coded in check_universal and
        catalogued in rule_catalog.RULES as optional description-hygiene rules.
        The shipped layer evaluated only criteria that read the description
        string, so they stayed behind when the description rows moved.
        Finding: the two checks depend on which frontmatter keys exist, not on
        one value. skill-type-tag has a row only while the tag is absent;
        skill-type-valid has a row only while it is present. A criterion that is
        always evaluated cannot express that.
        Rulings: (1) MechanicalEvaluator.evaluate takes a SkillContext and the
        effective thresholds; the description evaluators read the description
        from the context. (2) MechanicalEvaluator.applies(SkillContext) -> bool
        gates the row. It runs in resolved and deferred modes, reads no
        threshold, and a criterion it rejects produces no row. (3) The criteria
        rows are emitted right after the description row whether the
        description is present or absent, so a SKILL.md without a description
        still gets its skill-type row. (4) The statements, severities (tag:
        judgment, valid: fail) and keywords live in the shipped file; the row
        labels, notes and verdicts are unchanged from the hard-coded block. (5)
        The catalog counts become 39 optional, 11 inoffensive, 3 architectural.
        Accepted regression: without pyyaml the shipped file cannot be read, so
        both rows are deferred judgment-required rows. skill-type-valid on an
        invalid value is therefore judgment-required, not a FAIL, on a bare
        interpreter, and the absent-tag row carries the "(deferred)" label. A
        run under the skills-kit plugin venv is unchanged.
        Follow-up: none for these ids. Verification: the golden corpus stayed
        byte-identical, and the shipped-standards regression test fails when
        skill-type-valid is removed from a copy of the shipped file.
      origin: Surface, finding and follow-up above; milestone M6 wave 1 of the configurable-standards work.
      added: "2026-10-16"
    - id: claude_md_criteria_shipped
      keywords: [claude-md-import-size, claude-md-size-signal, claude-md-record-floor, CLAUDE-md-standards.md, ClaudeMdContext, reads_builtin_thresholds, builtin threshold, import_max_lines, section, shipped file list, deferred row, no pyyaml, M6, shipped standards]
      summary: "skills-kit 0.94.0 moves claude-md-import-size, claude-md-size-signal and claude-md-record-floor out of audit.py and rule_catalog.RULES into the shipped CLAUDE-md-standards.md as mechanical criteria. An evaluator reads a built-in threshold without declaring it (reads_builtin_thresholds); a criterion declares only a threshold it alone owns. Extends skill_type_criteria_shipped."
      detail: |
        Surface: three optional CLAUDE.md rows were hard-coded in
        check_claude_md_defaults and audit_claude_md, and catalogued in
        rule_catalog.RULES. The CLAUDE.md audit did not resolve standards at
        all, so it never needed the shipped layer.
        Finding: one of the three needs a limit no other rule reads
        (import_max_lines), one needs limits the SKILL.md body-size-signal rule
        also reads (body_max_lines, body_max_tokens), and one applies only when
        the file carries a parsed claude_md: block. The import scan also feeds
        the inoffensive claude-md-links-resolve rule, which reports a missing
        import and stays hard-coded.
        Rulings: (D1) Built-in thresholds stay built in. body_max_lines and
        body_max_tokens remain in audit.THRESHOLDS, so a user override moves
        the SKILL.md rule and the CLAUDE.md rule together. A criterion declares
        only a threshold it alone owns. An evaluator names the built-in
        thresholds it reads in MechanicalEvaluator.reads_builtin_thresholds,
        needs no declaration for them, and receives a view holding only the
        thresholds its record names (its owned one plus those), so an
        undeclared read fails loudly. A criterion that declares a built-in
        threshold is still rejected, even one its evaluator reads. (2)
        import_max_lines moves from audit.THRESHOLDS into the
        claude-md-import-size criterion (`threshold: {name: import_max_lines,
        default: 50}`). The config key is unchanged: `thresholds:
        {import_max_lines: <int>}` tunes it, and the key stays a valid knob when
        the shipped layer is opted out. (3) A ClaudeMdContext (path, content,
        body, parsed claude_md: mapping or None) is a second context type beside
        SkillContext; the evaluator's applies_to names which one it receives.
        SkillContext was not generalised because a skill has a frontmatter and a
        directory and a CLAUDE.md has neither. (4) claude-md-record-floor gates
        on `applies`: it has a row only when the parsed block is a mapping. (5)
        MechanicalEvaluator.section places a row in the universal or the
        yaml_contract list, so the floor keeps its position after the contract
        rows and the other two keep theirs after the links and fences rows. (6)
        mechanical_criteria(applies_to, resolved) replaces skill_md_criteria and
        serves both file types. (7) standards_resolve requires a list of shipped
        files, SKILL-standards.md and CLAUDE-md-standards.md; a missing one is a
        StandardsConfigError for every SKILL.md and CLAUDE.md audit. (8) Labels,
        notes, verdicts, positions and the claude-md-size-signal
        judgment-not-fail outcome are unchanged; severity judgment maps a
        failed evaluation to judgment-required.
        Accepted regression: without pyyaml the shipped files cannot be read, so
        claude-md-import-size and claude-md-size-signal become deferred
        judgment-required rows on a bare interpreter. An import over the limit
        is therefore not a FAIL there, and the size row carries none of its
        counts. claude-md-record-floor has no deferred row in practice: the
        claude_md: block it needs cannot be parsed without pyyaml, so its gate
        rejects the document. A run under the skills-kit plugin venv is
        unchanged.
        Follow-up: none for these ids. Verification: the golden corpus stayed
        byte-identical, and the shipped-standards regression tests fail when a
        criterion is removed from a copy of the shipped CLAUDE-md file while the
        rows come from hard-coded criteria.
      origin: Surface, finding and follow-up above; milestone M6 wave 2 of the configurable-standards work.
      added: "2026-10-16"
    - id: body_refs_criteria_shipped
      keywords: [body-line-count, body-token-count, body-size-signal, refs-one-hop-deep, n/a outcome, evaluator outcome, tri-state, info severity, count rows, reads_builtin_thresholds, deferred row, no pyyaml, M6, shipped standards]
      summary: "skills-kit 0.95.0 moves body-line-count, body-token-count, body-size-signal and refs-one-hop-deep out of audit.check_universal and rule_catalog.RULES into the shipped SKILL-standards.md as mechanical criteria. An evaluator may report n/a: its outcome is True (pass), False (violated; severity decides fail or judgment) or None (n/a). Extends claude_md_criteria_shipped."
      detail: |
        Surface: four optional SKILL.md rows were hard-coded in check_universal
        and catalogued in rule_catalog.RULES as layout and thresholds-signals
        rules. Two of them (the counts) are informational, one reads the
        built-in body limits, and one needs the skill directory.
        Finding: an evaluator returned (label, passed: bool, note), which cannot
        say "this criterion has a row but nothing to check". Two of today's rows
        are n/a in ordinary cases: refs-one-hop-deep when the skill has no
        references/ directory, and the progressive-disclosure row
        (body-size-signal) while the body is within the limits. The applies
        gate cannot carry that, because a gated criterion has no row at all and
        the current output has an n/a row.
        Rulings: (D1) body_max_lines and body_max_tokens stay built in;
        body-size-signal names them in reads_builtin_thresholds and owns no
        threshold, so one override moves it and claude-md-size-signal together.
        (D3) body-line-count and body-token-count ship as mechanical criteria of
        severity info that always pass and carry the count in the note; output is
        unchanged and a user can switch either off with rules: {<id>: off}.
        (3) Outcome type: MechanicalEvaluator.evaluate returns True (pass), False
        (violated) or None (n/a). A violation keeps the severity mapping already
        in place (fail severity -> fail, otherwise judgment-required), so
        body-size-signal is severity judgment and refs-one-hop-deep is severity
        fail. A fourth value was not added: pass, violation and n/a are the only
        outcomes today's rows produce, and judgment-required is already what
        severity maps a violation to. The eight existing evaluators return bools
        and are untouched. (4) The four criteria follow skill-type-valid in the
        shipped file, which is their old position (after the skill-type rows and
        before refs-cited-exist, which stays hard-coded). (5) The catalog counts
        become 32 optional, 11 inoffensive, 3 architectural.
        Accepted regression: without pyyaml the shipped file cannot be read, so
        the four rows are deferred judgment-required rows on a bare interpreter.
        An undeclared nested reference is therefore not a FAIL there, the
        progressive-disclosure row is judgment-required at any body size, and
        the count rows carry no count. A run under the skills-kit plugin venv is
        unchanged. The current no-pyyaml output of these ids could not be kept:
        a deferred row needs the file's severity, which is the one thing that
        cannot be read.
        Follow-up: none for these ids. Verification: the golden corpus stayed
        byte-identical, and the shipped-standards regression tests fail when a
        criterion is removed from a copy of the shipped file while the rows come
        from hard-coded code.
      origin: Surface, finding and follow-up above; milestone M6 wave 3 of the configurable-standards work.
      added: "2026-10-16"
    - id: contract_floor_criteria_shipped
      keywords: [facts-floor, facts-gotcha, facts-example, caution-floor, yaml_contract section, SkillContext yaml_root, yaml_units, applies gate, contract-staged, no pyyaml, no deferred row, record floors, M6, shipped standards]
      summary: "skills-kit 0.96.0 moves facts-floor, facts-gotcha, facts-example and caution-floor out of audit.py's check_facts_cross_rules and check_technique_caution_cross_rule and out of rule_catalog.RULES into the shipped SKILL-standards.md as mechanical criteria that join the yaml_contract list. Extends body_refs_criteria_shipped."
      detail: |
        Surface: four optional YAML-contract floors were emitted by two
        hard-coded functions that ran after the portable-unit rows, and were
        catalogued in rule_catalog.RULES as record-floors rules. The skill_md
        evaluators so far ran inside check_universal, before the contract is
        parsed.
        Finding: these floors read two things the universal rows never had,
        the document's parsed YAML units and the contract root the audit
        resolved (the facts floor gates on that root, with the frontmatter tag
        as the fallback only for a document with no recognized root). The
        yaml_contract section already existed for claude-md-record-floor, but a
        skill_md audit placed none of its rows by section.
        Rulings: (1) SkillContext gains yaml_root and a cached yaml_units. The
        root is a result of the contract check, so the universal context leaves
        it unset and audit() builds a second context once the root exists;
        the units are parsed on first use and shared, so the four evaluators
        parse the body once. (2) The four evaluators declare section
        "yaml_contract"; check_universal runs only the universal ones, and
        audit() runs the yaml_contract ones after check_portable_units and
        before check_asset_dependencies_resolve, which is where the removed
        functions emitted. Row order, labels, notes and verdicts are unchanged.
        (3) facts-gotcha and facts-example have an applies gate that is true
        only when at least one fact is declared, because the removed function
        returned after the floor row when no fact existed. (4) None declares a
        threshold: each floor is "at least one", with no count in THRESHOLDS.
        (5) The catalog counts become 28 optional, 11 inoffensive, 3
        architectural. (6) The two removed functions are deleted, not kept as
        wrappers.
        No-pyyaml output is preserved exactly: the floors had no row on a
        bare interpreter, so the applies gate is false without pyyaml and the
        rows are not deferred rows. That differs from waves 1 to 3, whose rows
        become deferred there, and it is why this wave has no accepted
        regression.
        Behaviour kept that the contract-only reading would miss: a SKILL.md
        tagged skill-type: reference-skill with no contract block still gets a
        facts-floor row (the tag is the fallback gate), and a reference block
        that fails to parse still gets one.
        Follow-up: none for these ids. Verification: the output of 39 fixtures
        (every case above, with and without pyyaml) was byte-identical before
        and after, the golden corpus stayed byte-identical, and the
        shipped-standards regression tests fail when a criterion is removed
        from a copy of the shipped file while the rows come from hard-coded
        code.
      origin: Surface, finding and follow-up above; milestone M6 wave 4 of the configurable-standards work.
      added: "2026-10-16"
    - id: legacy_heuristic_criteria_shipped
      keywords: [SKILL-legacy-standards.md, legacy heuristics, type_specific section, ref-example-block, pattern-prohibited-bundle, technique-ordered-steps, step-tracking, discipline-pressure-test, domain-orientation, bare_severity, JUDGMENT outcome, contract_staged, applies gate, fence-stripped body, no pyyaml, coverage ids stay, D2, D4, M6, shipped standards]
      summary: "skills-kit 0.97.0 moves the 19 legacy per-skill-type heuristic ids (ref-*, pattern-*, technique-*, discipline-*, domain-*) and step-tracking out of audit.py's per-type check functions and out of rule_catalog.RULES into a dedicated shipped file, SKILL-legacy-standards.md, as mechanical criteria in the type_specific list. The eight coverage ids stay in the catalog. Extends contract_floor_criteria_shipped."
      detail: |
        Surface: twenty optional rules were emitted by five hard-coded
        functions, one per skill type, selected by a TYPE_RUNNERS table, and
        catalogued in rule_catalog.RULES as legacy-heuristics (step-tracking as
        a record floor). They ran only for a SKILL.md with no staged YAML
        contract, only for its declared skill-type, and against the body with
        fenced code removed.
        Finding: unlike the rows moved in waves 1 to 4, these rows are scoped
        by the document's declared type and by the absence of a contract, have
        a third report list of their own (type_specific), and have always kept
        their real verdict on a bare interpreter, because each is a
        deterministic heading, marker or filesystem test.
        Decision D4 (settled): keep the 20 legacy rows mechanical, in a separate
        shipped SKILL-legacy-standards.md (applies_to skill_md), split into
        per-skill-type commits; preserve the rules that legacy rows run only
        without a staged contract, only for the declared skill type, and
        against code-fence-stripped prose.
        Decision D2 (settled, restated because it bounds this wave): the eight
        coverage ids (absent-fact-earns-ambient-cost through
        present-content-not-re-audited) stay registered in rule_catalog.RULES.
        Their criteria are shipped data in
        skills/md-domain/references/standards/coverage-standards.md and are
        applied by an agent in the coverage lane, which reads the catalog to
        know the id is disableable; they have no evaluator. The catalog is
        therefore 8 optional, 11 inoffensive and 3 architectural.
        Rulings: (1) A third evaluator section, type_specific. audit() evaluates
        it last, with a SkillContext whose body is the fence-stripped narrative
        body and which carries contract_staged. (2) The scope is an applies
        predicate on each evaluator (no staged contract and a declared
        skill-type equal to the one the criterion covers), not a field in the
        standards file: the standards schema has no scope key, the facts floors
        already gate on the contract root the same way, and the criterion's
        statement names its type. (3) MechanicalEvaluator.bare_severity: the
        legacy rows must keep their real verdict without pyyaml, where the
        shipped file cannot be read, so each evaluator carries a copy of its
        criterion's severity that is used instead of a deferred row. This is
        the one place a severity lives in code; a test pins every copy equal to
        the shipped file, so the file stays the source. Waves 1 to 3 accepted
        deferred rows on a bare interpreter; this wave does not, because the
        legacy heuristics are the only audit a no-contract skill gets there.
        (4) An evaluator outcome may also be JUDGMENT. discipline-pressure-test
        has three outcomes: no marker is a miss, and a marker is neither a pass
        nor a miss but a row the agent must verify, so it is judgment-required
        whatever severity a layer would give the criterion. (5)
        SHIPPED_REQUIRED_STANDARDS gains the legacy file; a missing file is a
        StandardsConfigError on a bare interpreter too. (6) step-tracking is
        technique-scoped, so it ships with the technique criteria, between the
        other two in file order, and is n/a (keeping its "only N steps" note)
        with three or fewer steps. (7) TYPE_RUNNERS, the five check_*_skill
        functions and the special case that routed technique-skill around the
        table left the audit path; audit() runs none of them, and the two
        tests that called check_technique_skill go through audit(). The names
        themselves stay as deprecation shims (m6_deprecation_shims).
        Severity per id copies the old verdict on a miss: five rows are
        judgment (ref-example-block, ref-gotcha-block,
        pattern-recognition-block, pattern-counter-example and
        domain-identity-sentence) and the other fifteen are fail.
        Behaviour kept: a reference-skill, pattern-skill, technique-skill,
        discipline-skill or domain-skill tag with a contract block gets no
        legacy row, an untagged skill or a capability-skill or audit-skill gets
        none, a marker that appears only inside a code fence does not count,
        and rows keep their labels, notes, verdicts and positions. No behaviour
        change, including without pyyaml.
        Follow-up: none for these ids. Verification: the output of 738
        generated fixtures (every skill type, tagged and untagged, contract
        staged and not, fenced markers, each marker present and absent, step
        counts 0 to 7, H2 counts 0 to 3, scripts/ and bin/ directories) plus
        the 29 SKILL.md files of the repo was byte-identical before and after
        at every one of the five commits, with and without pyyaml; the same
        fixtures through resolve() matched the default-mode output; the golden
        corpus stayed byte-identical; and the red-on-revert tests fail when a
        criterion is removed from a copy of the shipped file while the rows
        come from hard-coded code, and when the contract gate is removed.
      origin: Surface, finding and follow-up above; milestone M6 wave 5 of the configurable-standards work.
      added: "2026-10-16"
    - id: m6_deprecation_shims
      keywords: [deprecation shim, DeprecationWarning, deprecation policy, SkillCriterion, skill_md_criteria, TYPE_RUNNERS, check_reference_skill, check_facts_cross_rules, check_claude_md_record_floor, check_claude_md_defaults, THRESHOLDS import_max_lines, contract/public-surface.json, remove_after, 0.99.0, shared lib, skills_kit_lib, M6]
      summary: "skills-kit 0.97.0 restores the audit.py names that waves 1 to 5 of M6 removed or narrowed, as deprecation shims removable in 0.99.0: SkillCriterion, skill_md_criteria, TYPE_RUNNERS, the five check_<type>_skill functions, check_facts_cross_rules, check_technique_caution_cross_rule, check_claude_md_record_floor, the body and th arguments of check_claude_md_defaults, and the import_max_lines key of THRESHOLDS. Supersedes the deleted-not-wrapped ruling in legacy_heuristic_criteria_shipped (7)."
      detail: |
        Surface: skills_kit_lib is published as a shared library
        (bootstrap.json shared_libs), so the module-level names of audit.py are
        public under the marketplace deprecation policy (rule 1: a public name is anything a consumer can import). Waves 1 to 5
        removed eleven names and dropped two parameters of
        check_claude_md_defaults without the two-minor-version shim window the
        policy requires; the waves' rulings (deleted, not kept as wrappers)
        reasoned from "no caller in this repository" and did not weigh
        consumers in other repositories.
        Finding: a review of the range confirmed the removals as a policy
        violation, and the policy's rule 4 prescribes the remedy: restore a
        shim, as a fix forward.
        Ruling: each shim keeps the old name and the old call shape, emits
        DeprecationWarning with stacklevel=2 naming the replacement and the
        removal version (deprecated in 0.97.0, removable in 0.99.0, the second
        minor release after it), and returns what the former function returned
        by delegating to the shipped criteria through the current evaluator
        path. The five check_<type>_skill shims build their rows from the
        legacy criteria with no severity, so each takes its evaluator's
        bare_severity (pinned equal to SKILL-legacy-standards.md); the facts,
        caution and record-floor shims pass severity fail, the verdict the
        former functions hard-coded. SkillCriterion is MechanicalCriterion and
        TYPE_RUNNERS is a table of the four runners it held, both served by a
        module __getattr__ so that an access warns. check_claude_md_defaults
        called with the former four arguments warns and also returns the
        import-size and size-signal rows it used to append, computed by the
        shipped evaluators with the caller's th; the two-argument call is
        unchanged and silent. THRESHOLDS is a dict subclass whose
        __missing__ answers import_max_lines (50, pinned equal to the shipped
        criterion's default) with a warning; the key is still not a member, so
        the standards resolver still refuses a criterion that declares it.
        MechanicalEvaluator and MECHANICAL_EVALUATORS are not shimmed: they are
        the in-library seam that binds a shipped criterion id to code, no
        consumer outside skills-kit reaches it, and a registration made for the
        former evaluate(description, thresholds) shape cannot be adapted to the
        context argument without guessing which shape a callable expects.
        They are not listed in the contract.
        Follow-up: delete the shims, their tests, and the deprecated entries
        of contract/public-surface.json (recording them as removed) in the
        release that carries 0.99.0 or later; the shim
        test module (test_audit_deprecation_shims.py) fails once the plugin version reaches
        remove_after. Verification: each shim's rows matched the original
        functions (commit efd43c8b, skills-kit 0.92.1) over 40229 comparisons
        (6428 generated bodies and the 29 SKILL.md files of the repo through
        each type function, 50 YAML documents through the floors, 45
        CLAUDE.md texts through the defaults), with and without pyyaml; the
        captured original rows are pinned in the test.
      origin: Surface, finding and follow-up above; review of skills-kit 0.92.1 to 0.97.0 against the marketplace deprecation policy.
      added: "2026-10-16"
```
