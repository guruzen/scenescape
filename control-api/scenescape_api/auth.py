import json, os, time
from dataclasses import dataclass
from pathlib import Path
from fastapi import Header, HTTPException
import jwt
from jwt import PyJWKClient
@dataclass(frozen=True)
class Principal:
    subject:str; display_name:str; roles:frozenset[str]; scene_scopes:frozenset[str]; expires_at:int
    @property
    def is_admin(self): return "scenescape-admin" in self.roles
def _key(): return os.getenv("API_SIGNING_KEY","development-only-key-change-me-123456")
def issue_token(username:str):
    now=int(time.time()); return jwt.encode({"sub":username,"name":username,"roles":["scenescape-admin"],"scenes":["*"],"iat":now,"exp":now+3600,"aud":"scenescape-api","typ":"service"},_key(),algorithm="HS256")
def verify_service(username:str,password:str)->bool:
    for item in filter(None,os.getenv("SERVICE_AUTH_FILES","").replace(",",os.pathsep).split(os.pathsep)):
        try:
            data=json.loads(Path(item).read_text())
            if data.get("user")==username and data.get("password")==password:return True
        except Exception: continue
    return False
def _principal(data):
    roles=set(data.get("roles") or [])
    realm=data.get("realm_access") or {}; roles.update(realm.get("roles") or [])
    for client in (data.get("resource_access") or {}).values(): roles.update(client.get("roles") or [])
    scenes=data.get("scenes") or data.get("scene_scopes") or []
    return Principal(str(data.get("sub")),str(data.get("name") or data.get("preferred_username") or data.get("sub")),frozenset(roles),frozenset(map(str,scenes)),int(data.get("exp",0)))
def current_principal(authorization:str|None=Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Bearer token required")
    token=authorization.split(" ",1)[1]
    try:
        header=jwt.get_unverified_header(token); alg=header.get("alg")
        if alg=="HS256": data=jwt.decode(token,_key(),algorithms=["HS256"],audience=os.getenv("OIDC_AUDIENCE","scenescape-api"))
        else:
            jwks=os.getenv("OIDC_JWKS_URL"); issuer=os.getenv("OIDC_ISSUER"); audience=os.getenv("OIDC_AUDIENCE","scenescape-api")
            if not jwks or not issuer: raise RuntimeError("OIDC_JWKS_URL and OIDC_ISSUER are required")
            signing_key=PyJWKClient(jwks).get_signing_key_from_jwt(token).key
            data=jwt.decode(token,signing_key,algorithms=[alg or "RS256"],audience=audience,issuer=issuer)
    except Exception as exc: raise HTTPException(401,f"Invalid token: {exc}") from exc
    return _principal(data)
