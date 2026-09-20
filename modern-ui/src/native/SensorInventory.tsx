import { useEffect, useMemo, useState } from 'react'
import type { MouseEvent } from 'react'
import { apiFetch, apiObjectUrl } from '../api/client'

type Row = Record<string, any>
const idOf=(row:Row)=>String(row.uid??row.sensor_id??row.id??'')
const nameOf=(row:Row)=>String(row.name??row.uid??'Sensor')
const defaultRanges={sectors:[{color:'green',color_min:0},{color:'yellow',color_min:2},{color:'red',color_min:5}],range_max:10}
const imagePath=(scene:Row)=>{
  const values=[scene.thumbnail,scene.map].map((value)=>String(value||''))
  return values.find((value)=>/^\/media\/.+\.(png|jpe?g|webp)$/i.test(value))||''
}

function SensorMapEditor({
  scene,sensor,center,points,iconUrl,onCenter,onPoint,
}:{
  scene:Row|null;sensor:Row;center:number[]|null;points:number[][];iconUrl:string;
  onCenter:(point:number[])=>void;onPoint:(point:number[])=>void;
}) {
  const [url,setUrl]=useState('')
  const [size,setSize]=useState<[number,number]>([1000,700])
  const path=scene?imagePath(scene):''
  const scale=Math.max(1,Number(scene?.scale||100))
  useEffect(()=>{
    let alive=true,current=''
    setUrl('')
    if(!path)return
    void apiObjectUrl(path).then((next)=>{
      if(!alive){URL.revokeObjectURL(next);return}
      const img=new Image()
      img.onload=()=>{if(alive){setSize([Math.max(1,img.naturalWidth),Math.max(1,img.naturalHeight)]);setUrl(next);current=next}else URL.revokeObjectURL(next)}
      img.onerror=()=>URL.revokeObjectURL(next)
      img.src=next
    }).catch(()=>{})
    return()=>{alive=false;if(current)URL.revokeObjectURL(current)}
  },[path])
  const xy=(point:number[])=>[Number(point?.[0]||0)*scale,size[1]-Number(point?.[1]||0)*scale] as const
  const sensorCenter=center||(
    Array.isArray(sensor.center)?sensor.center:
    Array.isArray(sensor.translation)?sensor.translation.slice(0,2):null
  )
  const svgPoints=points.map((point)=>xy(point).join(',')).join(' ')
  const click=(event:MouseEvent<SVGSVGElement>)=>{
    const rect=event.currentTarget.getBoundingClientRect()
    const px=((event.clientX-rect.left)/Math.max(rect.width,1))*size[0]
    const py=((event.clientY-rect.top)/Math.max(rect.height,1))*size[1]
    const point=[px/scale,(size[1]-py)/scale]
    if(sensor.area==='poly') onPoint(point)
    else onCenter(point)
  }
  return <div className="sensor-map-frame">
    <svg viewBox={`0 0 ${size[0]} ${size[1]}`} onClick={click}>
      {url&&<image href={url} x="0" y="0" width={size[0]} height={size[1]} preserveAspectRatio="none"/>}
      {sensor.area==='scene'&&<rect x="2" y="2" width={Math.max(0,size[0]-4)} height={Math.max(0,size[1]-4)} className="sensor-scene-area"/>}
      {sensor.area==='poly'&&points.length>1&&<polygon points={svgPoints} className="sensor-poly-area"/>}
      {sensor.area==='poly'&&points.map((point,index)=>{const [x,y]=xy(point);return <g key={index}><circle cx={x} cy={y} r="7" className="sensor-vertex"/><text x={x+10} y={y-8} className="map-label">{index+1}</text></g>})}
      {sensor.area==='circle'&&sensorCenter&&(()=>{const [x,y]=xy(sensorCenter);return <circle cx={x} cy={y} r={Math.max(1,Number(sensor.radius||0)*scale)} className="sensor-circle-area"/>})()}
      {sensorCenter&&(()=>{const [x,y]=xy(sensorCenter);return <g>{iconUrl?<image href={iconUrl} x={x-14} y={y-14} width="28" height="28" preserveAspectRatio="xMidYMid meet" className="sensor-map-icon"/>:<circle cx={x} cy={y} r="9" className="sensor-center-dot"/>}<text x={x+12} y={y-9} className="map-label">{String(sensor.name||'Sensor')}</text></g>})()}
    </svg>
    {!url&&<div className="map-watermark">No renderable 2D map is available for this scene. Numeric geometry can still be edited.</div>}
  </div>
}

export default function SensorInventory({isAdmin}:{isAdmin:boolean}){
  const [rows,setRows]=useState<Row[]>([])
  const [scenes,setScenes]=useState<Row[]>([])
  const [selected,setSelected]=useState<Row|null>(null)
  const [query,setQuery]=useState('')
  const [draft,setDraft]=useState<Row>({uid:'',name:'',scene:'',area:'scene',singleton_type:'environmental',visible:false})
  const [center,setCenter]=useState<number[]|null>(null)
  const [points,setPoints]=useState<number[][]>([])
  const [ranges,setRanges]=useState<Row>(defaultRanges)
  const [iconFile,setIconFile]=useState<File|null>(null)
  const [iconUrl,setIconUrl]=useState('')
  const [telemetry,setTelemetry]=useState<Row[]>([])
  const [busy,setBusy]=useState(false)
  const [message,setMessage]=useState('')
  const [error,setError]=useState('')

  const load=()=>{
    void apiFetch<Row[]>('/api/v2/sensors').then(setRows).catch((e)=>setError(String(e)))
    void apiFetch<Row[]>('/api/v2/scenes').then(setScenes).catch(()=>{})
  }
  useEffect(load,[])
  const filtered=useMemo(()=>rows.filter((row)=>JSON.stringify(row).toLowerCase().includes(query.toLowerCase())),[rows,query])
  const scene=scenes.find((item)=>idOf(item)===String(draft.scene||''))||null

  const open=(row:Row|null)=>{
    const value: Row = row ? { ...row } : { uid:'',name:'',scene:'',area:'scene',singleton_type:'environmental',visible:false,radius:1 }
    setSelected(row);setDraft(value)
    const c=Array.isArray(value.center)?value.center:(Array.isArray(value.translation)&&value.translation[0]!=null?[value.translation[0],value.translation[1]]:null)
    setCenter(c?c.map(Number):null)
    setPoints(Array.isArray(value.points)?value.points.map((p:any)=>[Number(p[0]),Number(p[1])]):[])
    setRanges(value.color_ranges?JSON.parse(JSON.stringify(value.color_ranges)):JSON.parse(JSON.stringify(defaultRanges)))
    setIconFile(null);setTelemetry([]);setMessage('');setError('')
  }
  useEffect(()=>{
    let alive=true,current=''
    setIconUrl('')
    const icon=String(draft.icon||'')
    if(!icon)return
    void apiObjectUrl(icon).then((url)=>{if(alive){current=url;setIconUrl(url)}else URL.revokeObjectURL(url)}).catch(()=>{})
    return()=>{alive=false;if(current)URL.revokeObjectURL(current)}
  },[draft.icon])

  const refreshTelemetry=()=>{
    if(!selected)return
    void apiFetch<Row[]>(`/api/v2/sensors/${encodeURIComponent(idOf(selected))}/telemetry?limit=20`)
      .then(setTelemetry).catch(()=>setTelemetry([]))
  }
  useEffect(()=>{if(selected)refreshTelemetry();else setTelemetry([])},[selected?idOf(selected):''])

  const field=(key:string,value:unknown)=>setDraft((old)=>({...old,[key]:value}))
  const setSector=(color:string,value:number)=>setRanges((old)=>({...old,sectors:(old.sectors||[]).map((item:Row)=>item.color===color?{...item,color_min:value}:item)}))

  const payload=()=>{
    const body:Row={
      name:String(draft.name||''),
      scene:draft.scene||null,
      area:String(draft.area||'scene'),
      singleton_type:String(draft.singleton_type||'environmental'),
      visible:Boolean(draft.visible),
      color_ranges:{
        sectors:(ranges.sectors||[]).map((item:Row)=>({color:String(item.color),color_min:Number(item.color_min)})),
        range_max:Number(ranges.range_max),
      },
    }
    if(!selected||String(draft.uid||'')!==idOf(selected)) body.sensor_id=String(draft.uid||draft.name||'')
    if(center) body.center=center.map(Number)
    if(body.area==='circle') body.radius=Number(draft.radius)
    if(body.area==='poly') body.points=points
    return body
  }

  const uploadIcon=async(saved:Row)=>{
    if(!iconFile)return saved
    const form=new FormData();form.append('icon',iconFile)
    return await apiFetch<Row>(`/api/v2/sensors/${encodeURIComponent(idOf(saved))}/icon?revision=${saved.revision}`,{method:'POST',body:form})
  }

  const save=async()=>{
    if(!isAdmin)return
    if(draft.area==='poly'&&points.length<3){setError('A custom polygon measurement area requires at least 3 vertices.');return}
    if(draft.area==='circle'&&!center){setError('A circular measurement area requires a sensor center. Click the map or enter X/Y coordinates.');return}
    setBusy(true);setError('');setMessage('')
    try{
      let saved:Row
      if(selected) saved=await apiFetch<Row>(`/api/v2/sensors/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`,{method:'PUT',body:JSON.stringify(payload())})
      else saved=await apiFetch<Row>('/api/v2/sensors',{method:'POST',body:JSON.stringify(payload())})
      saved=await uploadIcon(saved)
      setSelected(saved);setDraft({...saved});setIconFile(null)
      setMessage('Sensor configuration and measurement area saved.')
      load()
    }catch(e){setError(String(e))}finally{setBusy(false)}
  }
  const remove=async()=>{
    if(!selected||!window.confirm(`Delete ${nameOf(selected)}?`))return
    setBusy(true);setError('')
    try{await apiFetch(`/api/v2/sensors/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`,{method:'DELETE'});setSelected(null);open(null);load()}
    catch(e){setError(String(e))}finally{setBusy(false)}
  }
  const removeIcon=async()=>{
    if(!selected)return
    setBusy(true)
    try{
      const saved=await apiFetch<Row>(`/api/v2/sensors/${encodeURIComponent(idOf(selected))}/icon?revision=${selected.revision}`,{method:'DELETE'})
      setSelected(saved);setDraft({...saved});setIconFile(null);load()
    }catch(e){setError(String(e))}finally{setBusy(false)}
  }

  return <>
    <div className="page-header"><div><div className="kicker">Configuration · sensor plane</div><h1>Sensors</h1></div><div className="header-actions">{isAdmin&&<button className="btn btn-primary" onClick={()=>open(null)}>New sensor</button>}</div></div>
    {message&&<div className="notice-box">{message}</div>}{error&&<div className="error-box">{error}</div>}
    <div className="config-grid sensor-lifecycle-layout">
      <section className="panel">
        <div className="toolbar camera-toolbar"><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Search sensors"/><span className="muted">{filtered.length} configured</span></div>
        <div className="scene-list">{filtered.map((row)=><button key={idOf(row)} className={selected&&idOf(selected)===idOf(row)?'scene-config-row active':'scene-config-row'} onClick={()=>open(row)}><span><b>{nameOf(row)}</b><small>{idOf(row)}</small></span><span><small>{row.area||'scene'} · {row.singleton_type||'environmental'}</small></span></button>)}{!filtered.length&&<div className="table-empty">No sensors configured</div>}</div>
      </section>
      <section className="panel sensor-editor">
        <div className="panel-title"><div><h2>{selected?`Manage ${nameOf(selected)}`:'Create sensor'}</h2><p>Location, measurement area, sensor type and scalar thresholds</p></div>{selected&&<button className="btn" onClick={()=>open(null)}>New</button>}</div>
        <div className="sensor-editor-grid">
          <div className="sensor-fields">
            <div className="scene-form-grid">
              <label>Sensor ID<input value={String(draft.uid||'')} onChange={(e)=>field('uid',e.target.value)}/></label>
              <label>Name<input value={String(draft.name||'')} onChange={(e)=>field('name',e.target.value)}/></label>
              <label>Scene<select value={String(draft.scene||'')} onChange={(e)=>{field('scene',e.target.value);setCenter(null);setPoints([])}}><option value="">No scene</option>{scenes.map((item)=><option key={idOf(item)} value={idOf(item)}>{nameOf(item)}</option>)}</select></label>
              <label>Sensor type<select value={String(draft.singleton_type||'environmental')} onChange={(e)=>field('singleton_type',e.target.value)}><option value="environmental">environmental</option><option value="attribute">attribute</option></select></label>
              <label>Measurement area<select value={String(draft.area||'scene')} onChange={(e)=>field('area',e.target.value)}><option value="scene">Entire scene</option><option value="circle">Circle</option><option value="poly">Custom polygon</option></select></label>
              {draft.area==='circle'&&<label>Radius (meters)<input type="number" min="0" step="0.1" value={Number(draft.radius??1)} onChange={(e)=>field('radius',Number(e.target.value))}/></label>}
              <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.visible)} onChange={(e)=>field('visible',e.target.checked)}/>Visible in scene</label>
              <label>Sensor X (m)<input type="number" step="any" value={center?.[0]??''} onChange={(e)=>setCenter([Number(e.target.value||0),Number(center?.[1]??0)])}/></label>
              <label>Sensor Y (m)<input type="number" step="any" value={center?.[1]??''} onChange={(e)=>setCenter([Number(center?.[0]??0),Number(e.target.value||0)])}/></label>
            </div>
            <div className="scene-subsection"><h3>Color range</h3><div className="scene-form-grid">{['green','yellow','red'].map((color)=>{const sector=(ranges.sectors||[]).find((item:Row)=>item.color===color)||{};return <label key={color}>{color} minimum<input type="number" step="any" value={Number(sector.color_min??0)} onChange={(e)=>setSector(color,Number(e.target.value))}/></label>})}<label>Range maximum<input type="number" step="any" value={Number(ranges.range_max??10)} onChange={(e)=>setRanges((old)=>({...old,range_max:Number(e.target.value)}))}/></label></div></div>
            <div className="scene-subsection"><h3>Sensor icon</h3><div className="sensor-icon-row">{iconUrl?<img src={iconUrl} alt="Sensor icon" className="sensor-icon-preview"/>:<div className="sensor-icon-placeholder">Default red marker</div>}<label className="file-field">PNG/JPEG icon<input type="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg" onChange={(e)=>setIconFile(e.target.files?.[0]||null)}/></label>{selected&&draft.icon&&<button className="btn" onClick={()=>void removeIcon()}>Remove icon</button>}</div></div>
            {selected&&<div className="scene-subsection"><div className="sensor-telemetry-title"><h3>Telemetry</h3><button className="btn" onClick={refreshTelemetry}>Refresh</button></div><div className="sensor-telemetry-list">{telemetry.slice(0,8).map((item)=><div key={item.id}><b>{item.value===null||item.value===undefined?'—':typeof item.value==='object'?JSON.stringify(item.value):String(item.value)}</b><span>{String(item.timestamp||'')}</span></div>)}{!telemetry.length&&<div className="table-empty">No retained sensor values yet.</div>}</div></div>}
          </div>
          <div className="sensor-map-column">
            <div className="sensor-map-help">{draft.area==='poly'?'Click map vertices in order. Use Reset polygon to redraw.':'Click the map to place or move the sensor.'}</div>
            <SensorMapEditor scene={scene} sensor={draft} center={center} points={points} iconUrl={iconUrl} onCenter={setCenter} onPoint={(point)=>setPoints((old)=>[...old,point])}/>
            <div className="editor-actions">{draft.area==='poly'&&<button className="btn" onClick={()=>setPoints([])}>Reset polygon</button>}</div>
            {draft.area==='poly'&&<div className="point-strip">{points.map((point,index)=><code key={index}>{index+1}: {point.map((v)=>v.toFixed(2)).join(', ')}</code>)}</div>}
          </div>
        </div>
        <div className="editor-actions camera-save-actions">{selected&&<button className="btn danger-button" disabled={busy} onClick={()=>void remove()}>Delete</button>}{isAdmin&&<button className="btn btn-primary" disabled={busy} onClick={()=>void save()}>{busy?'Working…':'Save sensor'}</button>}</div>
      </section>
    </div>
  </>
}
