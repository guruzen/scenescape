"""Import legacy or sample SceneScape JSON into native resource tables.

The importer is intentionally additive/upsert-only: it never deletes legacy or
native rows. It accepts both the legacy export envelope and the upstream sample
scene shape where cameras/sensors/regions/tripwires are nested inside a scene.
"""
import json
import sys
from copy import deepcopy
from sqlalchemy import select

from .auth import Principal
from .database import Base, Resource, get_engine, sessions
from .resources import upsert

KINDS = {"scenes":"scene","cameras":"camera","sensors":"sensor","regions":"region","tripwires":"tripwire","assets":"asset","children":"child","markers":"marker","calibrationmarkers":"marker"}
NESTED = ("cameras","sensors","regions","tripwires","children","calibrationmarkers","markers")


def _uid(item, kind):
    if not isinstance(item, dict): return None
    if kind == "marker":
        return item.get("marker_id") or item.get("uid") or item.get("id")
    return item.get("uid") or item.get("id") or item.get("uuid") or item.get("sensor_id")


def normalize_snapshot(data):
    if isinstance(data, list): data={"scenes":data}
    if not isinstance(data, dict): raise ValueError("snapshot must be a JSON object or scene array")
    out={key:[] for key in KINDS}; seen={key:set() for key in KINDS}
    def add(plural,item,scene_uid=None):
        if plural not in KINDS or not isinstance(item,dict): return
        row=deepcopy(item)
        if scene_uid and plural=="children": row.setdefault("parent",scene_uid)
        elif scene_uid and plural not in ("scenes","assets"): row.setdefault("scene",scene_uid)
        kind=KINDS[plural]; key=str(_uid(row,kind) or json.dumps(row,sort_keys=True,default=str))
        if key in seen[plural]: return
        seen[plural].add(key); out[plural].append(row)
    def add_scene(scene,parent_uid=None):
        if not isinstance(scene,dict): return
        scene_uid=str(scene.get("uid") or scene.get("id") or scene.get("uuid") or "") or None
        base={k:deepcopy(v) for k,v in scene.items() if k not in NESTED}; add("scenes",base)
        for plural in NESTED:
            rows=scene.get(plural) or []
            if not isinstance(rows,list): raise ValueError(f"{plural} must be an array")
            for row in rows:
                if plural=="children" and isinstance(row,dict) and row.get("uid") and (row.get("cameras") is not None or row.get("sensors") is not None or row.get("regions") is not None):
                    add_scene(row,scene_uid); link=deepcopy(row.get("link") or {})
                    if link:
                        link.setdefault("parent",scene_uid); link.setdefault("child",row.get("uid")); add("children",link,scene_uid)
                    continue
                add(plural,row,scene_uid)
    if "scenes" not in data and (data.get("uid") or data.get("id") or data.get("uuid")) and data.get("name"):
        add_scene(data)
    else:
        scenes=data.get("scenes",[])
        if not isinstance(scenes,list): raise ValueError("scenes must be an array")
        for scene in scenes: add_scene(scene)
        for plural in KINDS:
            if plural=="scenes": continue
            rows=data.get(plural,[])
            if rows is None: continue
            if not isinstance(rows,list): raise ValueError(f"{plural} must be an array")
            for row in rows: add(plural,row)
    out["markers"].extend(out.pop("calibrationmarkers",[])); return out


def _marker_target_uid(db, marker_id):
    if marker_id is None: return None
    canonical=str(marker_id)
    exact=db.scalar(select(Resource).where(Resource.kind=="marker",Resource.uid==canonical))
    if exact is not None: return exact.uid
    for row in db.scalars(select(Resource).where(Resource.kind=="marker").order_by(Resource.id)).all():
        payload=row.payload or {}
        if str(payload.get("marker_id") or payload.get("uid") or "")==canonical:
            return row.uid
    return canonical


def migrate(data):
    normalized=normalize_snapshot(data); actor=Principal("migration","Migration",frozenset({"scenescape-admin"}),frozenset({"*"}),2**31)
    Base.metadata.create_all(get_engine()); db=sessions()(); counts={}
    try:
        for plural,kind in KINDS.items():
            if plural=="calibrationmarkers": continue
            rows=normalized.get(plural,[]); counts[plural]=len(rows)
            for item in rows:
                uid=_uid(item,kind); target=_marker_target_uid(db,uid) if kind=="marker" else (str(uid) if uid is not None else None)
                upsert(db,kind,target,item,actor)
        db.commit(); return counts
    except Exception:
        db.rollback(); raise
    finally: db.close()


def main():
    raw=sys.stdin.buffer.read()
    if len(raw)>64*1024*1024: raise SystemExit("snapshot exceeds 64 MiB limit")
    counts=migrate(json.loads(raw or b"{}")); print(json.dumps({"imported":counts},sort_keys=True))

if __name__=="__main__": main()
