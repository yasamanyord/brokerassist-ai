"""Offline administration of named pilot credentials; never commit the roster."""
import argparse, getpass, json, os, tempfile
from pathlib import Path
from .pilot import user_record

def write_user(path,record):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    rows=json.loads(path.read_text()) if path.exists() else []
    rows=[r for r in rows if r["username"]!=record["username"]]+[record]
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:json.dump(rows,f,indent=2);f.write("\n")
        os.chmod(tmp,0o600);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file",required=True,type=Path);p.add_argument("--username",required=True);p.add_argument("--role",required=True,choices=["admin","operator","viewer"])
    a=p.parse_args()
    first=getpass.getpass("Strong password (20+ characters): ");second=getpass.getpass("Repeat password: ")
    if first!=second:p.error("Passwords do not match")
    write_user(a.file,user_record(a.username,a.role,first))
    print("Credential hash saved. Restart pilot to load new roster.")
if __name__=="__main__":main()
