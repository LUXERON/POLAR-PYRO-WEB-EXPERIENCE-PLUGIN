from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from qwen_harness.web_renderer import RendererError, materialize_react_vite, solve_ui_plan
from qwen_harness.web_ux_compiler import compile_ux_contract


ROOT=Path(__file__).resolve().parents[2]
CATALOG=json.loads((ROOT/"catalog/web_experience/catalog.lock.json").read_text(encoding="utf-8"))
DESIGN=json.loads((ROOT/"catalog/web_experience/design-languages.json").read_text(encoding="utf-8"))["design_languages"][0]
CAP={"application_id":"reference.app","routes":[{"id":"dashboard"}],"roles":[{"id":"operator"}],"queries":[{"id":"list_items"}],"commands":[{"id":"create_item"}]}
BIND={"application_id":"reference.app","view_recipes":{"dashboard":"data_table_detail_drawer"}}
JOURNEY=[{"id":"manage_items_journey","task_id":"manage_items","role_ids":["operator"],"entry_route":"dashboard","recovery_route":"dashboard","success_state":"item_created","query_ids":["list_items"],"command_ids":["create_item"],"steps":[{"id":"inspect","route_id":"dashboard","state":"ready"},{"id":"submit","route_id":"dashboard","state":"submitting","command_id":"create_item"}]}]


def _plan():
    ux=compile_ux_contract(CAP,BIND,JOURNEY)
    return solve_ui_plan(CAP,ux,BIND,CATALOG["components"],DESIGN)


def test_same_input_materializes_byte_equivalent_react_vite_projects(tmp_path: Path)->None:
    plan=_plan()
    first=materialize_react_vite(plan,CAP,DESIGN,tmp_path/"first")
    second=materialize_react_vite(plan,CAP,DESIGN,tmp_path/"second")
    assert first.output_sha256==second.output_sha256
    assert first.file_hashes==second.file_hashes
    assert (tmp_path/"first/src/generated/ui-plan.json").is_file()
    assert "src/main.tsx#Region" in first.plan_to_source.values()


def test_unknown_recipe_and_action_poison_are_rejected(tmp_path: Path)->None:
    ux=compile_ux_contract(CAP,BIND,JOURNEY)
    poisoned=dict(BIND,view_recipes={"dashboard":"model_authored_jsx"})
    with pytest.raises(RendererError,match="unknown recipe"):
        solve_ui_plan(CAP,ux,poisoned,CATALOG["components"],DESIGN)
    plan=_plan()
    plan["routes"][0]["regions"][0]["command_ids"]=["delete_everything"]
    with pytest.raises(RendererError,match="unknown command"):
        materialize_react_vite(plan,CAP,DESIGN,tmp_path/"poison")


def test_template_is_data_driven_and_contains_accessibility_states(tmp_path: Path)->None:
    receipt=materialize_react_vite(_plan(),CAP,DESIGN,tmp_path/"app")
    source=(tmp_path/"app/src/main.tsx").read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in source
    assert "eval(" not in source
    assert "aria-current" in source and "Content state demonstrations" in source
    assert set(json.loads((tmp_path/"app/src/generated/ui-plan.json").read_text())["routes"][0])=={"route_id","recipe_id","regions"}
    assert asdict(receipt)["renderer"].endswith("v1")
