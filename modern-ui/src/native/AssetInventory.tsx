import { useEffect, useMemo, useState } from 'react'
import { apiFetch, apiObjectUrl } from '../api/client'
import ThreeScene from './ThreeScene'

type Row = Record<string, any>
const idOf=(row:Row)=>String(row.uid??row.id??'')
const nameOf=(row:Row)=>String(row.name??row.uid??'Asset')
const defaults:Row={
  name:'',x_size:1,y_size:1,z_size:1,x_buffer_size:0,y_buffer_size:0,z_buffer_size:0,
  tracking_radius:2,shift_type:1,mark_color:'#888888',scale:1,project_to_map:false,
  rotation_from_velocity:false,rotation_x:0,rotation_y:0,rotation_z:0,
  translation_x:0,translation_y:0,translation_z:0,geometric_center:[0,0,0],mass:1,
  center_of_mass:[0,0,0],is_static:false,ttl:0,linear_damping:.05,angular_damping:.05,
  coefficient_of_restitution:.5,friction_coefficients:[.5,.4]
}
const vec=(value:any,len:number,fallback:number[])=>Array.isArray(value)&&value.length===len?value.map(Number):fallback
export default function AssetInventory({isAdmin}:{isAdmin:boolean}){
  const [rows,setRows]=useState<Row[]>([])
  const [selected,setSelected]=useState<Row|null>(null)
  const [draft,setDraft]=useState<Row>({...defaults})
  const [query,setQuery]=useState('')
  const [modelFile,setModelFile]=useState<File|null>(null)
  const [modelUrl,setModelUrl]=useState('')
  const [message,setMessage]=useState('')
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  const load=()=>void apiFetch<Row[]>('/api/v2/assets').then(setRows).catch((e)=>setError(String(e)))
  useEffect(load,[])
  const filtered=useMemo(()=>rows.filter((row)=>JSON.stringify(row).toLowerCase().includes(query.toLowerCase())),[rows,query])
  const open=(row:Row|null)=>{setSelected(row);setDraft(row?{...defaults,...row}:{...defaults});setModelFile(null);setMessage('');setError('')}
  useEffect(()=>{
    let alive=true,current=''
    setModelUrl('')
    if(modelFile){
      current=URL.createObjectURL(modelFile)
      setModelUrl(current)
      return()=>{alive=false;if(current)URL.revokeObjectURL(current)}
    }
    const path=String(draft.model_3d||'')
    if(!path)return
    void apiObjectUrl(path).then((url)=>{if(alive){current=url;setModelUrl(url)}else URL.revokeObjectURL(url)}).catch(()=>{})
    return()=>{alive=false;if(current)URL.revokeObjectURL(current)}
  },[draft.model_3d,modelFile])
  const field=(key:string,value:any)=>setDraft((old)=>({...old,[key]:value}))
  const num=(key:string)=>Number(draft[key]??defaults[key]??0)
  const body=()=>{
    const value:Row={name:String(draft.name||'')}
    for(const key of ['x_size','y_size','z_size','x_buffer_size','y_buffer_size','z_buffer_size','tracking_radius','scale','rotation_x','rotation_y','rotation_z','translation_x','translation_y','translation_z','mass','ttl','linear_damping','angular_damping','coefficient_of_restitution']) value[key]=num(key)
    value.shift_type=Number(draft.shift_type??1)
    for(const key of ['project_to_map','rotation_from_velocity','is_static']) value[key]=Boolean(draft[key])
    value.mark_color=String(draft.mark_color||'#888888')
    value.geometric_center=vec(draft.geometric_center,3,[0,0,0])
    value.center_of_mass=vec(draft.center_of_mass,3,[0,0,0])
    value.friction_coefficients=vec(draft.friction_coefficients,2,[.5,.4])
    if(selected&&draft.model_3d===null)value.model_3d=null
    return value
  }
  const save=async()=>{
    if(!isAdmin)return
    setBusy(true);setError('');setMessage('')
    try{
      const form=new FormData()
      const payload=body()
      Object.entries(payload).forEach(([key,value])=>form.append(key,typeof value==='string'?value:(JSON.stringify(value)??'')))
      if(modelFile)form.append('model_3d',modelFile)
      let saved:Row
      if(selected)saved=await apiFetch<Row>(`/api/v2/assets/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`,{method:'PUT',body:form})
      else saved=await apiFetch<Row>('/api/v2/assets',{method:'POST',body:form})
      setSelected(saved);setDraft({...defaults,...saved});setModelFile(null);setMessage('Object library entry saved.');load()
    }catch(e){setError(String(e))}finally{setBusy(false)}
  }
  const remove=async()=>{
    if(!selected||!isAdmin||!window.confirm(`Delete ${nameOf(selected)}?`))return
    setBusy(true)
    try{await apiFetch(`/api/v2/assets/${encodeURIComponent(idOf(selected))}`,{method:'DELETE'});open(null);setSelected(null);load()}
    catch(e){setError(String(e))}finally{setBusy(false)}
  }
  const clearModel=()=>{setModelFile(null);field('model_3d',null);setModelUrl('')}
  return <>
    <div className="page-header"><div><div className="kicker">Configuration · visualization & tracking</div><h1>Object Library</h1></div>{isAdmin&&<button className="btn btn-primary" onClick={()=>open(null)}>New object class</button>}</div>
    {message&&<div className="notice-box">{message}</div>}{error&&<div className="error-box">{error}</div>}
    <div className="config-grid asset-library-layout">
      <section className="panel"><div className="toolbar camera-toolbar"><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Search object classes"/><span className="muted">{filtered.length} classes</span></div><div className="scene-list">{filtered.map((row)=><button key={idOf(row)} className={selected&&idOf(selected)===idOf(row)?'scene-config-row active':'scene-config-row'} onClick={()=>open(row)}><span><b>{nameOf(row)}</b><small>{row.model_3d?'GLB model':'box geometry'}</small></span><span><small>{row.x_size}×{row.y_size}×{row.z_size} m</small></span></button>)}{!filtered.length&&<div className="table-empty">No object classes configured</div>}</div></section>
      <section className="panel asset-editor">
        <div className="panel-title"><div><h2>{selected?`Manage ${nameOf(selected)}`:'Create object class'}</h2><p>Class name must exactly match the tracked object category.</p></div></div>
        <div className="asset-editor-grid">
          <div>
            <div className="scene-form-grid">
              <label className="wide">Class name<input value={String(draft.name||'')} onChange={(e)=>field('name',e.target.value)}/></label>
              {['x_size','y_size','z_size'].map((key)=><label key={key}>{key.replace('_',' ').toUpperCase()} (m)<input type="number" min="0" step="0.01" value={num(key)} onChange={(e)=>field(key,Number(e.target.value))}/></label>)}
              {['x_buffer_size','y_buffer_size','z_buffer_size'].map((key)=><label key={key}>{key.replaceAll('_',' ')}<input type="number" step="0.01" value={num(key)} onChange={(e)=>field(key,Number(e.target.value))}/></label>)}
              <label>Tracking radius (m)<input type="number" step="0.01" value={num('tracking_radius')} onChange={(e)=>field('tracking_radius',Number(e.target.value))}/></label>
              <label>Scale<input type="number" step="0.01" value={num('scale')} onChange={(e)=>field('scale',Number(e.target.value))}/></label>
              <label>Shift type<input type="number" step="1" value={num('shift_type')} onChange={(e)=>field('shift_type',Number(e.target.value))}/></label>
              <label>Mark color<input type="color" value={String(draft.mark_color||'#888888')} onChange={(e)=>field('mark_color',e.target.value)}/></label>
              <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.project_to_map)} onChange={(e)=>field('project_to_map',e.target.checked)}/>Project to map</label>
              <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.rotation_from_velocity)} onChange={(e)=>field('rotation_from_velocity',e.target.checked)}/>Rotation from velocity</label>
            </div>
            <div className="scene-subsection"><h3>Model transform</h3><div className="scene-form-grid">
              {['rotation_x','rotation_y','rotation_z'].map((key)=><label key={key}>{key.replace('_',' ')} (deg)<input type="number" step="0.1" value={num(key)} onChange={(e)=>field(key,Number(e.target.value))}/></label>)}
              {['translation_x','translation_y','translation_z'].map((key)=><label key={key}>{key.replace('_',' ')} (m)<input type="number" step="0.01" value={num(key)} onChange={(e)=>field(key,Number(e.target.value))}/></label>)}
            </div></div>
            <div className="scene-subsection"><h3>Physics & temporal behavior</h3><div className="scene-form-grid">
              <label>Mass (kg)<input type="number" min="0" step="0.01" value={num('mass')} onChange={(e)=>field('mass',Number(e.target.value))}/></label>
              <label>TTL (s)<input type="number" min="0" step="0.01" value={num('ttl')} onChange={(e)=>field('ttl',Number(e.target.value))}/></label>
              <label>Linear damping<input type="number" min="0" max="1" step="0.01" value={num('linear_damping')} onChange={(e)=>field('linear_damping',Number(e.target.value))}/></label>
              <label>Angular damping<input type="number" min="0" max="1" step="0.01" value={num('angular_damping')} onChange={(e)=>field('angular_damping',Number(e.target.value))}/></label>
              <label>Restitution<input type="number" min="0" max="1" step="0.01" value={num('coefficient_of_restitution')} onChange={(e)=>field('coefficient_of_restitution',Number(e.target.value))}/></label>
              <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.is_static)} onChange={(e)=>field('is_static',e.target.checked)}/>Static object</label>
              <label className="wide">Geometric center [x,y,z]<input value={JSON.stringify(vec(draft.geometric_center,3,[0,0,0]))} onChange={(e)=>{try{field('geometric_center',JSON.parse(e.target.value))}catch{}}}/></label>
              <label className="wide">Center of mass [x,y,z]<input value={JSON.stringify(vec(draft.center_of_mass,3,[0,0,0]))} onChange={(e)=>{try{field('center_of_mass',JSON.parse(e.target.value))}catch{}}}/></label>
              <label className="wide">Friction [static,dynamic]<input value={JSON.stringify(vec(draft.friction_coefficients,2,[.5,.4]))} onChange={(e)=>{try{field('friction_coefficients',JSON.parse(e.target.value))}catch{}}}/></label>
            </div></div>
            <div className="scene-subsection"><h3>3D model</h3><div className="asset-upload-row"><label className="file-field">GLB model<input type="file" accept=".glb,model/gltf-binary" onChange={(e)=>setModelFile(e.target.files?.[0]||null)}/></label>{draft.model_3d&&<button className="btn" onClick={clearModel}>Remove model</button>}<code>{modelFile?.name||draft.model_3d||'Default box geometry'}</code></div></div>
          </div>
          <aside className="asset-preview-panel"><div className="asset-preview-label">Live preview</div><ThreeScene objects={[]} scale={1} mediaOverrideUrl={modelUrl||undefined} previewAsset={draft}/></aside>
        </div>
        <div className="editor-actions camera-save-actions">{selected&&<button className="btn danger-button" disabled={busy} onClick={()=>void remove()}>Delete</button>}{isAdmin&&<button className="btn btn-primary" disabled={busy} onClick={()=>void save()}>{busy?'Working…':'Save object class'}</button>}</div>
      </section>
    </div>
  </>
}
