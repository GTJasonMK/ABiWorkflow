from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import engine
from app.services.schema_cleanup import cleanup_deprecated_single_track_schema

logger = logging.getLogger("schema_cleanup")


async def _run(force: bool) -> int:
    async with engine.begin() as conn:
        result = await conn.run_sync(lambda sync_conn: cleanup_deprecated_single_track_schema(sync_conn, force=force))

    logger.info(
        "single-track schema cleanup finished: dropped_table=%s dropped_column=%s skipped_by_marker=%s",
        result.get("dropped_table"),
        result.get("dropped_column"),
        result.get("skipped_by_marker"),
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup deprecated schema for panel single-track migration.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore marker and run cleanup again.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    return asyncio.run(_run(force=args.force))


if __name__ == "__main__":
    raise SystemExit(main())
