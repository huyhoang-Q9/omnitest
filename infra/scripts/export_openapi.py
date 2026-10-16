"""Xuất OpenAPI của API ra packages/contracts/openapi.json (không cần DB hay secret thật)."""

import base64
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMNITEST_MASTER_KEY", base64.urlsafe_b64encode(b"0" * 32).decode())
os.environ["OMNITEST_ENV"] = "development"

from omnitest_api.main import create_app

out = Path(__file__).resolve().parents[2] / "packages" / "contracts" / "openapi.json"
out.write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n")
print(f"Đã ghi {out}", file=sys.stderr)
