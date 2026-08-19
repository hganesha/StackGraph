from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


class ContractValidator:
    def __init__(self, contract_dir: Path) -> None:
        schema_files = sorted((contract_dir / "schemas").glob("*.json"))
        self.schemas = [load_json(path) for path in schema_files]
        self.store = {schema["$id"]: schema for schema in self.schemas}
        self.registry = Registry()
        for schema_id, schema in self.store.items():
            self.registry = self.registry.with_resource(
                schema_id, Resource.from_contents(schema),
            )
        self.read_models = self.store[
            "https://stackgraph.dev/contracts/v1/schemas/read-models.schema.json"
        ]

    def validate_read_model(self, definition: str, instance: Any) -> None:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": (
                "https://stackgraph.dev/contracts/v1/schemas/"
                f"read-models.schema.json#/$defs/{definition}"
            ),
        }
        Draft202012Validator(schema, registry=self.registry).validate(instance)
