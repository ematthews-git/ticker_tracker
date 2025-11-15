import sqlite3
import sys
import argparse
import shutil
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH


def create_backup(target_path: Path) -> Path:
    """Creates a timestamped backup of the target database.
    
    Args:
        target_path: Path to the database file to backup
        
    Returns:
        Path to the backup file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target_path.parent / f"{target_path.stem}_backup_{timestamp}{target_path.suffix}"
    shutil.copy2(target_path, backup_path)
    return backup_path


def merge_databases(source_db_path: str, target_db_path: str = None, create_backup_file: bool = True):
    """Merges data from source database into target database.
    
    Args:
        source_db_path (str): Path to the source SQLite database file
        target_db_path (str, optional): Path to the target database. 
                                       Defaults to DB_PATH from config, or 'data.db' in project root
        create_backup_file (bool): Whether to create a backup of the target database before merging.
                                  Defaults to True (recommended)
    """
    # Validate source database exists
    source_path = Path(source_db_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source database not found: {source_db_path}")
    
    # Determine target database path
    if target_db_path is None:
        if DB_PATH:
            target_path = Path(DB_PATH)
        else:
            # Default to data.db in project root
            target_path = Path(__file__).parent.parent.parent / "data.db"
    else:
        target_path = Path(target_db_path)
    
    # Validate target database exists
    if not target_path.exists():
        raise FileNotFoundError(f"Target database not found: {target_path}. Please ensure the database exists before merging.")
    
    # Create backup if requested
    backup_path = None
    if create_backup_file:
        print(f"Creating backup of target database...")
        backup_path = create_backup(target_path)
        print(f"Backup created: {backup_path}")
        print("-" * 50)
    
    print(f"Source database: {source_path}")
    print(f"Target database: {target_path}")
    if backup_path:
        print(f"Backup location: {backup_path}")
    print("-" * 50)
    
    # Connect to both databases
    source_conn = sqlite3.connect(str(source_path))
    target_conn = sqlite3.connect(str(target_path))
    
    source_cursor = source_conn.cursor()
    target_cursor = target_conn.cursor()
    
    try:
        # Merge mentions table
        print("Merging mentions table...")
        source_cursor.execute("SELECT COUNT(*) FROM mentions")
        source_count = source_cursor.fetchone()[0]
        print(f"  Found {source_count} rows in source mentions table")
        
        source_cursor.execute("SELECT ticker, subreddit, timestamp, mention_count FROM mentions")
        mentions_inserted = 0
        mentions_skipped = 0
        
        for row in source_cursor.fetchall():
            try:
                target_cursor.execute("""
                    INSERT OR IGNORE INTO mentions (ticker, subreddit, timestamp, mention_count)
                    VALUES (?, ?, ?, ?)
                """, row)
                if target_cursor.rowcount > 0:
                    mentions_inserted += 1
                else:
                    mentions_skipped += 1
            except sqlite3.Error as e:
                print(f"  Error inserting mention row: {e}")
                continue
        
        target_conn.commit()
        print(f"  Inserted {mentions_inserted} new mentions")
        print(f"  Skipped {mentions_skipped} duplicate mentions")
        
        # Merge posts table
        print("\nMerging posts table...")
        source_cursor.execute("SELECT COUNT(*) FROM posts")
        source_count = source_cursor.fetchone()[0]
        print(f"  Found {source_count} rows in source posts table")
        
        source_cursor.execute("SELECT post_id, subreddit, created_utc, text, type FROM posts")
        posts_inserted = 0
        posts_skipped = 0
        
        for row in source_cursor.fetchall():
            try:
                target_cursor.execute("""
                    INSERT OR IGNORE INTO posts (post_id, subreddit, created_utc, text, type)
                    VALUES (?, ?, ?, ?, ?)
                """, row)
                if target_cursor.rowcount > 0:
                    posts_inserted += 1
                else:
                    posts_skipped += 1
            except sqlite3.Error as e:
                print(f"  Error inserting post row: {e}")
                continue
        
        target_conn.commit()
        print(f"  Inserted {posts_inserted} new posts")
        print(f"  Skipped {posts_skipped} duplicate posts")
        
        print("\n" + "=" * 50)
        print("Merge completed successfully!")
        print(f"Total: {mentions_inserted + posts_inserted} new rows added")
        print(f"Total: {mentions_skipped + posts_skipped} duplicate rows skipped")
        
    except sqlite3.Error as e:
        print(f"\nDatabase error: {e}")
        target_conn.rollback()
        if backup_path:
            print(f"\n⚠️  ERROR: Merge failed! Your original database is safe.")
            print(f"To restore, copy the backup back:")
            print(f"  cp {backup_path} {target_path}")
        raise
    finally:
        source_conn.close()
        target_conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Merge data from a source SQLite database into the local database"
    )
    parser.add_argument(
        "source_db",
        help="Path to the source SQLite database file to merge from"
    )
    parser.add_argument(
        "--target-db",
        help="Path to the target database (defaults to DB_PATH from config or data.db in project root)",
        default=None
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a backup of the target database before merging (not recommended)"
    )
    
    args = parser.parse_args()
    
    try:
        merge_databases(args.source_db, args.target_db, create_backup_file=not args.no_backup)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

