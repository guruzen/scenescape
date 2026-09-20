import { useEffect, useMemo, useRef, useState } from 'react'
import type { MouseEvent, PointerEvent } from 'react'
import { apiFetch, apiObjectUrl } from '../api/client'

type Row = Record<string, any>
type SpatialKind = 'region' | 'tripwire'

const idOf=(row:Row)=>String(row.uid??row.uuid??row.id??'')
const nameOf=(row:Row)=>String(row.name??row.uid??'Geometry')
const defaults={sectors:[{color:'green',color_min:0},{color:'yellow',color_min:2},{color:'red',color_min:5}],range_max:10}
const imagePath=(scene:Row)=>{
  const values=[scene.thumbnail,scene.map].map((value)=>String(value||''))
  return values.find((value)=>/^\/media\/.+\.(png|jpe?g|webp)$/i.test(value))||''
}

function GeometryMap({
  scene,regions,tripwires,kind,selectedId,draft,points,onPoints,
}:{
  scene:Row;regions:Row[];tripwires:Row[];kind:SpatialKind;selectedId:string;
  draft:Row;points:number[][];onPoints:(points:number[][])=>void;
}){
  const [url,setUrl]=useState('')
  const [size,setSize]=useState<[number,number]>([1000,700])
  const dragIndex=useRef<number|null>(null)
  const moved=useRef(false)
  const path=imagePath(scene)
  const scale=Math.max(1,Number(scene.scale||100))

  useEffect(()=>{
    let alive=true,current=''
    setUrl('')
    if(!path)return
    void apiObjectUrl(path).then((next)=>{
      if(!alive){URL.revokeObjectURL(next);return}
      const img=new Image()
      img.onload=()=>{if(alive){setSize([Math.max(1,img.naturalWidth),Math.max(1,img.naturalHeight)]);current=next;setUrl(next)}else URL.revokeObjectURL(next)}
      img.onerror=()=>URL.revokeObjectURL(next)
      img.src=next
    }).catch(()=>{})
    return()=>{alive=false;if(current)URL.revokeObjectURL(current)}
  },[path])

  const xy=(point:number[])=>[Number(point?.[0]||0)*scale,size[1]-Number(point?.[1]||0)*scale] as const
  const fromEvent=(event:{clientX:number;clientY:number;currentTarget:SVGSVGElement})=>{
    const rect=event.currentTarget.getBoundingClientRect()
    const px=((event.clientX-rect.left)/Math.max(rect.width,1))*size[0]
    const py=((event.clientY-rect.top)/Math.max(rect.height,1))*size[1]
    return [px/scale,(size[1]-py)/scale]
  }
  const persisted=(row:Row,shape:SpatialKind)=>{
    if(idOf(row)===selectedId)return null
    const value=(row.points||[]).map((p:any)=>xy(p).join(',')).join(' ')
    if(!value)return null
    return shape==='region'
      ? <polygon key={idOf(row)} points={value} className="spatial-existing-region"/>
      : <polyline key={idOf(row)} points={value} className="spatial-existing-tripwire"/>
  }
  const draftPoints=points.map((p)=>xy(p).join(',')).join(' ')
  const click=(event:MouseEvent<SVGSVGElement>)=>{
    if(moved.current){moved.current=false;return}
    if(dragIndex.current!==null)return
    onPoints([...points,fromEvent(event)])
  }
  const pointerMove=(event:PointerEvent<SVGSVGElement>)=>{
    if(dragIndex.current===null)return
    moved.current=true
    const next=[...points]
    next[dragIndex.current]=fromEvent(event)
    onPoints(next)
  }
  const pointerUp=()=>{dragIndex.current=null}

  return <div className="spatial-map-frame">
    <svg
      viewBox={`0 0 ${size[0]} ${size[1]}`}
      onClick={click}
      onPointerMove={pointerMove}
      onPointerUp={pointerUp}
      onPointerCancel={pointerUp}
    >
      <defs><marker id="trip-arrow" markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" className="trip-arrow-head"/></marker></defs>
      {url&&<image href={url} x="0" y="0" width={size[0]} height={size[1]} preserveAspectRatio="none"/>}
      {regions.map((row)=>persisted(row,'region'))}
      {tripwires.map((row)=>persisted(row,'tripwire'))}
      {kind==='region'&&draftPoints&&<polygon points={draftPoints} className="spatial-draft-region"/>}
      {kind==='tripwire'&&draftPoints&&<polyline points={draftPoints} className="spatial-draft-tripwire" markerEnd="url(#trip-arrow)"/>}
      {points.map((point,index)=>{const [x,y]=xy(point);return <g key={index}>
        <circle
          cx={x} cy={y} r="8" className="spatial-vertex"
          onPointerDown={(event)=>{event.stopPropagation();dragIndex.current=index;(event.currentTarget as SVGCircleElement).setPointerCapture(event.pointerId)}}
        />
        <text x={x+11} y={y-9} className="map-label">{index+1}</text>
      </g>})}
    </svg>
    {!url&&<div className="map-watermark">No renderable 2D map is available; coordinates can still be authored on the scene canvas.</div>}
  </div>
}

export default function SpatialEditor({
  scene,regions,tripwires,isAdmin,onSaved,
}:{
  scene:Row;regions:Row[];tripwires:Row[];isAdmin:boolean;onSaved:()=>void;
}){
  const [kind,setKind]=useState<SpatialKind>('region')
  const [selectedId,setSelectedId]=useState('')
  const [draft,setDraft]=useState<Row>({name:'',height:1,buffer_size:0,volumetric:false,visible:false})
  const [points,setPoints]=useState<number[][]>([])
  const [ranges,setRanges]=useState<Row>(JSON.parse(JSON.stringify(defaults)))
  const [message,setMessage]=useState('')
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)

  const rows=kind==='region'?regions:tripwires
  const selected=useMemo(()=>rows.find((row)=>idOf(row)===selectedId)||null,[rows,selectedId])
  const sceneId=idOf(scene)

  const open=(nextKind:SpatialKind,row:Row|null)=>{
    setKind(nextKind)
    setSelectedId(row?idOf(row):'')
    setDraft(row?{...row}:{name:'',height:1,buffer_size:0,volumetric:false,visible:false})
    setPoints(Array.isArray(row?.points)?row!.points.map((p:any)=>[Number(p[0]),Number(p[1])]):[])
    setRanges(row?.color_ranges?JSON.parse(JSON.stringify(row.color_ranges)):JSON.parse(JSON.stringify(defaults)))
    setMessage('');setError('')
  }
  useEffect(()=>{
    if(selectedId&&!rows.some((row)=>idOf(row)===selectedId))open(kind,null)
  },[rows.length])

  const field=(key:string,value:unknown)=>setDraft((old)=>({...old,[key]:value}))
  const setSector=(color:string,value:number)=>setRanges((old)=>({...old,sectors:(old.sectors||[]).map((item:Row)=>item.color===color?{...item,color_min:value}:item)}))
  const valid=kind==='region'?points.length>=3:points.length>=2

  const payload=()=>{
    const body:Row={
      name:String(draft.name||'').trim(),
      scene:sceneId,
      points,
      height:Number(draft.height??1),
      visible:Boolean(draft.visible),
    }
    if(kind==='region'){
      body.buffer_size=Number(draft.buffer_size??0)
      body.volumetric=Boolean(draft.volumetric)
      body.color_ranges={
        sectors:(ranges.sectors||[]).map((item:Row)=>({color:String(item.color),color_min:Number(item.color_min)})),
        range_max:Number(ranges.range_max),
      }
    }
    return body
  }

  const save=async()=>{
    if(!isAdmin)return
    if(!String(draft.name||'').trim()){setError('Name is required.');return}
    if(!valid){setError(kind==='region'?'A region requires at least 3 points.':'A tripwire requires at least 2 points.');return}
    setBusy(true);setError('');setMessage('')
    try{
      const plural=kind==='region'?'regions':'tripwires'
      let saved:Row
      if(selected){
        saved=await apiFetch<Row>(`/api/v2/${plural}/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`,{method:'PUT',body:JSON.stringify(payload())})
      }else{
        saved=await apiFetch<Row>(`/api/v2/${plural}`,{method:'POST',body:JSON.stringify(payload())})
      }
      setSelectedId(idOf(saved));setDraft({...saved});setPoints((saved.points||[]).map((p:any)=>[Number(p[0]),Number(p[1])]))
      if(saved.color_ranges)setRanges(JSON.parse(JSON.stringify(saved.color_ranges)))
      setMessage(`${kind==='region'?'Region':'Tripwire'} saved.`)
      onSaved()
    }catch(e){setError(String(e))}finally{setBusy(false)}
  }

  const remove=async()=>{
    if(!selected||!isAdmin||!window.confirm(`Delete ${nameOf(selected)}?`))return
    setBusy(true);setError('')
    try{
      const plural=kind==='region'?'regions':'tripwires'
      await apiFetch(`/api/v2/${plural}/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`,{method:'DELETE'})
      open(kind,null);onSaved()
    }catch(e){setError(String(e))}finally{setBusy(false)}
  }

  return <div className="spatial-workspace">
    <section className="panel spatial-list-panel">
      <div className="panel-title"><div><h2>Spatial analytics</h2><p>Regions, volumetric occupancy and directional tripwires</p></div></div>
      <div className="spatial-kind-tabs">
        <button className={kind==='region'?'btn active-tab':'btn'} onClick={()=>open('region',null)}>Regions ({regions.length})</button>
        <button className={kind==='tripwire'?'btn active-tab':'btn'} onClick={()=>open('tripwire',null)}>Tripwires ({tripwires.length})</button>
      </div>
      <div className="scene-list">
        {rows.map((row)=><button key={idOf(row)} className={selectedId===idOf(row)?'scene-config-row active':'scene-config-row'} onClick={()=>open(kind,row)}>
          <span><b>{nameOf(row)}</b><small>{idOf(row)}</small></span>
          <span><small>{(row.points||[]).length} pts · {row.visible?'visible':'hidden'}</small></span>
        </button>)}
        {!rows.length&&<div className="table-empty">No {kind==='region'?'regions':'tripwires'} configured</div>}
      </div>
      {isAdmin&&<button className="btn btn-primary spatial-new" onClick={()=>open(kind,null)}>New {kind}</button>}
    </section>

    <section className="panel spatial-editor-panel">
      <div className="panel-title"><div><h2>{selected?`Edit ${nameOf(selected)}`:`New ${kind}`}</h2><p>Point order is preserved by the controller. Tripwire order determines crossing direction.</p></div>{selected&&<span className="status-pill">{idOf(selected)}</span>}</div>
      {message&&<div className="notice-box spatial-message">{message}</div>}
      {error&&<div className="error-box spatial-message">{error}</div>}
      <div className="spatial-editor-grid">
        <div className="spatial-settings">
          <div className="scene-form-grid">
            <label className="wide">Name<input value={String(draft.name||'')} onChange={(e)=>field('name',e.target.value)}/></label>
            <label>Height (m)<input type="number" step="0.01" value={Number(draft.height??1)} onChange={(e)=>field('height',Number(e.target.value))}/></label>
            <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.visible)} onChange={(e)=>field('visible',e.target.checked)}/>Visible</label>
            {kind==='region'&&<>
              <label>Buffer size (m)<input type="number" min="0" step="0.01" value={Number(draft.buffer_size??0)} onChange={(e)=>field('buffer_size',Number(e.target.value))}/></label>
              <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.volumetric)} onChange={(e)=>field('volumetric',e.target.checked)}/>Volumetric occupancy</label>
            </>}
          </div>
          {kind==='region'&&<div className="scene-subsection"><h3>Occupancy color thresholds</h3><div className="scene-form-grid">
            {['green','yellow','red'].map((color)=>{const sector=(ranges.sectors||[]).find((item:Row)=>item.color===color)||{};return <label key={color}>{color} minimum<input type="number" step="any" value={Number(sector.color_min??0)} onChange={(e)=>setSector(color,Number(e.target.value))}/></label>})}
            <label>Range maximum<input type="number" step="any" value={Number(ranges.range_max??10)} onChange={(e)=>setRanges((old)=>({...old,range_max:Number(e.target.value)}))}/></label>
          </div></div>}
          <div className="scene-subsection"><h3>Vertices</h3>
            <div className="spatial-point-list">{points.map((point,index)=><div key={index}><b>{index+1}</b><input type="number" step="any" value={point[0]} onChange={(e)=>setPoints((old)=>old.map((p,i)=>i===index?[Number(e.target.value),p[1]]:p))}/><input type="number" step="any" value={point[1]} onChange={(e)=>setPoints((old)=>old.map((p,i)=>i===index?[p[0],Number(e.target.value)]:p))}/><button className="text-button" onClick={()=>setPoints((old)=>old.filter((_,i)=>i!==index))}>Remove</button></div>)}</div>
            <div className="editor-actions"><button className="btn" onClick={()=>setPoints([])}>Redraw</button>{kind==='tripwire'&&points.length>=2&&<button className="btn" onClick={()=>setPoints((old)=>[...old].reverse())}>Reverse direction</button>}</div>
          </div>
        </div>
        <div className="spatial-map-column">
          <div className="sensor-map-help">Click to add vertices. Drag an orange vertex to reposition it.</div>
          <GeometryMap scene={scene} regions={regions} tripwires={tripwires} kind={kind} selectedId={selectedId} draft={draft} points={points} onPoints={setPoints}/>
        </div>
      </div>
      <div className="editor-actions camera-save-actions">{selected&&<button className="btn danger-button" disabled={busy} onClick={()=>void remove()}>Delete</button>}{isAdmin&&<button className="btn btn-primary" disabled={busy} onClick={()=>void save()}>{busy?'Working…':`Save ${kind}`}</button>}</div>
    </section>
  </div>
}
