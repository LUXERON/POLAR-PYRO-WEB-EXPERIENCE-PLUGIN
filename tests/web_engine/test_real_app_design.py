from __future__ import annotations

import json
from pathlib import Path

from polar_pyro_web_experience.real_app_design import design_schema, route_catalog
from polar_pyro_web_experience.real_app_renderer import materialize_real_app


ROOT = Path(__file__).resolve().parents[2]


def test_design_schema_closes_provider_neutral_route_catalog() -> None:
    routes = route_catalog(["discover", "moderation", "unknown_route"])
    schema = design_schema("fixture", routes)
    route_schema = schema["properties"]["route_recipes"]
    assert set(route_schema["required"]) == set(routes)
    assert route_schema["additionalProperties"] is False
    assert "editorial_discovery_canvas" in route_schema["properties"]["discover"]["enum"]
    assert "kling" not in json.dumps(schema).lower()


def test_renderer_materializes_hash_bound_product_and_design(tmp_path: Path) -> None:
    manifest = {"product_id": "fixture", "name": "Fixture", "routes": [{"id": "discover"}]}
    design = {"schema_version": "1.0", "product_id": "fixture", "route_recipes": {"discover": "editorial_discovery_canvas"}}
    receipt = materialize_real_app(template=ROOT / "renderers" / "real-app-react", output=tmp_path / "app", manifest=manifest, design_ir=design)
    assert receipt.renderer == "luxeron.real-app-react.v1"
    assert (tmp_path / "app/src/generated/product.json").is_file()
    assert (tmp_path / "app/package-lock.json").is_file()
    assert receipt.files["src/generated/design-ir.json"]
