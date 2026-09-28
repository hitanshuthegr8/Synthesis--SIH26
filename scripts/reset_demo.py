"""Reset the demo by deleting the database and re-seeding."""
import sys
from pathlib import Path

# Add the scripts directory to sys.path to import seed_database
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The database is located at synthesis/backend/data/synthesis.db
db_path = Path(__file__).resolve().parents[1] / "backend" / "data" / "synthesis.db"

def main():
    if db_path.exists():
        db_path.unlink()
        print(f"Deleted database at {db_path}")
    else:
        print(f"No existing database found at {db_path}")

    # Call seed_database.py logic
    import seed_database
    seed_database.main()

if __name__ == "__main__":
    main()
