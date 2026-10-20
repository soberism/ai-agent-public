"""OPEN-06原始setup明确要求有材料与无材料两种情况，补跑无材料分支。"""

import os

import pytest
from eval_seed_setup import SETUPS
from test_assistant_eval_seeded_live import CASES
from test_assistant_eval_seeded_live import test_seeded_assistant_case as replay


@pytest.mark.skipif(
    os.getenv("RUN_SEEDED_ASSISTANT_EVAL") != "1", reason="显式启用隔离回放"
)
def test_contract_without_material(cloud, monkeypatch):
    case = next(case for case in CASES if case["id"] == "OPEN-06")
    monkeypatch.setitem(
        SETUPS, "OPEN-06", {"objects": [], "fixture_notes": [], "requires": []}
    )
    replay(cloud, monkeypatch, {**case, "variant": "without_material"})
