import asyncio
from pathlib import Path

from app.config import Settings
from tests.contract_support import ContractValidator, load_json
from tests.test_api import app_with_stubs, request


CONTRACTS = Settings(environment="test").contracts_dir


def test_generated_openapi_preserves_frozen_operations() -> None:
    app, _ = app_with_stubs()
    generated = app.openapi()
    frozen = load_json(Path(CONTRACTS) / "openapi.json")

    assert set(frozen["paths"]) <= set(generated["paths"])
    for path, frozen_path in frozen["paths"].items():
        for method, frozen_operation in frozen_path.items():
            operation = generated["paths"][path][method]
            assert operation["operationId"] == frozen_operation["operationId"]
            frozen_inline_parameters = {
                (parameter["name"], parameter["in"])
                for parameter in frozen_operation.get("parameters", [])
                if "$ref" not in parameter
            }
            generated_parameters = {
                (parameter["name"], parameter["in"])
                for parameter in operation.get("parameters", [])
            }
            assert frozen_inline_parameters <= generated_parameters


def test_http_response_conforms_to_frozen_estate_schema() -> None:
    app, _ = app_with_stubs()
    response = asyncio.run(request(app, "GET", "/api/v1/estate/summary"))

    assert response.status_code == 200
    ContractValidator(Path(CONTRACTS)).validate_read_model("estateSummary", response.json())


def test_capability_and_modernization_fixtures_conform_to_frozen_schemas() -> None:
    fixtures = Path(CONTRACTS) / "fixtures"
    validator = ContractValidator(Path(CONTRACTS))
    validator.validate_read_model(
        "capabilityTaxonomy", load_json(fixtures / "capability-taxonomy.json"),
    )
    validator.validate_read_model(
        "repositoryCapabilityIntelligence", load_json(fixtures / "repository-capabilities.json"),
    )
    validator.validate_read_model(
        "repositoryModernizationIntelligence",
        load_json(fixtures / "repository-modernization-intelligence.json"),
    )
    validator.validate_read_model(
        "phase3IntelligenceMetrics",
        load_json(fixtures / "phase3-intelligence-metrics.json"),
    )
    validator.validate_read_model(
        "repositoryActivity", load_json(fixtures / "repository-activity.json"),
    )
