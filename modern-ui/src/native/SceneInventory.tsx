import { useEffect, useMemo, useState } from 'react'
import { apiBlob, apiFetch } from '../api/client'

type Row = Record<string, any>

const idOf = (row: Row) => String(row.uid ?? row.id ?? '')
const nameOf = (row: Row) => String(row.name ?? row.uid ?? 'Unnamed')
const jsonText = (value: unknown, fallback: unknown) => JSON.stringify(value ?? fallback)
const numberOrNull = (value: string) => value.trim() === '' ? null : Number(value)
const defaultScene = {
  name: '',
  map_type: 'map_upload',
  scale: 100,
  use_tracker: true,
  output_lla: false,
  map_corners_lla: null,
  geospatial_provider: 'google',
  map_zoom: 15,
  map_center_lat: null,
  map_center_lng: null,
  map_bearing: 0,
  mesh_translation: [0, 0, 0],
  mesh_rotation: [0, 0, 0],
  mesh_scale: [1, 1, 1],
  trs_matrix: null,
}

function parseJson(label: string, raw: string, fallback: unknown) {
  if (!raw.trim()) return fallback
  try { return JSON.parse(raw) } catch { throw new Error(`${label} must contain valid JSON.`) }
}

export default function SceneInventory({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<Row[]>([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Row | null>(null)
  const [draft, setDraft] = useState<Row>({ ...defaultScene })
  const [corners, setCorners] = useState('null')
  const [trs, setTrs] = useState('null')
  const [translation, setTranslation] = useState('[0,0,0]')
  const [rotation, setRotation] = useState('[0,0,0]')
  const [meshScale, setMeshScale] = useState('[1,1,1]')
  const [mapFile, setMapFile] = useState<File | null>(null)
  const [polycamFile, setPolycamFile] = useState<File | null>(null)
  const [mappingVideo, setMappingVideo] = useState<File | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [mapping, setMapping] = useState<Row | null>(null)
  const [busy, setBusy] = useState(false)

  const load = () => void apiFetch<Row[]>('/api/v2/scenes').then(setRows).catch((e) => setError(String(e)))
  useEffect(load, [])
  const filtered = useMemo(() => rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase())), [rows, query])

  const open = (row: Row | null) => {
    const value = row ? { ...row } : { ...defaultScene }
    setSelected(row)
    setDraft(value)
    setCorners(jsonText(value.map_corners_lla, null))
    setTrs(jsonText(value.trs_matrix, null))
    setTranslation(jsonText(value.mesh_translation, [0,0,0]))
    setRotation(jsonText(value.mesh_rotation, [0,0,0]))
    setMeshScale(jsonText(value.mesh_scale, [1,1,1]))
    setMapFile(null)
    setPolycamFile(null)
    setMappingVideo(null)
    setMessage('')
    setError('')
    setMapping(null)
  }

  const field = (key: string, value: unknown) => setDraft((old) => ({ ...old, [key]: value }))

  const save = async () => {
    if (!isAdmin) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const body: Row = {
        name: String(draft.name || ''),
        map_type: String(draft.map_type || 'map_upload'),
        scale: draft.scale === null || draft.scale === '' ? null : Number(draft.scale),
        use_tracker: Boolean(draft.use_tracker),
        output_lla: Boolean(draft.output_lla),
        map_corners_lla: parseJson('Map corners LLA', corners, null),
        geospatial_provider: String(draft.geospatial_provider || 'google'),
        map_zoom: Number(draft.map_zoom ?? 15),
        map_center_lat: draft.map_center_lat === null || draft.map_center_lat === '' ? null : Number(draft.map_center_lat),
        map_center_lng: draft.map_center_lng === null || draft.map_center_lng === '' ? null : Number(draft.map_center_lng),
        map_bearing: Number(draft.map_bearing ?? 0),
        mesh_translation: parseJson('Mesh translation', translation, [0,0,0]),
        mesh_rotation: parseJson('Mesh rotation', rotation, [0,0,0]),
        mesh_scale: parseJson('Mesh scale', meshScale, [1,1,1]),
        trs_matrix: parseJson('TRS matrix', trs, null),
      }
      if (body.scale === null) delete body.scale
      if (body.map_center_lat === null) delete body.map_center_lat
      if (body.map_center_lng === null) delete body.map_center_lng
      if (body.trs_matrix === null) delete body.trs_matrix
      if (body.map_corners_lla === null) delete body.map_corners_lla

      let saved: Row
      if (selected) {
        saved = await apiFetch<Row>(`/api/v2/scenes/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`, {
          method: 'PUT',
          body: JSON.stringify(body),
        })
      } else {
        saved = await apiFetch<Row>('/api/v2/scenes', { method: 'POST', body: JSON.stringify(body) })
      }

      if (mapFile || polycamFile) {
        const form = new FormData()
        if (mapFile) form.append('map', mapFile)
        if (polycamFile) form.append('polycam_data', polycamFile)
        saved = await apiFetch<Row>(`/api/v2/scenes/${encodeURIComponent(idOf(saved))}/files`, { method: 'POST', body: form })
      }

      setSelected(saved)
      setDraft(saved)
      setCorners(jsonText(saved.map_corners_lla, null))
      setTrs(jsonText(saved.trs_matrix, null))
      setTranslation(jsonText(saved.mesh_translation, [0,0,0]))
      setRotation(jsonText(saved.mesh_rotation, [0,0,0]))
      setMeshScale(jsonText(saved.mesh_scale, [1,1,1]))
      setMapFile(null)
      setPolycamFile(null)
      setMessage('Scene saved.')
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!selected || !isAdmin || !window.confirm(`Delete ${nameOf(selected)} and its scene media?`)) return
    setBusy(true)
    try {
      await apiFetch(`/api/v2/scenes/${encodeURIComponent(idOf(selected))}`, { method: 'DELETE' })
      open(null)
      setSelected(null)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const clearMap = async () => {
    if (!selected || !isAdmin) return
    setBusy(true)
    try {
      const saved = await apiFetch<Row>(`/api/v2/scenes/${encodeURIComponent(idOf(selected))}?revision=${selected.revision}`, {
        method: 'PUT',
        body: JSON.stringify({ map: null }),
      })
      open(saved)
      setMessage('Scene map removed.')
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const importScene = async (file: File) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const form = new FormData()
      form.append('zipFile', file)
      await apiFetch('/api/v2/scenes/import', { method: 'POST', body: form })
      setMessage('Scene archive imported.')
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const exportScene = async () => {
    if (!selected) return
    try {
      const blob = await apiBlob(`/api/v2/scenes/${encodeURIComponent(idOf(selected))}/export`)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${nameOf(selected)}.zip`
      link.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(String(e))
    }
  }

  const checkMapping = async () => {
    try {
      setMapping(await apiFetch<Row>('/api/v2/mapping/health'))
    } catch (e) {
      setError(String(e))
    }
  }

  const generateMesh = async () => {
    if (!selected) return
    setBusy(true)
    setError('')
    setMessage('Starting Mapping Service reconstruction…')
    try {
      const form = new FormData()
      form.append('mesh_type', 'mesh')
      if (mappingVideo) form.append('map', mappingVideo)
      const start = await apiFetch<Row>(`/api/v2/scenes/${encodeURIComponent(idOf(selected))}/mesh`, { method: 'POST', body: form })
      const requestId = String(start.request_id)
      for (let attempt = 0; attempt < 150; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000))
        const status = await apiFetch<Row>(`/api/v2/scenes/${encodeURIComponent(idOf(selected))}/mesh/status?request_id=${encodeURIComponent(requestId)}`)
        setMapping(status)
        if (status.state === 'complete') {
          if (status.success === false || (!status.finalized && status.result?.success === false)) {
            throw new Error(String(status.error || status.result?.error || 'Mapping reconstruction failed'))
          }
          load()
          const refreshed = await apiFetch<Row>(`/api/v2/scenes/${encodeURIComponent(idOf(selected))}`)
          setSelected(refreshed)
          setDraft(refreshed)
          setTranslation(jsonText(refreshed.mesh_translation, [0,0,0]))
          setRotation(jsonText(refreshed.mesh_rotation, [0,0,0]))
          setMeshScale(jsonText(refreshed.mesh_scale, [1,1,1]))
          setMappingVideo(null)
          setMessage('Generated mesh finalized and scene/camera geometry refreshed.')
          return
        }
        if (status.state === 'failed' || status.success === false) {
          throw new Error(String(status.error || 'Mapping reconstruction failed'))
        }
        setMessage(`Mapping Service: ${status.state || 'processing'}…`)
      }
      throw new Error('Mapping reconstruction did not complete within the polling window.')
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return <>
    <div className="page-header"><div><div className="kicker">Configuration · control plane</div><h1>Sites, floors & scenes</h1></div>
      <div className="header-actions">
        {isAdmin && <label className="btn">Import ZIP<input className="hidden-file" type="file" accept=".zip" onChange={(e) => { const file=e.target.files?.[0]; if(file) void importScene(file); e.currentTarget.value='' }}/></label>}
        {isAdmin && <button className="btn btn-primary" onClick={() => open(null)}>New scene</button>}
      </div>
    </div>
    {message && <div className="notice-box">{message}</div>}
    {error && <div className="error-box">{error}</div>}
    <div className="config-grid scene-lifecycle-layout">
      <section className="panel">
        <div className="toolbar scene-toolbar"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search Sites, floors & scenes"/><span className="muted">{filtered.length} configured</span></div>
        <div className="scene-list">{filtered.map((row) => <button className={selected && idOf(selected)===idOf(row) ? 'scene-config-row active' : 'scene-config-row'} key={idOf(row)} onClick={() => open(row)}>
          <span><b>{nameOf(row)}</b><small>{idOf(row)}</small></span><span><small>{row.map ? 'Map configured' : 'No map'} · {row.map_type || 'map_upload'}</small></span>
        </button>)}{!filtered.length && <div className="table-empty">No matching resources</div>}</div>
      </section>
      <section className="panel scene-editor">
        <div className="panel-title"><div><h2>{selected ? `Edit ${nameOf(selected)}` : 'Create scene'}</h2><p>2026.2 scene lifecycle controls</p></div>{selected && <button className="btn" onClick={() => open(null)}>New</button>}</div>
        {!isAdmin && !selected ? <div className="table-empty">Administrator role required to create scenes.</div> : <>
          <div className="scene-form-grid">
            <label>Name<input value={String(draft.name ?? '')} onChange={(e)=>field('name',e.target.value)}/></label>
            <label>Map type<select value={String(draft.map_type || 'map_upload')} onChange={(e)=>field('map_type',e.target.value)}><option value="map_upload">Upload map</option><option value="geospatial_map">Geospatial map</option></select></label>
            <label>Scale (pixels/m)<input type="number" step="any" value={draft.scale ?? ''} onChange={(e)=>field('scale',numberOrNull(e.target.value))}/></label>
            <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.use_tracker)} onChange={(e)=>field('use_tracker',e.target.checked)}/>Use tracker</label>
            <label>Scene map<input type="file" accept=".png,.jpg,.jpeg,.glb,.ply,.zip" onChange={(e)=>setMapFile(e.target.files?.[0] || null)}/></label>
            <label>Polycam data<input type="file" accept=".zip" onChange={(e)=>setPolycamFile(e.target.files?.[0] || null)}/></label>
          </div>
          {draft.map_type === 'geospatial_map' && <div className="scene-subsection"><h3>Geospatial configuration</h3><div className="scene-form-grid">
            <label>Provider<select value={String(draft.geospatial_provider || 'google')} onChange={(e)=>field('geospatial_provider',e.target.value)}><option value="google">Google Maps</option><option value="mapbox">Mapbox</option></select></label>
            <label>Zoom<input type="number" step="any" value={draft.map_zoom ?? 15} onChange={(e)=>field('map_zoom',Number(e.target.value))}/></label>
            <label>Center latitude<input type="number" step="any" value={draft.map_center_lat ?? ''} onChange={(e)=>field('map_center_lat',numberOrNull(e.target.value))}/></label>
            <label>Center longitude<input type="number" step="any" value={draft.map_center_lng ?? ''} onChange={(e)=>field('map_center_lng',numberOrNull(e.target.value))}/></label>
            <label>Bearing<input type="number" step="any" value={draft.map_bearing ?? 0} onChange={(e)=>field('map_bearing',Number(e.target.value))}/></label>
            <label className="checkbox-label"><input type="checkbox" checked={Boolean(draft.output_lla)} onChange={(e)=>field('output_lla',e.target.checked)}/>Output LLA</label>
            <label className="wide">Map corners LLA<textarea value={corners} onChange={(e)=>setCorners(e.target.value)} placeholder="[[lat,lng,alt], ... four corners]"/></label>
          </div></div>}
          <div className="scene-subsection"><h3>Map transform</h3><div className="scene-form-grid">
            <label>Translation [x,y,z]<input value={translation} onChange={(e)=>setTranslation(e.target.value)}/></label>
            <label>Rotation° [x,y,z]<input value={rotation} onChange={(e)=>setRotation(e.target.value)}/></label>
            <label>Scale [x,y,z]<input value={meshScale} onChange={(e)=>setMeshScale(e.target.value)}/></label>
            <label className="wide">TRS → LLA matrix<textarea value={trs} onChange={(e)=>setTrs(e.target.value)} placeholder="4x4 JSON matrix or null"/></label>
          </div></div>
          {selected && <div className="scene-subsection"><h3>Current media</h3><div className="media-summary"><code>{String(selected.map || 'No map')}</code><code>{String(selected.thumbnail || 'No thumbnail')}</code></div></div>}
          <div className="editor-actions scene-editor-actions">
            {selected && <button className="btn" onClick={() => void exportScene()}>Export ZIP</button>}
            {selected && <button className="btn" onClick={() => void checkMapping()}>Mapping status</button>}
            {selected && <label className="btn">Optional mapping video<input className="hidden-file" type="file" accept=".mp4,.mov,.mkv,.webm,.avi" onChange={(e)=>setMappingVideo(e.target.files?.[0] || null)}/></label>}
            {selected && mappingVideo && <span className="muted">{mappingVideo.name}</span>}
            {selected && <button className="btn" disabled={busy} onClick={() => void generateMesh()}>Generate mesh</button>}
            {selected && selected.map && <button className="btn" disabled={busy} onClick={() => void clearMap()}>Remove map</button>}
            {selected && <button className="btn danger-button" disabled={busy} onClick={() => void remove()}>Delete</button>}
            {isAdmin && <button className="btn btn-primary" disabled={busy} onClick={() => void save()}>{busy ? 'Working…' : 'Save scene'}</button>}
          </div>
          {mapping && <pre className="mapping-status">{JSON.stringify(mapping, null, 2)}</pre>}
        </>}
      </section>
    </div>
  </>
}
