from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline import fetch_all_sources  # noqa: E402


def main() -> int:
    report = fetch_all_sources(limit_per_source=15)
    print(f"Fetched at (UTC): {report.fetched_at.isoformat()}")
    print(f"Total raw items: {len(report.items)}")
    print()

    successful_types: set[str] = set()
    for source in report.sources:
        if source.success:
            successful_types.add(source.source_type)
            print(
                f"[OK]   {source.display_name:<28} "
                f"{source.item_count:>2} items  {source.elapsed_ms:>6} ms  {source.source_type}"
            )
        else:
            print(f"[FAIL] {source.display_name:<28} 0 items  {source.error}")

    print()
    print(f"Successful source types: {len(successful_types)}")
    if len(successful_types) < 3:
        print("Verification failed: fewer than 3 public source types returned real data.")
        return 1
    print("Verification passed: at least 3 public source types returned real data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

