"""The old-versus-copy differential for the three legacy suites.

Each case runs one legacy suite from ``tests/<suite>`` and the same suite's
re-pointed twin from the ignored mirror ``tmp/<suite>``, each in its own pytest
process, then compares the normalized outcomes:

* the mirrored files collect the same node ids as their legacy originals;
* every outcome agrees, failures by node id, exception type and normalized
  message, except the differences the suite's ledger declares;
* every legacy failure is a baseline failure the ledger records, so a legacy
  suite that is not green still has a trustworthy comparison.

The mirror process puts the generated ``tmp/sitecustomize.py`` on every
interpreter it starts, so a legacy library on any import root fails the run
instead of being compared. Slow (about two minutes per suite).
"""

from __future__ import annotations

import pytest

import repoint


@pytest.mark.parametrize("suite", repoint.SUITES)
def test_repointed_suite_matches_the_legacy_suite(suite, tmp_path):
    problems, legacy, mirror = repoint.compare_suite(suite, tmp_path)

    ledger = repoint.load_ledger(suite)
    assert len(legacy.outcomes) == repoint.SUITE_TOTALS[suite], (
        f"legacy {suite} collected {len(legacy.outcomes)} tests, ledger totals "
        f"{repoint.SUITE_TOTALS[suite]}")
    per_file: dict[str, int] = {}
    for node in legacy.outcomes:
        file_name = node.split("::", 1)[0].split("/", 1)[1]
        per_file[file_name] = per_file.get(file_name, 0) + 1
    recorded = {r["path"].rsplit("/", 1)[1]: r["collection_count"] for r in ledger["rows"]}
    assert per_file == recorded, "per-file collection counts drifted from the ledger"

    assert not problems, (
        f"{suite}: {len(problems)} difference(s) between the legacy run "
        f"({legacy.summary}) and the re-pointed run ({mirror.summary}):\n"
        + "\n".join(problems[:60]))
