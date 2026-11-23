"""Print the API's OpenAPI spec as stable JSON (no server, no database needed).

The frontend's typed client is generated from this (`npm run gen:api` in
frontend/), and CI fails if the committed copy is out of date.
"""

from __future__ import annotations

import json
import sys

from app.main import app


def main() -> None:
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
