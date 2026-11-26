"""Create a consistent, private SQLite snapshot and verify integrity."""
import argparse, os, sqlite3
from pathlib import Path
from .store import db_path

def backup(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_file():raise ValueError("Source database missing")
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation avoids overwriting any prior backup.
    fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)
    try:
        src=sqlite3.connect(source.as_uri()+"?mode=ro",uri=True,timeout=10)
        try:
            dst=sqlite3.connect(destination)
            try:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("Backup integrity check failed")
            finally:dst.close()
        finally:src.close()
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("destination",type=Path)
    a=p.parse_args()
    backup(db_path().resolve(),a.destination.resolve())
    print("Verified private database snapshot created.")
if __name__=="__main__":main()
