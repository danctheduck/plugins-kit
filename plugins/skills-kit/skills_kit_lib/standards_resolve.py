"""standards_resolve -- resolve the layered skills-kit standards configuration.

skills-kit ships all its opinions on by default; a user tunes the OPTIONAL layer
(never the architectural spine, never the inoffensive integrity checks) through
version-controllable config that mirrors bootstrap.json layering:

    0  shipped_dir (default SHIPPED_STANDARDS_DIR, skills_kit_lib/defaults/standards/;
       must exist and hold at least one *-standards.md; None opts out)
    1  <user_dir>/skills-kit/                    config.yaml + *-standards.md
    2  <user_dir>/skills-kit/config.local.yaml   per-machine config overlay
    3  <project>/.claude/skills-kit/             config.yaml + *-standards.md
    4  <project>/.claude/skills-kit/config.local.yaml  personal config overlay

<user_dir> = $CLAUDE_CONFIG_DIR else ~/.claude (the harness config dir). Config
merges later-wins (deep-merge); standards files UNION across layers (a later
layer appends, never replaces).

Self-contained by design: stdlib + pyyaml only, no bootstrap_lib import (that
would take a shared_lib_imports manifest change and break audit.py's graceful
bare-python degradation). Importing this module never needs pyyaml, but
RESOLVING does: when pyyaml is unavailable resolve() raises
StandardsUnavailableError naming the missing dependency and the venv to use,
because returning empty defaults would ignore every config and standards file
while reading exactly like "nothing configured". Malformed config, an un-tunable rule id, an unknown
threshold, an unknown adapter or adapter setting, an unknown audit setting or value, or an invalid standards file
are LOUD (StandardsConfigError), never a silent {}. So are a missing shipped
standards layer (each of SHIPPED_REQUIRED_STANDARDS), a criterion id repeated anywhere in the resolved layers or
equal to a rule_catalog id, an `enforcement: mechanical` criterion with no
registered evaluator (audit.MECHANICAL_EVALUATORS), and a malformed or
conflicting criterion `threshold:` declaration.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import rule_catalog
from .audit import MECHANICAL_EVALUATORS, THRESHOLDS
from .document_walker import collect_yaml_units
from .schema_engine import validate
from .schema_registry import SCHEMAS_BY_ROOT

try:
    import yaml as _yaml
    HAVE_YAML = True
except ImportError:  # pragma: no cover - exercised only on a bare interpreter
    _yaml = None
    HAVE_YAML = False


#: Layer 0: the standards skills-kit ships. Inside the package because
#: bootstrap's shared_libs step copies only skills_kit_lib/ (bootstrap.json),
#: the same reason defaults/lane_models.yaml lives beside it. resolve() reads
#: this module attribute at call time, never as a bound default.
SHIPPED_STANDARDS_DIR = Path(__file__).resolve().parent / "defaults" / "standards"

#: The shipped files carrying the criteria audit.py evaluates: skill_md (the
#: general file and the legacy per-skill-type heuristics) and claude_md. Each
#: must exist in the shipped directory.
SHIPPED_SKILL_STANDARDS = "SKILL-standards.md"
SHIPPED_LEGACY_STANDARDS = "SKILL-legacy-standards.md"
SHIPPED_CLAUDE_MD_STANDARDS = "CLAUDE-md-standards.md"
SHIPPED_REQUIRED_STANDARDS = (
    SHIPPED_SKILL_STANDARDS,
    SHIPPED_LEGACY_STANDARDS,
    SHIPPED_CLAUDE_MD_STANDARDS,
)

#: Sentinel for "use SHIPPED_STANDARDS_DIR"; an explicit None opts out.
_SHIPPED_DEFAULT = object()

_THRESHOLD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


#: The file-type primitives a standards_set's `applies_to:` may name
#: (schemas/standards.py's owner-doc note; configuring-standards.md's
#: "Additive standards files" table). Defined once here, next to the
#: schema's note, so both stay in sync.
APPLIES_TO_PRIMITIVES = ("skill_md", "claude_md", "reference_doc", "plain_md")

#: Composition ids recognised as `applies_to:` names (the analyze lane's
#: subject: one directory plus its ambient CLAUDE.md chain). Recognised is not
#: authorable: see APPLIES_TO_NOT_CONSUMED.
APPLIES_TO_COMPOSITIONS = ("code_directory",)

#: Every recognised `applies_to:` value.
APPLIES_TO_SUBJECTS = APPLIES_TO_PRIMITIVES + APPLIES_TO_COMPOSITIONS

#: Deprecated `applies_to:` spellings, normalised to the current id so a
#: file carrying the former name `code_subtree` gets the same error as one
#: naming `code_directory`.
APPLIES_TO_ALIASES = {"code_subtree": "code_directory"}

#: Subjects that are valid NAMES (the registry and `--primitive` use them) but
#: have no lane that applies an AUTHORED standards set: the coverage lane reads
#: only its shipped criteria and `disabledCriteria`, never the resolved
#: `standards` map. An authored set naming one is rejected loudly rather than
#: validated and then silently ignored. Wiring a lane to consume a subject's
#: authored criteria means removing that subject from this set.
APPLIES_TO_NOT_CONSUMED = frozenset(APPLIES_TO_COMPOSITIONS)

#: The `applies_to:` values an authored set may carry.
_AUTHORABLE_SUBJECTS = tuple(
    s for s in APPLIES_TO_SUBJECTS if s not in APPLIES_TO_NOT_CONSUMED
)


class StandardsConfigError(Exception):
    """A resolved standards layer is malformed or names something un-tunable.

    Raised loudly rather than degrading to a silent empty config: a broken
    config file, an attempt to disable an architectural/inoffensive/unknown
    rule, an unknown threshold key, a bad value, or an invalid *-standards.md.
    """


class StandardsUnavailableError(StandardsConfigError):
    """Resolution cannot run on this interpreter: pyyaml is not importable.

    A subclass of StandardsConfigError so every caller that already stops on a
    malformed layer also stops here. A caller that deliberately tolerates an
    unresolvable config (emit_audit_jobs.resolve_admitted_endpoints) catches
    this subclass by name, but only to stay quiet when
    existing_layer_files() finds nothing to ignore; with any layer file on
    disk it re-raises.
    """


#: The one adapter id this configuration surface knows, and the keys it takes.
#: An adapter is task-specific context admitted for the model-task pairs it was
#: MEASURED on. The shipped default admits nothing, so an unconfigured user gets
#: the behaviour of not having the adapter at all.
ADAPTER_MD_AUDIT_EVIDENCE_PACK = "md-audit-evidence-pack"
ADAPTER_KEYS: dict[str, set[str]] = {
    ADAPTER_MD_AUDIT_EVIDENCE_PACK: {"admitted_endpoints"},
}


#: The audit-behaviour settings, a fourth top-level config block (`audit:`).
#: These are behaviour settings, not rule ids, so they do not live under
#: `rules:`. Each key maps to its allowed values; the FIRST value is the shipped
#: default. `fix_mode: apply` applies FIX findings as edits (the audit's
#: default); `fix_mode: propose` reports every FIX finding as a proposal and
#: makes no edit.
AUDIT_KEYS: dict[str, tuple[str, ...]] = {
    "fix_mode": ("apply", "propose"),
}
AUDIT_DEFAULTS: dict[str, str] = {key: values[0] for key, values in AUDIT_KEYS.items()}


@dataclass
class StandardsFile:
    """One authored *-standards.md, parsed and schema-validated."""

    path: Path
    applies_to: str
    criteria: list
    #: Which layer the file came from: "shipped", "user" or "project".
    layer: str = "user"


@dataclass
class ResolvedStandards:
    """The merged view of every standards layer for one resolution.

    - disabled_rules: optional rule ids the config switched off.
    - thresholds: threshold OVERRIDES only (names present in the config); an
      absent name keeps its default (audit.THRESHOLDS, or threshold_defaults).
    - threshold_defaults: threshold name -> default, for each threshold a
      resolved standards criterion declares (`threshold: {name, default}`).
    - standards_by_primitive: applies_to value -> the StandardsFiles governing
      it, unioned across layers in layer order.
    - adapters: adapter id -> that adapter's settings, for the ids in
      ADAPTER_KEYS. An absent adapter, or an absent key inside one, keeps the
      shipped default -- which for every adapter setting is EMPTY.
    - audit: the audit-behaviour settings (AUDIT_KEYS), always fully populated:
      a key the config does not set carries its AUDIT_DEFAULTS value.
    - notes: loud-but-non-fatal diagnostics. A missing pyyaml is not one: it
      raises StandardsUnavailableError instead.
    """

    disabled_rules: set[str] = field(default_factory=set)
    thresholds: dict[str, int] = field(default_factory=dict)
    threshold_defaults: dict[str, int] = field(default_factory=dict)
    standards_by_primitive: dict[str, list[StandardsFile]] = field(default_factory=dict)
    adapters: dict[str, dict] = field(default_factory=dict)
    audit: dict[str, str] = field(default_factory=lambda: dict(AUDIT_DEFAULTS))
    notes: list[str] = field(default_factory=list)

    def adapter_admitted_endpoints(self, adapter_id: str) -> frozenset[str]:
        """The endpoint ids admitted for one adapter; empty when unconfigured."""
        settings = self.adapters.get(adapter_id) or {}
        return frozenset(settings.get("admitted_endpoints", ()))


def _config_dir() -> Path:
    """The harness config dir: $CLAUDE_CONFIG_DIR if set, else ~/.claude.

    A small local reimplementation of md-domain/scripts/discover_project_doc.py's
    _config_dir -- copied deliberately rather than imported, so the lib takes no
    dependency on a skill's scripts dir.
    """
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Return base updated by overlay, recursing into nested dicts (later-wins).

    Nested mappings merge key-by-key; every other shape (scalar, list, or a
    dict-vs-nondict mismatch) replaces wholesale.
    """
    result = dict(base)
    for key, val in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _load_config_file(path: Path) -> dict:
    """Load one config.yaml / config.local.yaml layer.

    Absent -> {} (skip silently). Empty -> {}. Malformed YAML or a non-mapping
    root -> StandardsConfigError naming the path (never a silent {}).
    """
    if not path.exists():
        return {}
    try:
        data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise StandardsConfigError(f"{path}: malformed YAML -- {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise StandardsConfigError(
            f"{path}: config root must be a mapping, got {type(data).__name__}"
        )
    return data


def _is_off(val) -> bool:
    """True when a rules: value means 'disable'. YAML `off` parses to False; a
    quoted "off"/"false" stays a string. Anything else is not a disable value."""
    if val is False:
        return True
    if isinstance(val, str) and val.strip().lower() in ("off", "false"):
        return True
    return False


def _validate_adapters(merged: dict) -> dict[str, dict]:
    """Validate the merged config's `adapters:` block and return its settings.

    An unknown adapter id, an unknown key inside a known adapter, or a value of
    the wrong shape raises rather than being ignored: a typo'd endpoint list
    would otherwise silently admit nothing, which looks exactly like the
    (correct, empty) default and hides the mistake.
    """
    raw = merged.get("adapters", {})
    if raw and not isinstance(raw, dict):
        raise StandardsConfigError(
            f"'adapters:' must be a mapping of adapter-id -> settings, got "
            f"{type(raw).__name__}"
        )
    adapters: dict[str, dict] = {}
    for adapter_id, settings in (raw or {}).items():
        if adapter_id not in ADAPTER_KEYS:
            raise StandardsConfigError(
                f"adapter '{adapter_id}' is not a known adapter; valid adapter "
                f"ids: {sorted(ADAPTER_KEYS)}"
            )
        if not isinstance(settings, dict):
            raise StandardsConfigError(
                f"adapter '{adapter_id}' must be a mapping of setting -> value, "
                f"got {type(settings).__name__}"
            )
        valid = ADAPTER_KEYS[adapter_id]
        extracted: dict = {}
        for key, val in settings.items():
            if key not in valid:
                raise StandardsConfigError(
                    f"adapter '{adapter_id}' has no setting '{key}'; valid "
                    f"settings: {sorted(valid)}"
                )
            if key == "admitted_endpoints":
                if not isinstance(val, list) or not all(
                    isinstance(name, str) and name.strip() for name in val
                ):
                    raise StandardsConfigError(
                        f"adapter '{adapter_id}': admitted_endpoints must be a "
                        f"list of non-empty endpoint id strings; got {val!r}"
                    )
                extracted[key] = [name.strip() for name in val]
            else:  # pragma: no cover - unreachable while every key is handled
                extracted[key] = val
        adapters[adapter_id] = extracted
    return adapters


def _validate_audit(merged: dict) -> dict[str, str]:
    """Validate the merged config's `audit:` block and return the full settings.

    An unknown key, or a value outside the key's allowed set, raises: a typo'd
    `fix_mode` would otherwise silently keep the default and apply edits to a
    consumer who asked for none. Absent keys take their AUDIT_DEFAULTS value.
    """
    raw = merged.get("audit", {})
    if raw and not isinstance(raw, dict):
        raise StandardsConfigError(
            f"'audit:' must be a mapping of setting -> value, got {type(raw).__name__}"
        )
    settings = dict(AUDIT_DEFAULTS)
    for key, val in (raw or {}).items():
        if key not in AUDIT_KEYS:
            raise StandardsConfigError(
                f"audit setting '{key}' is not a known setting; valid settings: "
                f"{sorted(AUDIT_KEYS)}"
            )
        allowed = AUDIT_KEYS[key]
        if not isinstance(val, str) or val.strip().lower() not in allowed:
            raise StandardsConfigError(
                f"audit setting '{key}' must be one of {list(allowed)}; got {val!r}"
            )
        settings[key] = val.strip().lower()
    return settings


def _evaluator_thresholds() -> set[str]:
    """Threshold names the registered mechanical evaluators own."""
    return {ev.threshold for ev in MECHANICAL_EVALUATORS.values() if ev.threshold}


def _validate_and_extract(
    merged: dict,
    authored_criteria: set[str] | None = None,
    declared_thresholds: set[str] | None = None,
) -> tuple[set[str], dict[str, int]]:
    """Validate the merged config and extract disabled rules + threshold overrides.

    A rules: id that is not an optional rule and not an authored standards
    criterion raises, naming the id and its bucket (architectural/inoffensive/
    unknown). `authored_criteria` is the set of criterion ids declared by the
    standards files resolved for this project (any layer, any primitive); an id
    in that set is a valid config knob even though it is not in the catalog. A
    thresholds: key that is neither in audit's THRESHOLDS nor declared by a
    resolved criterion raises, naming the valid keys. A registered mechanical
    evaluator's id and threshold name are valid knobs even when the layer
    declaring its criterion was opted out (shipped_dir=None): those ids are
    configurable wherever skills-kit runs, and a caller that skips the shipped
    layer must not reject a config written for it. Rule values accept only
    off/false; threshold values must be positive ints.
    """
    disabled: set[str] = set()
    rules = merged.get("rules", {})
    if rules and not isinstance(rules, dict):
        raise StandardsConfigError(
            f"'rules:' must be a mapping of rule-id -> off, got {type(rules).__name__}"
        )
    optional = set(rule_catalog.optional_rule_ids()) | set(MECHANICAL_EVALUATORS)
    authored = authored_criteria or set()
    for rid, val in (rules or {}).items():
        if rid not in optional and rid not in authored:
            bucket = rule_catalog.BUCKETS.get(rid, "unknown")
            raise StandardsConfigError(
                f"rule '{rid}' is {bucket} and cannot be configured; only optional "
                f"rules and authored standards criteria are configurable (see "
                f"rule_catalog.optional_rule_ids())"
            )
        if not _is_off(val):
            raise StandardsConfigError(
                f"rule '{rid}' accepts only 'off' (or false) to disable it; got {val!r}"
            )
        disabled.add(rid)

    thresholds: dict[str, int] = {}
    raw_th = merged.get("thresholds", {})
    if raw_th and not isinstance(raw_th, dict):
        raise StandardsConfigError(
            f"'thresholds:' must be a mapping of name -> int, got {type(raw_th).__name__}"
        )
    valid_thresholds = set(THRESHOLDS) | _evaluator_thresholds() | (declared_thresholds or set())
    for name, val in (raw_th or {}).items():
        if name not in valid_thresholds:
            raise StandardsConfigError(
                f"threshold '{name}' is not a valid threshold; valid keys: {sorted(valid_thresholds)}"
            )
        if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
            raise StandardsConfigError(
                f"threshold '{name}' must be a positive integer; got {val!r}"
            )
        thresholds[name] = val
    return disabled, thresholds


def _parse_standards_file(path: Path, layer: str = "user") -> StandardsFile:
    """Parse + schema-validate one *-standards.md; raise loudly on any defect."""
    text = path.read_text(encoding="utf-8")
    units, _, parse_error = collect_yaml_units(text)
    if parse_error is not None:
        _root, msg = parse_error
        raise StandardsConfigError(
            f"{path}: fenced YAML block failed to parse -- {msg}"
        )
    block: dict | None = None
    for root, data in units:
        if root == "standards_set":
            block = data
            break
    if block is None:
        raise StandardsConfigError(
            f"{path}: no fenced `standards_set:` YAML block found "
            "(a *-standards.md file must carry exactly one)"
        )
    fails, _checked = validate(block, SCHEMAS_BY_ROOT["standards_set"])
    if fails:
        detail = "; ".join(f"{p}: {m}" for p, m in fails)
        raise StandardsConfigError(
            f"{path}: standards_set block failed schema validation -- {detail}"
        )
    inner = block["standards_set"]
    applies_to = inner["applies_to"]
    applies_to = APPLIES_TO_ALIASES.get(applies_to, applies_to)
    if applies_to not in APPLIES_TO_SUBJECTS:
        raise StandardsConfigError(
            f"{path}: applies_to '{applies_to}' is not a file-type primitive "
            f"or composition id; valid values: {list(_AUTHORABLE_SUBJECTS)}"
        )
    if applies_to in APPLIES_TO_NOT_CONSUMED:
        raise StandardsConfigError(
            f"{path}: applies_to '{applies_to}' cannot carry authored criteria: "
            "the coverage lane does not apply them, so this file would be "
            "ignored. To switch a shipped coverage criterion off, set "
            "`rules: {<criterion-id>: off}` in config.yaml (ids: "
            "references/standards/coverage-standards.md). Valid applies_to "
            f"values for an authored set: {list(_AUTHORABLE_SUBJECTS)}"
        )
    return StandardsFile(
        path=path,
        applies_to=applies_to,
        criteria=inner.get("criteria", []),
        layer=layer,
    )


def _validate_criteria(files: list[StandardsFile]) -> dict[str, int]:
    """Cross-file criterion checks over every resolved standards file.

    Raises StandardsConfigError, naming both sources, when a criterion id
    repeats within one list, across files, layers or primitives, or equals a
    rule_catalog id. Raises when an `enforcement: mechanical` criterion has no
    registered evaluator or names a different primitive than its evaluator,
    and when a `threshold:` declaration is malformed, is not the one its
    evaluator consumes, is missing where the evaluator needs it, collides with
    a built-in threshold, or is declared twice. Returns the declared
    threshold defaults (name -> default).
    """
    seen: dict[str, str] = {}
    declared: dict[str, tuple[int, str]] = {}
    for sf in files:
        for index, crit in enumerate(sf.criteria):
            cid = crit["id"]
            here = f"{sf.path} criteria[{index}]"
            if cid in seen:
                raise StandardsConfigError(
                    f"criterion id '{cid}' is declared twice: {seen[cid]} and {here}. "
                    "A criterion id is a config knob and an audit-finding key, so it "
                    "must be unique across every resolved standards file and layer"
                )
            seen[cid] = here
            if cid in rule_catalog.RULES:
                raise StandardsConfigError(
                    f"criterion id '{cid}' at {here} collides with the built-in "
                    f"{rule_catalog.BUCKETS[cid]} rule '{cid}' in "
                    "skills_kit_lib/rule_catalog.py; choose a different id"
                )
            mechanical = crit.get("enforcement") == "mechanical"
            evaluator = MECHANICAL_EVALUATORS.get(cid) if mechanical else None
            if mechanical and evaluator is None:
                raise StandardsConfigError(
                    f"criterion '{cid}' at {here} declares enforcement: mechanical, but "
                    "no evaluator is registered for that id (audit.MECHANICAL_EVALUATORS); "
                    "nothing would evaluate it. Declare it enforcement: judgment so the "
                    "detect lane applies its statement. Registered ids: "
                    f"{sorted(MECHANICAL_EVALUATORS)}"
                )
            if evaluator is not None and evaluator.applies_to != sf.applies_to:
                raise StandardsConfigError(
                    f"criterion '{cid}' at {here} is in a set for '{sf.applies_to}', but "
                    f"its registered evaluator audits '{evaluator.applies_to}'"
                )
            th = crit.get("threshold")
            wanted = evaluator.threshold if evaluator is not None else None
            if th is None:
                if wanted is not None:
                    raise StandardsConfigError(
                        f"criterion '{cid}' at {here} must declare "
                        f"`threshold: {{name: {wanted}, default: <positive int>}}`: its "
                        "evaluator reads that threshold, and the criterion is the only "
                        "source of its default"
                    )
                continue
            name, default = th.get("name"), th.get("default")
            if isinstance(name, str) and name in THRESHOLDS:
                raise StandardsConfigError(
                    f"criterion '{cid}' at {here} declares threshold '{name}', which is "
                    "a built-in threshold (audit.THRESHOLDS); a criterion may declare "
                    "only a threshold no built-in rule owns. An evaluator reads a "
                    "built-in threshold without declaring it "
                    "(MechanicalEvaluator.reads_builtin_thresholds), and a user tunes "
                    "it through `thresholds:`"
                )
            if wanted is None:
                raise StandardsConfigError(
                    f"criterion '{cid}' at {here} declares a threshold, but only a "
                    "mechanical criterion whose registered evaluator consumes a "
                    "threshold may declare one"
                )
            if name != wanted:
                raise StandardsConfigError(
                    f"criterion '{cid}' at {here} declares threshold '{name}', but its "
                    f"evaluator reads '{wanted}'"
                )
            if not isinstance(name, str) or not _THRESHOLD_NAME_RE.match(name):
                raise StandardsConfigError(
                    f"criterion '{cid}' at {here}: threshold name {name!r} is not snake_case"
                )
            if isinstance(default, bool) or not isinstance(default, int) or default <= 0:
                raise StandardsConfigError(
                    f"criterion '{cid}' at {here}: threshold '{name}' default must be a "
                    f"positive integer; got {default!r}"
                )
            if name in declared:
                raise StandardsConfigError(
                    f"threshold '{name}' is declared twice: {declared[name][1]} and {here}"
                )
            declared[name] = (default, here)
    return {name: default for name, (default, _where) in declared.items()}


def require_shipped_standards(shipped_dir: Path | None = None) -> list[Path]:
    """Return the shipped standards files audits need; raise if any is missing.

    Reads no content, so it works without pyyaml: audit.py's degraded path
    calls it to keep a missing shipped layer loud on a bare interpreter.
    """
    base = shipped_dir if shipped_dir is not None else SHIPPED_STANDARDS_DIR
    paths = [base / name for name in SHIPPED_REQUIRED_STANDARDS]
    for path in paths:
        if not path.is_file():
            raise StandardsConfigError(
                f"shipped standards file missing: {path}. The skills-kit install is "
                "incomplete; reinstall or update the plugin. Every SKILL.md and "
                "CLAUDE.md audit needs this layer, so it is never skipped."
            )
    return paths


def layer_paths(
    project_root: Path | None,
    *,
    shipped_dir: Path | None = None,
    user_dir: Path | None = None,
) -> tuple[list[Path], list[Path]]:
    """The paths resolve() reads, lowest layer first. Pure: touches no disk.

    Returns (config_files, standards_dirs). config_files are the config.yaml /
    config.local.yaml candidates, merged later-wins; standards_dirs are the
    directories scanned for *-standards.md. Either may name a path that does
    not exist. `user_dir` replaces the harness config dir (_config_dir()) for
    the user layer; lane_models passes `<home>/.claude` through it.
    """
    config_files, labelled = _layers(project_root, shipped_dir=shipped_dir, user_dir=user_dir)
    return config_files, [d for _label, d in labelled]


def _layers(
    project_root: Path | None,
    *,
    shipped_dir: Path | None = None,
    user_dir: Path | None = None,
) -> tuple[list[Path], list[tuple[str, Path]]]:
    """layer_paths with each standards dir labelled by its layer name."""
    user_layer = (user_dir if user_dir is not None else _config_dir()) / "skills-kit"
    proj_layer = (project_root / ".claude" / "skills-kit") if project_root is not None else None

    config_files: list[Path] = []
    standards_dirs: list[tuple[str, Path]] = []
    if shipped_dir is not None:
        config_files.append(shipped_dir / "config.yaml")
        standards_dirs.append(("shipped", shipped_dir))
    config_files.append(user_layer / "config.yaml")
    config_files.append(user_layer / "config.local.yaml")
    standards_dirs.append(("user", user_layer))
    if proj_layer is not None:
        config_files.append(proj_layer / "config.yaml")
        config_files.append(proj_layer / "config.local.yaml")
        standards_dirs.append(("project", proj_layer))
    return config_files, standards_dirs


def existing_layer_files(
    project_root: Path | None, *, shipped_dir: Path | None = None
) -> list[Path]:
    """The config and *-standards.md files on disk that resolve() would read.

    Reads no file content, so it works without pyyaml. A non-empty result
    means a caller that cannot resolve is ignoring configured values.
    """
    config_files, standards_dirs = layer_paths(project_root, shipped_dir=shipped_dir)
    found = [p for p in config_files if p.is_file()]
    for d in standards_dirs:
        if d.is_dir():
            found.extend(sorted(d.glob("*-standards.md")))
    return found


def _require_yaml() -> None:
    if not HAVE_YAML:
        raise StandardsUnavailableError(
            "pyyaml is not importable by this interpreter "
            f"({sys.executable}), so no skills-kit config or standards file "
            "can be read. Run under the skills-kit plugin venv "
            "(~/.claude/plugins/data/<marketplace>/skills-kit/.venv/, "
            "Scripts/python.exe on Windows, bin/python elsewhere), which "
            "bootstrap provisions with pyyaml."
        )


def _resolve_shipped_dir(shipped_dir) -> Path | None:
    """Map the sentinel to SHIPPED_STANDARDS_DIR and check the dir is usable."""
    if shipped_dir is _SHIPPED_DEFAULT:
        shipped_dir = SHIPPED_STANDARDS_DIR
    if shipped_dir is None:
        return None
    shipped_dir = Path(shipped_dir)
    if not shipped_dir.is_dir() or not any(shipped_dir.glob("*-standards.md")):
        raise StandardsConfigError(
            f"shipped standards directory {shipped_dir} is missing or holds no "
            "*-standards.md file. The skills-kit install is incomplete; reinstall "
            "or update the plugin."
        )
    return shipped_dir


def _collect_standards(
    labelled_dirs: list[tuple[str, Path]],
) -> tuple[dict[str, list[StandardsFile]], dict[str, int]]:
    """Parse every *-standards.md in layer order and validate them together."""
    standards_by_primitive: dict[str, list[StandardsFile]] = {}
    ordered: list[StandardsFile] = []
    for label, d in labelled_dirs:
        if not d.is_dir():
            continue
        for md_path in sorted(d.glob("*-standards.md")):
            sf = _parse_standards_file(md_path, label)
            standards_by_primitive.setdefault(sf.applies_to, []).append(sf)
            ordered.append(sf)
    return standards_by_primitive, _validate_criteria(ordered)


def resolve_shipped(*, shipped_dir=_SHIPPED_DEFAULT) -> ResolvedStandards:
    """Resolve the shipped layer alone: no user or project config, no overrides.

    What a plain `audit` (no --config) applies, so its output depends on the
    installed plugin only. Raises like resolve() on a missing pyyaml, a missing
    shipped layer, or an invalid shipped file.
    """
    _require_yaml()
    shipped = _resolve_shipped_dir(shipped_dir)
    if shipped is None:
        return ResolvedStandards()
    if shipped_dir is _SHIPPED_DEFAULT:
        require_shipped_standards(shipped)
    standards_by_primitive, threshold_defaults = _collect_standards([("shipped", shipped)])
    return ResolvedStandards(
        threshold_defaults=threshold_defaults,
        standards_by_primitive=standards_by_primitive,
    )


def resolve(project_root: Path | None, *, shipped_dir=_SHIPPED_DEFAULT) -> ResolvedStandards:
    """Resolve every standards layer into one ResolvedStandards.

    Layer order (lowest -> highest): shipped_dir (default SHIPPED_STANDARDS_DIR;
    pass None to opt out), <user_dir>/skills-kit (config.yaml then
    config.local.yaml), <project_root>/.claude/skills-kit (config.yaml then
    config.local.yaml). Config merges later-wins; standards files union across
    layers. Raises StandardsUnavailableError when pyyaml is unavailable: an
    unread config must never pass for an empty one. A missing shipped layer
    raises StandardsConfigError.
    """
    notes: list[str] = []
    _require_yaml()
    shipped = _resolve_shipped_dir(shipped_dir)
    if shipped is not None and shipped_dir is _SHIPPED_DEFAULT:
        require_shipped_standards(shipped)

    config_files, labelled_dirs = _layers(project_root, shipped_dir=shipped)

    merged: dict = {}
    for cf in config_files:
        merged = _deep_merge(merged, _load_config_file(cf))

    # -- standards files (dirs only; config.local.yaml carries no md) ---------
    # Collected BEFORE the rules: block is validated -- an authored criterion
    # id is a valid `rules: {<id>: off}` knob, so the rule-id validation below
    # needs the full criterion-id set up front.
    standards_by_primitive, threshold_defaults = _collect_standards(labelled_dirs)

    authored_criteria: set[str] = {
        c["id"]
        for files in standards_by_primitive.values()
        for sf in files
        for c in sf.criteria
    }

    disabled_rules, thresholds = _validate_and_extract(
        merged, authored_criteria, set(threshold_defaults)
    )
    adapters = _validate_adapters(merged)
    audit_settings = _validate_audit(merged)

    return ResolvedStandards(
        disabled_rules=disabled_rules,
        thresholds=thresholds,
        threshold_defaults=threshold_defaults,
        standards_by_primitive=standards_by_primitive,
        adapters=adapters,
        audit=audit_settings,
        notes=notes,
    )
