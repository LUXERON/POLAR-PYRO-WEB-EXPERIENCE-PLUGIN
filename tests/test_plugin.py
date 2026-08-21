from qwen_harness.plugin import compile_experience


def fixture() -> dict:
    return {
        "capability": {
            "application_id": "fixture",
            "routes": [{"id": "home"}],
            "roles": [{"id": "member"}],
            "queries": [{"id": "list_items"}],
            "commands": [{"id": "save_item"}],
        },
        "binding": {"application_id": "fixture", "view_recipes": {"home": "data_table_detail_drawer"}},
        "journeys": [{
            "id": "manage_items", "task_id": "manage_items", "entry_route": "home", "recovery_route": "home",
            "role_ids": ["member"], "query_ids": ["list_items"], "command_ids": ["save_item"],
            "steps": [{"id": "save", "route_id": "home", "command_id": "save_item"}], "success_state": "saved"
        }],
        "components": [{"component_id": "data_table"}],
        "design_language": {"design_language_id": "polar.precise.v1"},
    }


def test_plugin_compiles_closed_plan_and_proof_obligations() -> None:
    receipt = compile_experience(fixture())
    assert receipt["status"] == "PASS"
    assert receipt["evidence"]
    assert receipt["output"]["ui_plan"]["application_id"] == "fixture"
    assert receipt["output"]["euclid_obligations"]


def test_unknown_input_and_off_alphabet_symbols_fail_closed() -> None:
    value = fixture()
    value["command"] = "npm run build"
    assert compile_experience(value)["error"]["code"] == "CLOSED_INPUT"
    value = fixture()
    value["journeys"][0]["command_ids"] = ["delete_everything"]
    assert compile_experience(value)["status"] == "FAIL"
