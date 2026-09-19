import csv, io, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import Depends, FastAPI, Form, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import func, select
from .auth import Principal, current_principal, issue_token, verify_service
from .database import Base, Event, Heartbeat, Incident, Observation, get_engine, sessions
from .resources import ALIASES, get_resource, list_resources, to_dict, upsert

app=FastAPI(title="SceneScape Native Control API", version="0.1")
Base.metadata.create_all(get_engine())

def db_dep():
    db=sessions()()
    try: yield db
    finally: db.close()

def _kind(plural):
    if plural not in ALIASES: raise HTTPException(404,"Unknown resource type")
    return ALIASES[plural]

def _scene_allowed(p: Principal, scene_id: str):
    if p.is_admin or "*" in p.scene_scopes or scene_id in p.scene_scopes: return
    raise HTTPException(403,"Scene is outside token scope")

@app.post("/api/v1/auth")
def service_auth(username: str = Form(...), password: str = Form(...)):
    if not verify_service(username,password): raise HTTPException(401,"Invalid service credentials")
    return {"token": issue_token(username)}

@app.get("/api/v2/overview")
def overview(p=Depends(current_principal), db=Depends(db_dep)):
    counts={}
    for plural,kind in ALIASES.items(): counts[plural]=db.scalar(select(func.count()).select_from(__import__('scenescape_api.database',fromlist=['Resource']).Resource).where(__import__('scenescape_api.database',fromlist=['Resource']).Resource.kind==kind))
    hb=db.get(Heartbeat,"mqtt")
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"counts":counts,"health":{"database":"connected","mqtt":hb.state if hb else "unknown"}}

@app.get("/api/v2/{plural}")
def list_any(plural: str, p=Depends(current_principal), db=Depends(db_dep)):
    if plural == "incidents":
        rows=db.scalars(select(Incident).order_by(Incident.id.desc())).all()
        return [{"id":r.id,"scene_id":r.scene_id,"title":r.title,"status":r.status,"assignee":r.assignee,"notes":r.notes,"audit":r.audit} for r in rows]
    return list_resources(db,_kind(plural))

@app.post("/api/v2/{plural}")
def create_any(plural: str, body: dict, p=Depends(current_principal), db=Depends(db_dep)):
    row=upsert(db,_kind(plural),None,body,p); db.commit(); return to_dict(row)

@app.put("/api/v2/{plural}/{uid}")
def update_any(plural: str, uid: str, body: dict, revision: int|None=Query(default=None), p=Depends(current_principal), db=Depends(db_dep)):
    row=upsert(db,_kind(plural),uid,body,p,revision); db.commit(); return to_dict(row)

@app.get("/api/v2/scenes/{scene_id}/live")
def live(scene_id: str,p=Depends(current_principal),db=Depends(db_dep)):
    _scene_allowed(p,scene_id)
    row=db.scalar(select(Observation).where(Observation.scene_id==scene_id).order_by(Observation.observed_at.desc()))
    return row.payload if row else {"id":scene_id,"objects":[],"stale":True}

@app.get("/api/v2/scenes/{scene_id}/history")
def history(scene_id: str,limit:int=Query(200,ge=1,le=5000),p=Depends(current_principal),db=Depends(db_dep)):
    _scene_allowed(p,scene_id)
    rows=db.scalars(select(Observation).where(Observation.scene_id==scene_id).order_by(Observation.observed_at.desc()).limit(limit)).all()
    return [{"id":r.id,"timestamp":r.observed_at.isoformat(),"payload":r.payload} for r in reversed(rows)]

@app.get("/api/v2/scenes/{scene_id}/trends")
def trends(scene_id: str,p=Depends(current_principal),db=Depends(db_dep)):
    _scene_allowed(p,scene_id)
    since=datetime.now(timezone.utc)-timedelta(hours=24)
    rows=db.scalars(select(Observation).where(Observation.scene_id==scene_id,Observation.observed_at>=since)).all()
    buckets={}
    for r in rows:
        key=r.observed_at.replace(minute=0,second=0,microsecond=0).isoformat()
        buckets.setdefault(key,[]).append(len((r.payload or {}).get("objects") or []))
    return [{"bucket":k,"samples":len(v),"average_objects":round(sum(v)/len(v),2)} for k,v in sorted(buckets.items())]

@app.get("/api/v2/incidents")
def incidents(p=Depends(current_principal),db=Depends(db_dep)):
    rows=db.scalars(select(Incident).order_by(Incident.id.desc())).all()
    return [{"id":r.id,"scene_id":r.scene_id,"title":r.title,"status":r.status,"assignee":r.assignee,"notes":r.notes,"audit":r.audit} for r in rows]

@app.post("/api/v2/incidents/{incident_id}/action")
def incident_action(incident_id:int, body:dict,p=Depends(current_principal),db=Depends(db_dep)):
    r=db.get(Incident,incident_id)
    if not r: raise HTTPException(404,"Incident not found")
    status=str(body.get("status") or r.status)
    if status not in {"new","acknowledged","investigating","resolved","reopened"}: raise HTTPException(422,"Invalid incident status")
    note=str(body.get("note") or "").strip(); now=datetime.now(timezone.utc).isoformat()
    notes=list(r.notes or []); audit=list(r.audit or [])
    if note: notes.append({"at":now,"by":p.subject,"note":note})
    audit.append({"at":now,"by":p.subject,"status":status})
    r.status=status; r.notes=notes; r.audit=audit; r.updated_at=datetime.now(timezone.utc); db.commit()
    return {"id":r.id,"status":r.status,"notes":r.notes,"audit":r.audit,"title":r.title}

@app.get("/media/{path:path}")
def media(path:str,p=Depends(current_principal)):
    root=Path(os.getenv("MEDIA_ROOT","./media")).resolve(); target=(root/path).resolve()
    if root not in target.parents and target != root: raise HTTPException(404)
    if not target.is_file(): raise HTTPException(404)
    return FileResponse(target)

@app.get("/api/v1/health")
def api_health(db=Depends(db_dep)):
    db.execute(select(1))
    return {"status":"ok","database":"connected"}

@app.get("/healthz", response_class=PlainTextResponse)
def healthz(): return "ok"
