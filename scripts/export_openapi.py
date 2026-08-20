from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from app.config import Settings
from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the canonical StackGraph OpenAPI document")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    settings = Settings(
        environment="test",
        default_tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        contracts_dir=Path("/contracts/v1"),
    )
    document = create_app(settings=settings).openapi()
    document["servers"] = [{"url": "/api/v1"}]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
