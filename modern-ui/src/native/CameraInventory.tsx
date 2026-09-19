import { useEffect, useMemo, useState } from 'react'
import { apiBlob, apiFetch, apiObjectUrl } from '../api/client'

type Row = Record<string, any>

const idOf = (row: Row) => String(row.uid ?? row.id ?? '')
const nameOf = (row: Row) => String(row.name ?? row.uid ?? 'Camera')
const defaults: Row = {
  uid: '',
  name: '',
  scene: '',
  command: '',
  camerachain: 'retail',
  resolution: [640, 480],
  intrinsics: { fx: 570, fy: 570, cx: 320, cy: 240 },
  distortion: { k1: 0, k2: 0, p1: 0, p2: 0, k3: 0 },
  transform_type: '3d-2d point correspondence',
  translation: [0, 0, 0],
  rotation: [0, 0, 0],
  scale: [1, 1, 1],
  cv_subsystem: 'AUTO',
  undistort: false,
  modelconfig: 'model_config.json',
  use_camera_pipeline: false,
  camera_pipeline: '',
  detection_labels: '',
}

const vectorText = (value: unknown, fallback: number[]) => JSON.stringify(Array.isArray(value) ? value : fallback)
const parseVector = (label: string, value: string, length: number) => {
  let parsed: unknown
  try { parsed = JSON.parse(value) } catch { throw new Error(`${label} must be valid JSON.`) }
  if (!Array.isArray(parsed) || parsed.length !== length || parsed.some((item) => !Number.isFinite(Number(item)))) {
    throw new Error(`${label} must contain exactly ${length} numeric values.`)
  }
  return parsed.map(Number)
}

export default function CameraInventory({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<Row[]>([])
  const [scenes, setScenes] = useState<Row[]>([])
  const [modelConfigs, setModelConfigs] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Row | null>(null)
  const [draft, setDraft] = useState<Row>({ ...defaults })
  const [translation, setTranslation] = useState('[0,0,0]')
  const [rotation, setRotation] = useState('[0,0,0]')
  const [scale, setScale] = useState('[1,1,1]')
  const [snapshot, setSnapshot] = useState('')
  const [pipeline, setPipeline] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => {
    void apiFetch<Row[]>('/api/v2/cameras').then(setRows).catch((e)=>setError(String(e)))
    void apiFetch<Row[]>('/api/v2/scenes').then(setScenes).catch(()=>{})
    void apiFetch<{configs:string[]}>('/api/v2/models/configs').then((value)=>setModelConfigs(value.configs||[])).catch(()=>{})
  }
  useEffect(load, [])
  const filtered = useMemo(() => rows.filter((row)=>JSON.stringify(row).toLowerCase().includes(query.toLowerCase())), [rows,query])

  const open = (row: Row | null) => {
    const value = row ? { ...defaults, ...row } : { ...defaults }
    setSelected(row)
    setDraft(value)
    setTranslation(vectorText(value.translation, [0,0,0]))
    setRotation(vectorText(value.rotation, [0,0,0]))
    setScale(vectorText(value.scale, [1,1,1]))
    setSnapshot('')
    setPipeline(String(value.camera_pipeline || ''))
    setMessage('')
    setError('')
  }
  const field = (key: string, value: unknown) => setDraft((old)=>({...old,[key]:value}))
  const nested = (key: 'intrinsics'|'distortion', name: string, value: number) => setDraft((old)=>({...old,[key]:{...(old[key]||{}),[name]:value}}))

  useEffect(() => {
    if (!selected) return
    let active = true
    let current = ''
    const refresh = async () => {
      try {
        const next = await apiObjectUrl(`/api/v2/cameras/${encodeURIComponent(idOf(selected))}/snapshot?t=${Date.now()}`)
        if (!active) { URL.revokeObjectURL(next); return }
        if (current) URL.revokeObjectURL(current)
        current = next
        setSnapshot(next)
      } catch {
        // A stopped VA pipeline is represented by the placeholder.
      }
    }
    void refresh()
    const timer = window.setInterval(refresh, 1200)
    return () => { active=false; window.clearInterval(timer); if(current) URL.revokeObjectURL(current) }
  }, [selected ? idOf(selected) : ''])

  const body = () => {
    const value: Row = {
      name: String(draft.name || ''),
      scene: draft.scene || null,
      command: String(draft.command || ''),
      camerachain: String(draft.camerachain || ''),
      resolution: [Number(draft.resolution?.[0] || 640), Number(draft.resolution?.[1] || 480)],
      intrinsics: {
        fx: Number(draft.intrinsics?.fx), fy: Number(draft.intrinsics?.fy),
        cx: Number(draft.intrinsics?.cx), cy: Number(draft.intrinsics?.cy),
      },
      distortion: {
        k1: Number(draft.distortion?.k1 || 0), k2: Number(draft.distortion?.k2 || 0),
        p1: Number(draft.distortion?.p1 || 0), p2: Number(draft.distortion?.p2 || 0),
        k3: Number(draft.distortion?.k3 || 0),
      },
      transform_type: String(draft.transform_type || '3d-2d point correspondence'),
      cv_subsystem: String(draft.cv_subsystem || 'AUTO'),
      undistort: Boolean(draft.undistort),
      modelconfig: String(draft.modelconfig || 'model_config.json'),
      use_camera_pipeline: Boolean(draft.use_camera_pipeline),
      camera_pipeline: String(draft.camera_pipeline || pipeline || ''),
      detection_labels: String(draft.detection_labels || ''),
    }
    if (!selected || String(draft.uid || '') !== idOf(selected)) value.sensor_id = String(draft.uid || draft.name || '').replace(/\s+/g,'_')
    if (value.transform_type !== '3d-2d point correspondence') {
      value.translation = parseVector('Translation', translation, 3)
      value.rotation = parseVector('Rotation', rotation, value.transform_type === 'quaternion' ? 4 : 3)
      value.scale = parseVector('Scale', scale, 3)
    } else if (Array.isArray(draft.transforms)) {
      value.transforms = draft.transforms
    }
    return value
  }

  const save = async () => {
    if (!isAdmin) return
    setBusy(true); setError(''); setMessage('')
    try {
      const payload = body()
      if (payload.command && payload.camerachain) {
        const validated = await apiFetch<Row>('/api/v2/camera-pipeline/preview', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        if (!draft.use_camera_pipeline) {
          setPipeline(String(validated.pipeline || ''))
        }
      }
      let saved: Row
      if (selected) {
        saved = await apiFetch<Row>(`/api/v2/cameras/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`, { method:'PUT', body:JSON.stringify(payload) })
      } else {
        saved = await apiFetch<Row>('/api/v2/cameras', { method:'POST', body:JSON.stringify(payload) })
      }
      setSelected(saved)
      setDraft({ ...defaults, ...saved })
      setTranslation(vectorText(saved.translation,[0,0,0]))
      setRotation(vectorText(saved.rotation,[0,0,0]))
      setScale(vectorText(saved.scale,[1,1,1]))
      setPipeline(String(saved.camera_pipeline || ''))
      setMessage('Camera configuration saved.')
      load()
    } catch(e) { setError(String(e)) } finally { setBusy(false) }
  }

  const remove = async () => {
    if (!selected || !isAdmin || !window.confirm(`Delete ${nameOf(selected)}?`)) return
    setBusy(true)
    try {
      await apiFetch(`/api/v2/cameras/${encodeURIComponent(idOf(selected))}`, {method:'DELETE'})
      open(null); setSelected(null); load()
    } catch(e) { setError(String(e)) } finally { setBusy(false) }
  }

  const previewPipeline = async () => {
    setBusy(true); setError('')
    try {
      const payload = body()
      const value = selected
        ? await apiFetch<Row>(`/api/v2/cameras/${encodeURIComponent(idOf(selected))}/pipeline-preview`, {method:'POST',body:JSON.stringify(payload)})
        : await apiFetch<Row>('/api/v2/camera-pipeline/preview', {method:'POST',body:JSON.stringify(payload)})
      setPipeline(String(value.pipeline || ''))
      field('camera_pipeline', String(value.pipeline || ''))
      setMessage('Pipeline preview generated from the current camera settings.')
    } catch(e) { setError(String(e)) } finally { setBusy(false) }
  }

  const downloadVideo = async () => {
    if (!selected) return
    setBusy(true); setError('')
    try {
      const blob = await apiBlob(`/api/v2/cameras/${encodeURIComponent(idOf(selected))}/video`)
      const url=URL.createObjectURL(blob)
      const link=document.createElement('a'); link.href=url; link.download=`${idOf(selected)}.mp4`; link.click()
      URL.revokeObjectURL(url)
    } catch(e) { setError(String(e)) } finally { setBusy(false) }
  }

  return <>
    <div className="page-header"><div><div className="kicker">Configuration · control plane</div><h1>Cameras</h1></div><div className="header-actions">{isAdmin && <button className="btn btn-primary" onClick={()=>open(null)}>New camera</button>}</div></div>
    {message && <div className="notice-box">{message}</div>}{error && <div className="error-box">{error}</div>}
    <div className="config-grid camera-lifecycle-layout">
      <section className="panel">
        <div className="toolbar camera-toolbar"><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Search cameras"/><span className="muted">{filtered.length} configured</span></div>
        <div className="scene-list">{filtered.map((row)=><button className={selected && idOf(selected)===idOf(row)?'scene-config-row active':'scene-config-row'} key={idOf(row)} onClick={()=>open(row)}><span><b>{nameOf(row)}</b><small>{idOf(row)}</small></span><span><small>{row.scene || 'orphaned'} · {row.cv_subsystem || 'AUTO'}</small></span></button>)}{!filtered.length && <div className="table-empty">No cameras configured</div>}</div>
      </section>
      <section className="panel camera-editor">
        <div className="panel-title"><div><h2>{selected ? `Manage ${nameOf(selected)}` : 'Create camera'}</h2><p>Camera identity, video source, intrinsics, pose and VA pipeline</p></div>{selected && <button className="btn" onClick={()=>open(null)}>New</button>}</div>
        <div className="camera-editor-grid">
          <div>
            <div className="scene-form-grid">
              <label>Camera ID<input value={String(draft.uid || '')} disabled={Boolean(selected && !isAdmin)} onChange={(e)=>field('uid',e.target.value)}/></label>
              <label>Name<input value={String(draft.name || '')} onChange={(e)=>field('name',e.target.value)}/></label>
              <label>Scene<select value={String(draft.scene || '')} onChange={(e)=>field('scene',e.target.value)}><option value="">No scene</option>{scenes.map((scene)=><option key={idOf(scene)} value={idOf(scene)}>{nameOf(scene)}</option>)}</select></label>
              <label>Decode device<select value={String(draft.cv_subsystem || 'AUTO')} onChange={(e)=>field('cv_subsystem',e.target.value)}><option>AUTO</option><option>GPU</option><option>CPU</option></select></label>
              <label className="wide">Video source<input value={String(draft.command || '')} onChange={(e)=>field('command',e.target.value)} placeholder="rtsp://…, http(s)://…, file://…, /dev/video…"/></label>
              <label>Camera chain<input value={String(draft.camerachain || '')} onChange={(e)=>field('camerachain',e.target.value)} placeholder="retail or retail+reid"/></label>
              <label>Model config<select value={String(draft.modelconfig || '')} onChange={(e)=>field('modelconfig',e.target.value)}><option value={String(draft.modelconfig || 'model_config.json')}>{String(draft.modelconfig || 'model_config.json')}</option>{modelConfigs.filter((name)=>name!==String(draft.modelconfig||'')).map((name)=><option key={name} value={name}>{name}</option>)}</select></label>
              <label>Width<input type="number" min="1" value={Number(draft.resolution?.[0] || 640)} onChange={(e)=>field('resolution',[Number(e.target.value),Number(draft.resolution?.[1]||480)])}/></label>
              <label>Height<input type="number" min="1" value={Number(draft.resolution?.[1] || 480)} onChange={(e)=>field('resolution',[Number(draft.resolution?.[0]||640),Number(e.target.value)])}/></label>
              <label>Transform type<select value={String(draft.transform_type || '3d-2d point correspondence')} onChange={(e)=>field('transform_type',e.target.value)}><option value="3d-2d point correspondence">3D-2D point correspondence</option><option value="euler">Euler</option><option value="quaternion">Quaternion</option><option value="matrix">Matrix</option></select></label>
              <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.undistort)} onChange={(e)=>field('undistort',e.target.checked)}/>Undistort</label>
            </div>
            {draft.transform_type !== '3d-2d point correspondence' && <div className="scene-subsection"><h3>Pose</h3><div className="scene-form-grid"><label>Translation<input value={translation} onChange={(e)=>setTranslation(e.target.value)}/></label><label>Rotation<input value={rotation} onChange={(e)=>setRotation(e.target.value)}/></label><label>Scale<input value={scale} onChange={(e)=>setScale(e.target.value)}/></label></div></div>}
            <div className="scene-subsection"><h3>Intrinsics & distortion</h3><div className="scene-form-grid">
              {(['fx','fy','cx','cy'] as const).map((key)=><label key={key}>{key.toUpperCase()}<input type="number" step="any" value={Number(draft.intrinsics?.[key] ?? 0)} onChange={(e)=>nested('intrinsics',key,Number(e.target.value))}/></label>)}
              {(['k1','k2','p1','p2','k3'] as const).map((key)=><label key={key}>{key}<input type="number" step="any" value={Number(draft.distortion?.[key] ?? 0)} onChange={(e)=>nested('distortion',key,Number(e.target.value))}/></label>)}
            </div></div>
            <div className="scene-subsection"><h3>VA pipeline</h3><div className="scene-form-grid"><label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.use_camera_pipeline)} onChange={(e)=>field('use_camera_pipeline',e.target.checked)}/>Use camera pipeline override</label><label className="wide">Detection labels<textarea value={String(draft.detection_labels || '')} onChange={(e)=>field('detection_labels',e.target.value)} placeholder={'car\npedestrian\ntrolley'}/></label><label className="wide">Camera pipeline<textarea value={String(draft.camera_pipeline || pipeline || '')} onChange={(e)=>{field('camera_pipeline',e.target.value);setPipeline(e.target.value)}}/></label></div></div>
          </div>
          <aside className="camera-preview-panel">
            <div className="camera-feed-frame">{snapshot ? <img src={snapshot} alt={selected?nameOf(selected):'Camera preview'}/> : <div className="camera-feed-placeholder">{selected?'Waiting for live JPEG…':'Save the camera to enable live preview.'}</div>}</div>
            <div className="editor-actions"><button className="btn" disabled={busy || !draft.command || !draft.camerachain} onClick={()=>void previewPipeline()}>Generate pipeline preview</button>{selected && <button className="btn" disabled={busy} onClick={()=>void downloadVideo()}>Download camera video</button>}</div>
          </aside>
        </div>
        <div className="editor-actions camera-save-actions">{selected && <button className="btn danger-button" disabled={busy} onClick={()=>void remove()}>Delete</button>}{isAdmin && <button className="btn btn-primary" disabled={busy} onClick={()=>void save()}>{busy?'Working…':'Save camera'}</button>}</div>
      </section>
    </div>
  </>
}
