import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'

type Row = Record<string, any>
const idOf=(row:Row)=>String(row.uid??row.id??'')
const nameOf=(row:Row)=>String(row.name??row.uid??'Scene')
const identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
const defaultDraft:Row={child_type:'local',parent:'',child:'',remote_child_id:'',child_name:'',host_name:'',mqtt_username:'',mqtt_password:'',retrack:true,transform_type:'euler',transform:{translation:[0,0,0],rotation:[0,0,0],scale:[1,1,1]}}

const vector=(value:any,len:number,fallback:number[])=>Array.isArray(value)&&value.length===len?value.map(Number):fallback
const transformOf=(row:Row)=>row.transform&&typeof row.transform==='object'?row.transform:{translation:[0,0,0],rotation:[0,0,0],scale:[1,1,1]}

const editDraft=(row:Row)=> {
  const t=transformOf(row)
  const matrix=Array.from({length:16},(_,index)=>Number(row[`transform${index+1}`]??identity[index]))
  const quaternion=row.transform_type==='quaternion'
    ? [4,5,6,7].map((index)=>Number(row[`transform${index}`]??(index===7?1:0)))
    : [0,0,0,1]
  return {...defaultDraft,...row,matrix,quaternion,transform:{
    translation:vector(t.translation,3,[0,0,0]),
    rotation:vector(t.rotation,3,[0,0,0]),
    scale:vector(t.scale,3,[1,1,1]),
  }}
}

export default function HierarchyEditor({scenes,isAdmin,initialParent=''}:{scenes:Row[];isAdmin:boolean;initialParent?:string}){
  const [rows,setRows]=useState<Row[]>([])
  const [selected,setSelected]=useState<Row|null>(null)
  const [draft,setDraft]=useState<Row>({...defaultDraft,parent:initialParent})
  const [message,setMessage]=useState('')
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  const load=()=>void apiFetch<Row[]>('/api/v2/children').then(setRows).catch((e)=>setError(String(e)))
  useEffect(load,[])
  const parentScene=scenes.find((scene)=>idOf(scene)===String(draft.parent||''))
  const linkedLocalChildren=new Set(rows.filter((row)=>row.child_type!=='remote'&&(!selected||idOf(row)!==idOf(selected))).map((row)=>String(row.child||'')))
  const localOptions=scenes.filter((scene)=>idOf(scene)!==String(draft.parent||'')&&!linkedLocalChildren.has(idOf(scene)))
  const open=(row:Row|null,parent=initialParent)=>{
    setSelected(row)
    if(row)setDraft({...editDraft(row),mqtt_password:''})
    else setDraft({...defaultDraft,parent,matrix:[...identity],quaternion:[0,0,0,1]})
    setMessage('');setError('')
  }
  const field=(key:string,value:any)=>setDraft((old)=>({...old,[key]:value}))
  const tfield=(key:'translation'|'rotation'|'scale',index:number,value:number)=>setDraft((old)=>{
    const t=transformOf(old),next=vector(t[key],3,key==='scale'?[1,1,1]:[0,0,0]);next[index]=value
    return {...old,transform:{...t,[key]:next}}
  })
  const payload=()=>{
    const body:Row={
      child_type:String(draft.child_type||'local'),
      parent:String(draft.parent||''),
      retrack:Boolean(draft.retrack),
      transform_type:String(draft.transform_type||'euler'),
    }
    if(body.child_type==='local')body.child=String(draft.child||'')
    else{
      body.remote_child_id=String(draft.remote_child_id||'')
      body.child_name=String(draft.child_name||'')
      body.host_name=String(draft.host_name||'')
      body.mqtt_username=String(draft.mqtt_username||'')
      body.mqtt_password=String(draft.mqtt_password||'')
    }
    if(body.transform_type==='matrix'){
      const values=Array.isArray(draft.matrix)&&draft.matrix.length===16?draft.matrix.map(Number):identity
      values.forEach((value,index)=>body[`transform${index+1}`]=value)
    }else{
      body.transform={
        translation:vector(draft.transform?.translation,3,[0,0,0]),
        rotation:body.transform_type==='quaternion'?vector(draft.quaternion,4,[0,0,0,1]):vector(draft.transform?.rotation,3,[0,0,0]),
        scale:vector(draft.transform?.scale,3,[1,1,1]),
      }
    }
    return body
  }
  const save=async()=>{
    if(!isAdmin)return
    setBusy(true);setError('');setMessage('')
    try{
      let saved:Row
      if(selected)saved=await apiFetch<Row>(`/api/v2/children/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`,{method:'PUT',body:JSON.stringify(payload())})
      else saved=await apiFetch<Row>('/api/v2/children',{method:'POST',body:JSON.stringify(payload())})
      setSelected(saved);setDraft(editDraft(saved));setMessage('Scene hierarchy link saved.');load()
    }catch(e){setError(String(e))}finally{setBusy(false)}
  }
  const remove=async()=>{
    if(!selected||!isAdmin||!window.confirm(`Delete hierarchy link to ${nameOf(selected)}?`))return
    setBusy(true)
    try{await apiFetch(`/api/v2/children/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`,{method:'DELETE'});open(null,String(draft.parent||initialParent));load()}
    catch(e){setError(String(e))}finally{setBusy(false)}
  }
  const filtered=useMemo(()=>initialParent?rows.filter((row)=>String(row.parent||'')===initialParent):rows,[rows,initialParent])

  return <div className="hierarchy-layout">
    <section className="panel hierarchy-list">
      <div className="panel-title"><div><h2>Scene hierarchy</h2><p>Local and remote child scene links</p></div>{isAdmin&&<button className="btn btn-primary" onClick={()=>open(null,initialParent)}>New link</button>}</div>
      <div className="hierarchy-tree">{filtered.map((row)=><button key={idOf(row)} className={selected&&idOf(selected)===idOf(row)?'hierarchy-row active':'hierarchy-row'} onClick={()=>open(row)}>
        <span className="hierarchy-kind">{row.child_type==='remote'?'REMOTE':'LOCAL'}</span>
        <span><b>{nameOf(row)}</b><small>{row.parent} → {row.child_type==='remote'?row.remote_child_id:row.child}</small></span>
        <span><small>{row.retrack?'Retrack':'Keep child IDs'}</small></span>
      </button>)}{!filtered.length&&<div className="table-empty">No child scene links configured.</div>}</div>
    </section>
    <section className="panel hierarchy-editor">
      <div className="panel-title"><div><h2>{selected?`Edit ${nameOf(selected)}`:'Create child link'}</h2><p>Cycle prevention and unique-parent rules are enforced by FastAPI.</p></div></div>
      {message&&<div className="notice-box hierarchy-message">{message}</div>}{error&&<div className="error-box hierarchy-message">{error}</div>}
      <div className="scene-form-grid">
        <label>Type<select value={String(draft.child_type||'local')} onChange={(e)=>field('child_type',e.target.value)}><option value="local">Local</option><option value="remote">Remote</option></select></label>
        <label>Parent scene<select value={String(draft.parent||'')} disabled={Boolean(initialParent)} onChange={(e)=>field('parent',e.target.value)}><option value="">Select parent</option>{scenes.map((scene)=><option key={idOf(scene)} value={idOf(scene)}>{nameOf(scene)}</option>)}</select></label>
        {draft.child_type==='local'?<label className="wide">Child scene<select value={String(draft.child||'')} onChange={(e)=>field('child',e.target.value)}><option value="">Select child</option>{localOptions.map((scene)=><option key={idOf(scene)} value={idOf(scene)}>{nameOf(scene)}</option>)}</select></label>:<>
          <label>Remote child name<input value={String(draft.child_name||'')} onChange={(e)=>field('child_name',e.target.value)}/></label>
          <label>Remote child UUID<input value={String(draft.remote_child_id||'')} onChange={(e)=>field('remote_child_id',e.target.value)}/></label>
          <label className="wide">MQTT host<input value={String(draft.host_name||'')} onChange={(e)=>field('host_name',e.target.value)} placeholder="broker.example.com"/></label>
          <label>MQTT username<input value={String(draft.mqtt_username||'')} onChange={(e)=>field('mqtt_username',e.target.value)}/></label>
          <label>MQTT password<input type="password" value={String(draft.mqtt_password||'')} onChange={(e)=>field('mqtt_password',e.target.value)} placeholder={draft.has_mqtt_password?'Stored — leave blank to keep':'Required'}/></label>
        </>}
        <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.retrack)} onChange={(e)=>field('retrack',e.target.checked)}/>Retrack child objects in parent</label>
        <label>Transform<select value={String(draft.transform_type||'euler')} onChange={(e)=>field('transform_type',e.target.value)}><option value="euler">Euler</option><option value="quaternion">Quaternion</option><option value="matrix">Matrix</option></select></label>
      </div>
      {draft.transform_type==='matrix'?<div className="scene-subsection"><h3>4×4 transform matrix</h3><div className="matrix-grid">{(Array.isArray(draft.matrix)&&draft.matrix.length===16?draft.matrix:identity).map((value:number,index:number)=><input key={index} type="number" step="any" value={Number(value)} onChange={(e)=>{const next=Array.isArray(draft.matrix)&&draft.matrix.length===16?[...draft.matrix]:[...identity];next[index]=Number(e.target.value);field('matrix',next)}}/>)}</div></div>:<div className="scene-subsection"><h3>Child → parent transform</h3><div className="transform-vector-grid">
        <div><b>translation</b>{vector(draft.transform?.translation,3,[0,0,0]).map((value,index)=><label key={index}>{['X','Y','Z'][index]}<input type="number" step="any" value={value} onChange={(e)=>tfield('translation',index,Number(e.target.value))}/></label>)}</div>
        {draft.transform_type==='quaternion'
          ? <div className="quaternion-row"><b>quaternion</b>{vector(draft.quaternion,4,[0,0,0,1]).map((value,index)=><label key={index}>{['X','Y','Z','W'][index]}<input type="number" step="any" value={value} onChange={(e)=>{const next=vector(draft.quaternion,4,[0,0,0,1]);next[index]=Number(e.target.value);field('quaternion',next)}}/></label>)}</div>
          : <div><b>rotation</b>{vector(draft.transform?.rotation,3,[0,0,0]).map((value,index)=><label key={index}>{['X°','Y°','Z°'][index]}<input type="number" step="any" value={value} onChange={(e)=>tfield('rotation',index,Number(e.target.value))}/></label>)}</div>}
        <div><b>scale</b>{vector(draft.transform?.scale,3,[1,1,1]).map((value,index)=><label key={index}>{['X','Y','Z'][index]}<input type="number" step="any" value={value} onChange={(e)=>tfield('scale',index,Number(e.target.value))}/></label>)}</div>
      </div></div>}
      {draft.child_type==='remote'&&<div className="hierarchy-runtime"><div><span>Cached child ROIs</span><b>{Array.isArray(draft.cached_rois)?draft.cached_rois.length:0}</b></div><div><span>Cached child tripwires</span><b>{Array.isArray(draft.cached_tripwires)?draft.cached_tripwires.length:0}</b></div><p>Remote geometry catalog updates are persisted without forcing a controller configuration reload. Source timestamps remain on the child stream; <b>Retrack</b> controls whether parent tracking assigns new parent tracks.</p></div>}
      <div className="editor-actions camera-save-actions">{selected&&<button className="btn danger-button" disabled={busy} onClick={()=>void remove()}>Delete link</button>}{isAdmin&&<button className="btn btn-primary" disabled={busy} onClick={()=>void save()}>{busy?'Working…':'Save hierarchy link'}</button>}</div>
      {parentScene&&<div className="hierarchy-parent-note">Parent: <b>{nameOf(parentScene)}</b> · {idOf(parentScene)}</div>}
    </section>
  </div>
}
