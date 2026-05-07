"""Seed the synthetic database (idempotent).

Usage:
    python scripts/seed_db.py [--force] [--n 600] [--seed 7]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script without `pip install -e .`
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.data import generate_dataset  # noqa: E402
from src.database import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reseed even if the database already contains data.",
    )
    parser.add_argument("--n", type=int, default=None, help="Number of patients.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed.")
    args = parser.parse_args()

    settings = get_settings()
    n = args.n if args.n is not None else settings.num_patients
    seed = args.seed if args.seed is not None else settings.random_seed

    db = Database(settings.db_path)
    db.initialize_schema()
    if db.is_seeded() and not args.force:
        print(f"Database already seeded at {settings.db_path}. Use --force to overwrite.")
        return 0

    dataset = generate_dataset(num_patients=n, seed=seed)
    db.load_dataset(dataset)
    print(
        f"Seeded {n} patients into {settings.db_path} "
        f"({len(dataset.genomics)} mutation rows, "
        f"{len(dataset.transcriptomics)} expression rows)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
