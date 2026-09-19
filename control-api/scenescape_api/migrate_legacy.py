"""Import a bounded legacy JSON snapshot into native resource tables without deleting existing rows."""
import json, sys
from .auth import Principal
from .database import Base, get_engine, sessions
from .resources import upsert

KINDS={"scenes":"scene","cameras":"camera","sensors":"sensor","regions":"region","tripwires":"tripwire","assets":"asset","children":"child","markers":"marker"}

def migrate(data):
    if not isinstance(data,dict): raise ValueError("snapshot must be a JSON object")
    actor=Principal("migration","Migration",frozenset({"scenescape-admin"}),frozenset({"*"}),2**31)
    Base.metadata.create_all(get_engine())
    db=sessions()()
    try:
        for plural,kind in KINDS.items():
            rows=data.get(plural,[])
            if not isinstance(rows,list): raise ValueError(f"{plural} must be an array")
            for item in rows:
                if not isinstance(item,dict): raise ValueError(f"invalid {plural} row")
                uid=item.get("uid") or item.get("id") or item.get("uuid")
                upsert(db,kind,str(uid) if uid is not None else None,item,actor)
        db.commit()
    except Exception:
        db.rollback(); raise
    finally: db.close()

def main():
    raw=sys.stdin.buffer.read()
    if len(raw)>64*1024*1024: raise SystemExit("snapshot exceeds 64 MiB limit")
    migrate(json.loads(raw or b"{}"))
if __name__=="__main__": main()
