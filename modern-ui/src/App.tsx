import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { apiFetch, apiJsonStream, apiObjectUrl } from './api/client'
import { useAuth } from './auth/AuthProvider'
import ThreeScene from './native/ThreeScene'
import SceneInventory from './native/SceneInventory'
import CameraInventory from './native/CameraInventory'
import CameraCalibration from './native/CameraCalibration'
import SensorInventory from './native/SensorInventory'
import SpatialEditor from './native/SpatialEditor'
import AssetInventory from './native/AssetInventory'
import HierarchyEditor from './native/HierarchyEditor'
import SecurityAdmin from './native/SecurityAdmin'
import ModelLibrary from './native/ModelLibrary'
import {
  DEFAULT_SCENE_DESTINATION,
  PRIMARY_MODES,
  SECONDARY_VIEWS_BY_MODE,
  defaultDestinationForMode,
  destinationForLegacyTab,
  legacyTabForDestination,
  routeForDestination,
} from './ux/sceneWorkspaceContract'
import type { SceneDestination, ScenePrimaryMode } from './ux/sceneWorkspaceContract'

type Row = Record<string, any>
type Theme = 'light' | 'light-air' | 'dark' | 'dark-command'
type Overview = { generated_at: string; counts: Record<string, number>; health: Record<string, string | null> }
type Bundle = { scene: Row; cameras: Row[]; sensors: Row[]; regions: Row[]; tripwires: Row[]; children: Row[]; markers: Row[]; child_regions?: Row[]; child_tripwires?: Row[]; child_sensors?: Row[] }

const operations = [
  ['overview', 'Shift overview'], ['live', 'Live scenes'], ['incidents', 'Incidents'],
  ['history', 'History & replay'], ['trends', 'Trends & analytics'], ['health', 'Feed & service health'],
] as const
const configuration = [
  ['scenes', 'Sites, floors & scenes'], ['cameras', 'Cameras'], ['sensors', 'Sensors'], ['zones', 'Zones & tripwires'],
  ['assets', 'Object library'], ['models', 'Model library'], ['hierarchy', 'Scene hierarchy'],
] as const
const themes: Array<{ value: Theme; label: string }> = [
  { value: 'light', label: 'Light' }, { value: 'light-air', label: 'Light Air' },
  { value: 'dark', label: 'Dark' }, { value: 'dark-command', label: 'Dark Command' },
]

const route = () => window.location.hash.replace(/^#\/?/, '') || 'overview'
const go = (value: string) => { window.location.hash = `#/${value}` }
const rowId = (row: Row) => String(row.uid ?? row.id ?? row.uuid ?? row.sensor_id ?? '')
const rowName = (row: Row) => String(row.name ?? row.title ?? row.sensor_id ?? row.uid ?? row.id ?? 'Unnamed')
const text = (value: unknown) => value === null || value === undefined || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)
const initialTheme = (): Theme => {
  const saved = localStorage.getItem('scenescape-theme')
  if (themes.some((theme) => theme.value === saved)) return saved as Theme
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
const editablePayload = (row: Row) => {
  const copy = { ...row }
  delete copy.kind
  delete copy.revision
  return copy
}

const isImageMediaPath = (value: string) => /\.(?:png|jpe?g|webp)(?:$|\?)/i.test(value)
const scene2DMapCandidates = (scene: Row) => {
  const map = String(scene.map || '')
  const thumbnail = String(scene.thumbnail || '')
  const preferred = isImageMediaPath(map) ? [map, thumbnail] : [thumbnail]
  return preferred.filter((value, index, values) => value.startsWith('/media/') && values.indexOf(value) === index)
}

function Header({ title, kicker, children }: { title: string; kicker: string; children?: ReactNode }) {
  return <div className="page-header"><div><div className="kicker">{kicker}</div><h1>{title}</h1></div><div className="header-actions">{children}</div></div>
}

function Map2D({ bundle, live, onPoint, showTrails = false, showTelemetry = false, showHeatmap = false, showVelocity = false, visualizeRois = true, trails = {} }: { bundle: Bundle; live: Row; onPoint?: (point: number[]) => void; showTrails?: boolean; showTelemetry?: boolean; showHeatmap?: boolean; showVelocity?: boolean; visualizeRois?: boolean; trails?: Record<string, number[][]> }) {
  const scene = bundle.scene
  const [mapUrl, setMapUrl] = useState('')
  const [size, setSize] = useState<[number, number]>([1000, 700])
  const mapCandidates = scene2DMapCandidates(scene)
  const mapKey = mapCandidates.join('\n')
  const scale = Math.max(1, Number(scene.scale || 100))

  useEffect(() => {
    let alive = true
    let url = ''
    setMapUrl('')

    const load = async () => {
      for (const path of mapCandidates) {
        try {
          const value = await apiObjectUrl(path)
          if (!alive) { URL.revokeObjectURL(value); return }
          const image = new Image()
          const loaded = await new Promise<boolean>((resolve) => {
            image.onload = () => resolve(true)
            image.onerror = () => resolve(false)
            image.src = value
          })
          if (!alive) { URL.revokeObjectURL(value); return }
          if (!loaded) { URL.revokeObjectURL(value); continue }
          url = value
          setSize([Math.max(1, image.naturalWidth), Math.max(1, image.naturalHeight)])
          setMapUrl(value)
          return
        } catch {
          // Try the next renderable scene-media candidate.
        }
      }
    }

    void load()
    return () => { alive = false; if (url) URL.revokeObjectURL(url) }
  }, [mapKey])

  const xy = (point: any): [number, number] => {
    const x = Number(point?.[0] || 0) * scale
    const y = size[1] - Number(point?.[1] || 0) * scale
    return [x, y]
  }
  const points = (rows: Row[]) => rows.map((row) => (row.points || []).map((p: any) => xy(p).join(',')).join(' '))
  const regionPoints = points(bundle.regions)
  const tripPoints = points(bundle.tripwires)
  const childRegions = bundle.child_regions || []
  const childTripwires = bundle.child_tripwires || []
  const childSensors = bundle.child_sensors || []
  const childRegionPoints = points(childRegions)
  const childTripPoints = points(childTripwires)

  return <div className="map-frame">
    <svg className="native-map" viewBox={`0 0 ${size[0]} ${size[1]}`} onClick={(event) => {
      if (!onPoint) return
      const rect = event.currentTarget.getBoundingClientRect()
      const px = ((event.clientX - rect.left) / rect.width) * size[0]
      const py = ((event.clientY - rect.top) / rect.height) * size[1]
      onPoint([px / scale, (size[1] - py) / scale])
    }}>
      <defs>
        <marker id="velocity-arrow-head" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L8,4 L0,8 z" className="velocity-arrow-head"/>
        </marker>
      </defs>
      {mapUrl && <image href={mapUrl} x="0" y="0" width={size[0]} height={size[1]} preserveAspectRatio="none" />}
      {visualizeRois && bundle.regions.map((row, i) => row.visible && regionPoints[i] && <polygon key={rowId(row) || i} points={regionPoints[i]} className="region-shape" />)}
      {visualizeRois && childRegions.map((row, i) => childRegionPoints[i] && <polygon key={`child-region-${rowId(row)||i}`} points={childRegionPoints[i]} className="child-region-shape" />)}
      {bundle.tripwires.map((row, i) => row.visible && tripPoints[i] && <polyline key={rowId(row) || i} points={tripPoints[i]} className="tripwire-line" />)}
      {childTripwires.map((row, i) => childTripPoints[i] && <polyline key={`child-trip-${rowId(row)||i}`} points={childTripPoints[i]} className="child-tripwire-line" />)}
      {bundle.cameras.map((camera, i) => {
        const [x, y] = xy(camera.translation || [i + 1, i + 1])
        return <g key={rowId(camera) || i}><circle cx={x} cy={y} r="8" className="camera-dot"/><text x={x + 11} y={y - 7} className="map-label">{rowName(camera)}</text></g>
      })}
      {childSensors.map((sensor, i) => {
        if (sensor.area === 'scene') return null
        const center = Array.isArray(sensor.center)
          ? sensor.center
          : Array.isArray(sensor.translation) && sensor.translation[0] != null
            ? sensor.translation.slice(0, 2)
            : sensor.x != null && sensor.y != null ? [sensor.x, sensor.y] : null
        const polygon = Array.isArray(sensor.points) ? sensor.points.map((point: any) => xy(point).join(',')).join(' ') : ''
        const position = center ? xy(center) : (sensor.x != null && sensor.y != null ? xy([sensor.x,sensor.y]) : null)
        return <g key={`child-sensor-${rowId(sensor)||i}`}>
          {sensor.area === 'poly' && polygon && <polygon points={polygon} className="child-sensor-area"/>}
          {sensor.area === 'circle' && position && <circle cx={position[0]} cy={position[1]} r={Math.max(1, Number(sensor.radius || 0) * scale)} className="child-sensor-area"/>}
          {position && <><circle cx={position[0]} cy={position[1]} r="7" className="child-sensor-dot"/><text x={position[0] + 10} y={position[1] - 7} className="map-label">{rowName(sensor)} · {String(sensor.from_child_scene||'child')}</text></>}
        </g>
      })}
      {bundle.sensors.filter((sensor) => Boolean(sensor.visible)).map((sensor, i) => {
        const center = Array.isArray(sensor.center)
          ? sensor.center
          : Array.isArray(sensor.translation) && sensor.translation[0] != null
            ? sensor.translation.slice(0, 2)
            : null
        const polygon = Array.isArray(sensor.points) ? sensor.points.map((point: any) => xy(point).join(',')).join(' ') : ''
        const position = center ? xy(center) : null
        return <g key={rowId(sensor) || i}>
          {sensor.area === 'scene' && <rect x="2" y="2" width={Math.max(0,size[0]-4)} height={Math.max(0,size[1]-4)} className="sensor-scene-area"/>}
          {sensor.area === 'poly' && polygon && <polygon points={polygon} className="sensor-poly-area"/>}
          {sensor.area === 'circle' && position && <circle cx={position[0]} cy={position[1]} r={Math.max(1, Number(sensor.radius || 0) * scale)} className="sensor-circle-area"/>}
          {position && <><circle cx={position[0]} cy={position[1]} r="8" className="sensor-center-dot"/><text x={position[0] + 11} y={position[1] - 7} className="map-label">{rowName(sensor)}</text></>}
        </g>
      })}
      {showTrails && Object.entries(trails).map(([key, trail]) => {
        const value = trail.map((point) => xy(point).join(',')).join(' ')
        return value ? <polyline key={`trail-${key}`} points={value} className="object-trail"/> : null
      })}
      {(live.objects || []).map((object: Row, i: number) => {
        const [x, y] = xy(object.translation || [i + 1, i + 1])
        const label = String(object.category || object.type || object.id || 'object')
        const activeDwells = object.regions && typeof object.regions === 'object'
          ? Object.values(object.regions as Row).filter((value:any)=>value?.entered && value?.dwell != null).map((value:any)=>Number(value.dwell))
          : []
        const dwell = activeDwells.length ? Math.max(...activeDwells) : null
        const velocity = Array.isArray(object.velocity) && object.velocity.length >= 2
          ? [Number(object.velocity[0] || 0), Number(object.velocity[1] || 0)]
          : null
        const magnitude = velocity ? Math.hypot(velocity[0], velocity[1]) : 0
        const velocityLength = Math.min(2.5, Math.max(0.4, magnitude)) * scale
        const velocityEnd = velocity && magnitude > 0.001
          ? [x + (velocity[0] / magnitude) * velocityLength, y - (velocity[1] / magnitude) * velocityLength]
          : null
        const persistent = object.persistent_data && typeof object.persistent_data === 'object'
          ? Object.entries(object.persistent_data as Row).flatMap(([key,value]) =>
              value && typeof value === 'object'
                ? Object.entries(value as Row).map(([nested,nestedValue])=>`${key}.${nested}=${String(nestedValue)}`)
                : [`${key}=${String(value)}`]
            ).slice(0,3)
          : []
        const telemetry = showTelemetry ? [
          object.id != null ? `#${object.id}` : '',
          velocity ? `v ${velocity.map((v)=>v.toFixed(2)).join(',')}` : '',
          dwell != null && Number.isFinite(dwell) ? `dwell ${dwell.toFixed(1)}s` : '',
          ...persistent,
        ].filter(Boolean) : []
        const heatRadius = Math.max(14, Math.min(90, Number(object.tracking_radius || 0.6) * scale))
        return <g key={String(object.id ?? i)}>
          {showHeatmap && <circle cx={x} cy={y} r={heatRadius} className="object-heatmap"/>}
          {showHeatmap && <circle cx={x} cy={y} r={Math.max(8,heatRadius*0.45)} className="object-heatmap-core"/>}
          {showVelocity && velocityEnd && <line x1={x} y1={y} x2={velocityEnd[0]} y2={velocityEnd[1]} className="object-velocity" markerEnd="url(#velocity-arrow-head)"/>}
          <circle cx={x} cy={y} r="7" className="track-dot"/>
          <text x={x + 10} y={y + 4} className="map-label">{label}</text>
          {telemetry.map((line,index)=><text key={line+index} x={x + 10} y={y + 18 + index*12} className="map-telemetry">{line}</text>)}
        </g>
      })}
    </svg>
    {showTelemetry && <div className="scene-telemetry-hud">
      <b>Live telemetry</b>
      <span>Scene {Number(live.scene_rate || 0).toFixed(1)} Hz</span>
      <span>{(live.objects || []).length} objects</span>
      {live.rate && typeof live.rate === 'object'
        ? Object.entries(live.rate as Row).map(([camera,value])=><span key={camera}>{camera}: {Number(value || 0).toFixed(1)} FPS</span>)
        : <span>No per-camera rate in current feed</span>}
    </div>}
    {(showHeatmap || showVelocity) && <div className="visualization-status">
      {showHeatmap && <span>Heatmap: {(live.objects || []).length} tracked positions</span>}
      {showVelocity && <span>Velocity: {(live.objects || []).filter((object:Row)=>Array.isArray(object.velocity)&&object.velocity.length>=2).length}/{(live.objects || []).length} vectors</span>}
    </div>}
    {!mapUrl && <div className="map-watermark">No renderable 2D scene map is available; geometry and live coordinates are still shown.</div>}
  </div>
}



function SceneSensorTelemetry({ sensors }: { sensors: Row[] }) {
  const [telemetry, setTelemetry] = useState<Record<string, Row[]>>({})
  const [error, setError] = useState('')
  const load = async () => {
    setError('')
    const result: Record<string, Row[]> = {}
    await Promise.all(sensors.map(async (sensor) => {
      const id = rowId(sensor)
      if (!id) return
      try { result[id] = await apiFetch<Row[]>(`/api/v2/sensors/${encodeURIComponent(id)}/telemetry?limit=12`) }
      catch { result[id] = [] }
    }))
    setTelemetry(result)
  }
  useEffect(() => { void load() }, [sensors.map(rowId).join('|')])
  if (!sensors.length) return <div className="empty-state"><h2>No sensors configured</h2><p>This scene has no singleton sensors.</p></div>
  return <section className="panel">
    <div className="panel-title"><div><h2>Sensors & telemetry</h2><p>Latest retained native sensor observations for this scene.</p></div><button className="btn" onClick={()=>void load()}>Refresh</button></div>
    {error&&<div className="error-box">{error}</div>}
    <div className="sensor-runtime-grid">{sensors.map((sensor)=>{
      const id=rowId(sensor); const rows=telemetry[id]||[]; const latest=rows[0]
      return <div className="sensor-runtime-card" key={id}>
        <div><b>{rowName(sensor)}</b><code>{id}</code></div>
        <span className={latest?'status-pill ok-pill':'status-pill warning-pill'}>{latest?'Telemetry retained':'No telemetry'}</span>
        <dl><dt>Area</dt><dd>{String(sensor.area||'scene')}</dd><dt>Type</dt><dd>{String(sensor.singleton_type||'environmental')}</dd><dt>Latest</dt><dd>{latest ? String(latest.timestamp || '—') : '—'}</dd></dl>
        <div className="sensor-runtime-values">{rows.slice(0,5).map((row,i)=><div key={String(row.id??i)}><b>{String(row.payload?.subtype || row.payload?.type || 'value')}</b><span>{text(row.payload?.value ?? row.payload)}</span></div>)}{!rows.length&&<div className="table-empty">No retained values.</div>}</div>
      </div>
    })}</div>
  </section>
}

function SceneRuntime({ live, bundle, overview }: { live: Row; bundle: Bundle; overview?: Row | null }) {
  const observed = live.observed_at ? new Date(String(live.observed_at)) : null
  const age = observed ? Math.max(0,(Date.now()-observed.getTime())/1000) : null
  return <div className="metric-grid compact">
    <div className="metric"><span>Tracking feed</span><strong className={live.stale?'small-value':'small-value ok'}>{live.stale?'Stale / unavailable':'Live'}</strong><small>{age==null?'No observation retained':`last sample ${age.toFixed(1)}s ago`}</small></div>
    <div className="metric"><span>Scene rate</span><strong>{Number(live.scene_rate||0).toFixed(1)}</strong><small>Hz reported by regulated scene feed</small></div>
    <div className="metric"><span>Tracked objects</span><strong>{(live.objects||[]).length}</strong><small>Current retained observation</small></div>
    <div className="metric"><span>Configured inputs</span><strong>{bundle.cameras.length + bundle.sensors.length}</strong><small>{bundle.cameras.length} cameras · {bundle.sensors.length} sensors</small></div>
    <div className="metric"><span>MQTT ingestion</span><strong className="small-value">{String(overview?.health?.mqtt || 'unknown')}</strong><small>Server-side broker heartbeat</small></div>
  </div>
}

function CameraFeed({ camera, showTelemetry = false }: { camera: Row; showTelemetry?: boolean }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [telemetry, setTelemetry] = useState<Row | null>(null)
  const cameraId = rowId(camera)

  useEffect(() => {
    let active = true
    let currentUrl = ''
    let inFlight = false
    const refresh = async () => {
      if (!active || inFlight) return
      inFlight = true
      try {
        const next = await apiObjectUrl(`/api/v2/cameras/${encodeURIComponent(cameraId)}/snapshot?t=${Date.now()}`)
        if (!active) { URL.revokeObjectURL(next); return }
        if (currentUrl) URL.revokeObjectURL(currentUrl)
        currentUrl = next
        setUrl(next)
        setError('')
      } catch (e) {
        if (active) setError(String(e))
      } finally {
        inFlight = false
      }
    }
    void refresh()
    const timer = window.setInterval(refresh, 900)
    return () => {
      active = false
      window.clearInterval(timer)
      if (currentUrl) URL.revokeObjectURL(currentUrl)
    }
  }, [cameraId])

  useEffect(() => {
    if (!showTelemetry) { setTelemetry(null); return }
    let active = true
    const refresh = () => void apiFetch<Row>(`/api/v2/cameras/${encodeURIComponent(cameraId)}/telemetry`).then((value)=>active&&setTelemetry(value)).catch(()=>{})
    refresh()
    const timer = window.setInterval(refresh, 1500)
    return () => { active=false; window.clearInterval(timer) }
  }, [cameraId, showTelemetry])

  return <section className="panel camera-feed-card">
    <div className="panel-title"><div><h2>{rowName(camera)}</h2><p>{cameraId}</p></div><span className={error ? 'status-pill warning-pill' : 'status-pill ok-pill'}>{error ? 'Unavailable' : 'Live JPEG'}</span></div>
    <div className="camera-feed-frame">{url ? <img src={url} alt={`${rowName(camera)} live view`} /> : <div className="camera-feed-placeholder">Waiting for camera image…</div>}</div>
    {showTelemetry && <div className="camera-telemetry-strip"><span><b>{telemetry ? Number(telemetry.fps||0).toFixed(1) : '—'}</b> FPS</span><span><b>{telemetry ? Number(telemetry.detections||0) : '—'}</b> detections</span><span className={telemetry?.stale?'warning-text':'ok-text'}>{telemetry ? (telemetry.stale?'stale':'receiving') : 'waiting'}</span></div>}
    {error && <div className="camera-feed-error">{error}</div>}
  </section>
}

function CameraFeeds({ cameras, showTelemetry = false }: { cameras: Row[]; showTelemetry?: boolean }) {
  if (!cameras.length) return <div className="empty-state"><h2>No cameras configured</h2><p>This scene has no migrated camera resources.</p></div>
  return <div className="camera-feed-grid">{cameras.map((camera) => <CameraFeed key={rowId(camera)} camera={camera} showTelemetry={showTelemetry}/>)}</div>
}

function SceneWorkspace({ scene, scenes, onBack, onNavigate, isAdmin, initialTab = 'Live 2D' }: { scene: Row; scenes: Row[]; onBack: () => void; onNavigate: (path: string) => void; isAdmin: boolean; initialTab?: string }) {
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [live, setLive] = useState<Row>({ objects: [], stale: true })
  const [destination, setDestination] = useState<SceneDestination>(() => destinationForLegacyTab(initialTab) ?? DEFAULT_SCENE_DESTINATION)
  const [history, setHistory] = useState<Row[]>([])
  const [trends, setTrends] = useState<Row[]>([])
  const [message, setMessage] = useState('')
  const [liveView, setLiveView] = useState(true)
  const [showTrails, setShowTrails] = useState(false)
  const [showTelemetry, setShowTelemetry] = useState(false)
  const [showHeatmap, setShowHeatmap] = useState(false)
  const [showVelocity, setShowVelocity] = useState(false)
  const [visualizeRois, setVisualizeRois] = useState(true)
  const [showFloor, setShowFloor] = useState(() => localStorage.getItem('showFloor') !== 'false')
  const [trails, setTrails] = useState<Record<string, number[][]>>({})
  const [projectCameraFrames, setProjectCameraFrames] = useState(false)
  const [cameraOpacity, setCameraOpacity] = useState(0.8)
  const [selectedCameraId, setSelectedCameraId] = useState('')
  const [cameraView, setCameraView] = useState(false)
  const [lightIntensity, setLightIntensity] = useState(1)
  const [runtimeOverview, setRuntimeOverview] = useState<Row | null>(null)
  const visualRef = useRef<HTMLDivElement | null>(null)
  const id = rowId(scene)
  const tab = legacyTabForDestination(destination) ?? 'Live 2D'
  const selectMode = (mode: ScenePrimaryMode) => setDestination(defaultDestinationForMode(mode))
  const selectView = (view: string) => {
    const next: SceneDestination = { mode: destination.mode, view }
    const target = routeForDestination(next)
    if (target) {
      onNavigate(target)
      return
    }
    setDestination(next)
  }

  useEffect(() => {
    setDestination(destinationForLegacyTab(initialTab) ?? DEFAULT_SCENE_DESTINATION)
  }, [id, initialTab])

  const loadBundle = () => void apiFetch<Bundle>(`/api/v2/scenes/${id}/bundle`).then(setBundle).catch((e) => setMessage(String(e)))

  useEffect(() => {
    loadBundle()
    let active = true
    let fallbackTimer = 0
    const controller = new AbortController()
    const refresh = () => void apiFetch<Row>(`/api/v2/scenes/${id}/live`).then((value) => active && setLive(value)).catch(() => {})
    refresh()
    const acceptLive = (value: Row) => {
      if (!active) return
      setLive(value)
      setTrails((old) => {
        const next = { ...old }
        for (const [index, object] of (value.objects || []).entries()) {
          const key = String(object.id ?? index)
          const point = Array.isArray(object.translation) ? object.translation.slice(0, 2).map(Number) : null
          if (!point) continue
          next[key] = [...(next[key] || []), point].slice(-40)
        }
        return next
      })
    }
    void apiJsonStream<Row>(`/api/v2/scenes/${id}/live/stream`, acceptLive, controller.signal).catch(() => {
      if (active && !controller.signal.aborted) fallbackTimer = window.setInterval(refresh, 500)
    })
    return () => { active = false; controller.abort(); if (fallbackTimer) window.clearInterval(fallbackTimer) }
  }, [id])

  if (!bundle) return <><button className="btn" onClick={onBack}>← Back to scenes</button><div className="center-panel">Loading native scene workspace…{message && <div className="error-box">{message}</div>}</div></>
  const map3DPath = String(bundle.scene.map || bundle.scene.thumbnail || '')

  return <>
    <Header kicker="Operations · native scene workspace" title={rowName(bundle.scene)}>
      <button className="btn" onClick={onBack}>← All scenes</button>
      <span className={live.stale ? 'status-pill warning-pill' : 'status-pill ok-pill'}>{live.stale ? 'No live feed' : `${(live.objects || []).length} live objects · ${Number(live.scene_rate || 0).toFixed(1)} Hz`}</span>
    </Header>
    <div className="scene-summary">
      <div><span>Scene ID</span><b>{id}</b></div><div><span>Cameras</span><b>{bundle.cameras.length}</b></div><div><span>Sensors</span><b>{bundle.sensors.length}</b></div><div><span>Spatial rules</span><b>{bundle.regions.length + bundle.tripwires.length + (bundle.child_regions?.length||0) + (bundle.child_tripwires?.length||0)}</b></div>
    </div>
    <nav className="scene-primary-nav" aria-label="Scene workspace modes">
      {PRIMARY_MODES.map((mode) => <button key={mode} className={destination.mode === mode ? 'scene-primary-nav-item active' : 'scene-primary-nav-item'} onClick={() => selectMode(mode)} aria-current={destination.mode === mode ? 'page' : undefined}>{mode}</button>)}
    </nav>
    <nav className="scene-secondary-nav" aria-label={`${destination.mode} views`}>
      {SECONDARY_VIEWS_BY_MODE[destination.mode].map((view) => {
        const next: SceneDestination = { mode: destination.mode, view }
        const routesAway = Boolean(routeForDestination(next))
        return <button key={view} className={destination.view === view ? 'scene-secondary-nav-item active' : 'scene-secondary-nav-item'} onClick={() => selectView(view)} aria-current={destination.view === view ? 'page' : undefined}>{view}{routesAway && <span className="scene-nav-route-mark" aria-hidden="true">↗</span>}</button>
      })}
    </nav>
    {message && <div className="notice-box">{message}</div>}
    {(tab === 'Live 2D' || tab === 'Live 3D') && <div className="live-controls">
      <label><input type="checkbox" checked={liveView} onChange={(e)=>setLiveView(e.target.checked)}/>Live View</label>
      <label><input type="checkbox" checked={showTrails} onChange={(e)=>setShowTrails(e.target.checked)}/>Show Trails</label>
      <label><input type="checkbox" checked={showTelemetry} onChange={(e)=>setShowTelemetry(e.target.checked)}/>Show Telemetry</label>
      <label><input type="checkbox" checked={showHeatmap} onChange={(e)=>setShowHeatmap(e.target.checked)}/>Show Heatmap</label>
      <label><input type="checkbox" checked={showVelocity} onChange={(e)=>setShowVelocity(e.target.checked)}/>Show Velocity</label>
      <label><input type="checkbox" checked={visualizeRois} onChange={(e)=>setVisualizeRois(e.target.checked)}/>Visualize ROIs</label>
      {tab === 'Live 3D' && <label><input type="checkbox" checked={showFloor} onChange={(e)=>{setShowFloor(e.target.checked);localStorage.setItem('showFloor',String(e.target.checked))}}/>Floor Plane</label>}
      {tab === 'Live 3D' && <label><input type="checkbox" checked={projectCameraFrames} onChange={(e)=>setProjectCameraFrames(e.target.checked)}/>Project camera frames</label>}
      {tab === 'Live 3D' && <label className="range-control">Camera opacity <input type="range" min="0" max="100" value={Math.round(cameraOpacity*100)} onChange={(e)=>setCameraOpacity(Number(e.target.value)/100)}/><span>{Math.round(cameraOpacity*100)}%</span></label>}
      {tab === 'Live 3D' && <label className="range-control">Light <input type="range" min="10" max="300" value={Math.round(lightIntensity*100)} onChange={(e)=>setLightIntensity(Number(e.target.value)/100)}/><span>{lightIntensity.toFixed(1)}×</span></label>}
      {tab === 'Live 3D' && bundle.cameras.length > 0 && <><label>Camera <select value={selectedCameraId} onChange={(e)=>{setSelectedCameraId(e.target.value);if(!e.target.value)setCameraView(false)}}><option value="">None</option>{bundle.cameras.map((camera)=><option key={rowId(camera)} value={rowId(camera)}>{rowName(camera)}</option>)}</select></label><label><input type="checkbox" disabled={!selectedCameraId} checked={cameraView} onChange={(e)=>setCameraView(e.target.checked)}/>Scene camera view</label></>}
      {showTrails && <button className="text-button" onClick={()=>setTrails({})}>Clear trails</button>}
      <button className="text-button" onClick={()=>{const el=visualRef.current;if(!el)return;if(document.fullscreenElement)void document.exitFullscreen();else void el.requestFullscreen()}}>Fullscreen</button>
    </div>}
    <div ref={visualRef} className={(tab === 'Live 2D' || tab === 'Live 3D') ? 'scene-workspace-visual' : ''}>
    {tab === 'Live 2D' && <Map2D bundle={bundle} live={liveView ? live : { objects: [], stale: true }} showTrails={showTrails} showTelemetry={showTelemetry} showHeatmap={showHeatmap} showVelocity={showVelocity} visualizeRois={visualizeRois} trails={trails}/>} 
    {tab === 'Live 3D' && <><ThreeScene mapPath={map3DPath} objects={liveView ? (live.objects || []) : []} showTrackedObjects={liveView} showSpatial={visualizeRois} showFloor={showFloor} showHeatmap={showHeatmap} showVelocity={showVelocity} cameras={bundle.cameras} projectCameraFrames={projectCameraFrames} cameraOpacity={cameraOpacity} selectedCameraId={selectedCameraId} useSelectedCameraView={cameraView} lightIntensity={lightIntensity} scale={Number(bundle.scene.scale || 100)} meshTranslation={bundle.scene.mesh_translation} meshRotation={bundle.scene.mesh_rotation} meshScale={bundle.scene.mesh_scale} regions={bundle.regions} tripwires={bundle.tripwires} sensors={bundle.sensors} childRegions={bundle.child_regions||[]} childTripwires={bundle.child_tripwires||[]} childSensors={bundle.child_sensors||[]}/>
      {showTelemetry && <div className="scene-telemetry-hud three-telemetry-hud">
        <b>Live telemetry</b>
        <span>Scene {Number(live.scene_rate || 0).toFixed(1)} Hz</span>
        <span>{(live.objects || []).length} objects</span>
        {live.rate && typeof live.rate === 'object'
          ? Object.entries(live.rate as Row).map(([camera,value])=><span key={camera}>{camera}: {Number(value || 0).toFixed(1)} FPS</span>)
          : <span>No per-camera rate in current feed</span>}
      </div>}
      {(showHeatmap || showVelocity) && <div className="visualization-status three-visualization-status">
        {showHeatmap && <span>Heatmap: {(live.objects || []).length} tracked positions</span>}
        {showVelocity && <span>Velocity: {(live.objects || []).filter((object:Row)=>Array.isArray(object.velocity)&&object.velocity.length>=2).length}/{(live.objects || []).length} vectors</span>}
      </div>}
    </>} 
    </div>
    {tab === 'Camera feeds' && <><div className="live-controls camera-feed-controls"><label><input type="checkbox" checked={showTelemetry} onChange={(e)=>setShowTelemetry(e.target.checked)}/>Show Telemetry</label></div><CameraFeeds cameras={bundle.cameras} showTelemetry={showTelemetry}/></>} 
    {tab === 'Sensors & telemetry' && <SceneSensorTelemetry sensors={bundle.sensors}/>}
    {tab === 'Geometry' && <SpatialEditor scene={bundle.scene} regions={bundle.regions} tripwires={bundle.tripwires} isAdmin={isAdmin} onSaved={loadBundle}/>}
    {tab === 'Hierarchy' && <HierarchyEditor scenes={scenes} isAdmin={isAdmin} initialParent={id}/>}
    {tab === 'Camera calibration' && <CameraCalibration scene={bundle.scene} cameras={bundle.cameras} isAdmin={isAdmin} onSaved={loadBundle}/>}
    {tab === 'Runtime' && <><div className="header-actions runtime-refresh"><button className="btn" onClick={()=>void apiFetch<Row>('/api/v2/overview').then(setRuntimeOverview)}>Refresh runtime</button></div><SceneRuntime live={live} bundle={bundle} overview={runtimeOverview}/></>}
    {tab === 'History & replay' && <section className="panel history-panel"><div className="panel-title"><div><h2>Persisted observations</h2><p>Metadata replay from the native historian.</p></div><button className="btn btn-primary" onClick={() => void apiFetch<Row[]>(`/api/v2/scenes/${id}/history`).then(setHistory)}>Load history</button></div>{history.length > 0 ? <><input type="range" min="0" max={history.length - 1}/><div className="history-list">{history.slice(-12).map((row) => <div key={row.id}><b>{row.timestamp}</b><span>{(row.payload?.objects || []).length} objects</span></div>)}</div></> : <div className="table-empty">No retained samples loaded yet.</div>}</section>}
    {tab === 'Trends & analytics' && <section className="panel"><div className="panel-title"><div><h2>24-hour object trend</h2><p>Calculated from retained observations, not synthetic data.</p></div><button className="btn btn-primary" onClick={() => void apiFetch<Row[]>(`/api/v2/scenes/${id}/trends`).then(setTrends)}>Apply range</button></div><div className="table-wrap"><table><thead><tr><th>Hour</th><th>Average objects</th><th>Samples</th></tr></thead><tbody>{trends.map((row) => <tr key={row.bucket}><td>{row.bucket}</td><td>{row.average_objects}</td><td>{row.samples}</td></tr>)}</tbody></table>{!trends.length && <div className="table-empty">No trend samples loaded yet.</div>}</div></section>}
  </>
}

function Inventory({ kind, label, isAdmin }: { kind: 'scenes'|'cameras'|'sensors'|'regions'|'tripwires'; label: string; isAdmin: boolean }) {
  const [rows, setRows] = useState<Row[]>([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Row | null>(null)
  const [editor, setEditor] = useState('{}')
  const [error, setError] = useState('')
  const load = () => void apiFetch<Row[]>(`/api/v2/${kind}`).then(setRows).catch((e) => setError(String(e)))
  useEffect(load, [kind])
  const filtered = useMemo(() => rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase())), [rows, query])
  const open = (row: Row | null) => { setSelected(row); setEditor(JSON.stringify(row ? editablePayload(row) : { name: '', ...(kind !== 'scenes' ? { scene: '' } : {}) }, null, 2)); setError('') }
  const save = async () => {
    try {
      const body = JSON.parse(editor)
      if (selected) await apiFetch(`/api/v2/${kind}/${rowId(selected)}?revision=${selected.revision}`, { method: 'PUT', body: JSON.stringify(body) })
      else await apiFetch(`/api/v2/${kind}`, { method: 'POST', body: JSON.stringify(body) })
      open(null); setSelected(null); load()
    } catch (e) { setError(String(e)) }
  }
  const remove = async () => {
    if (!selected || !window.confirm(`Delete ${rowName(selected)} from native configuration?`)) return
    try { await apiFetch(`/api/v2/${kind}/${rowId(selected)}`, { method: 'DELETE' }); setSelected(null); load() } catch (e) { setError(String(e)) }
  }
  return <>
    <Header kicker="Configuration · control plane" title={label}>{isAdmin && <button className="btn btn-primary" onClick={() => open(null)}>Add native resource</button>}</Header>
    <div className="toolbar"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Search ${label}`} /><span className="muted">{filtered.length} configured</span></div>
    {error && <div className="error-box">{error}</div>}
    <div className="config-grid"><section className="panel table-wrap"><table><thead><tr><th>Name</th><th>Identifier</th><th>Scene / context</th><th></th></tr></thead><tbody>{filtered.map((row) => <tr key={rowId(row) || rowName(row)}><td><b>{rowName(row)}</b></td><td><code>{rowId(row) || '—'}</code></td><td>{text(row.scene ?? row.scene_id ?? row.parent)}</td><td>{kind === 'scenes' ? <button className="text-button" onClick={() => go(`scene/${rowId(row)}`)}>Open</button> : isAdmin ? <button className="text-button" onClick={() => open(row)}>Edit</button> : null}</td></tr>)}</tbody></table>{!filtered.length && <div className="table-empty">No matching resources</div>}</section>{isAdmin && (selected || editor !== '{}') && <section className="panel editor-panel"><div className="panel-title"><div><h2>{selected ? `Edit ${rowName(selected)}` : `New ${label}`}</h2><p>Native JSON editor with revision protection.</p></div></div><textarea value={editor} onChange={(e) => setEditor(e.target.value)} /><div className="editor-actions"><button className="btn" onClick={() => { setSelected(null); setEditor('{}') }}>Close</button>{selected && <button className="btn danger-button" onClick={() => void remove()}>Delete</button>}<button className="btn btn-primary" onClick={() => void save()}>Save</button></div></section>}</div>
  </>
}

function Zones({ goTo }: { goTo: (path: string) => void }) {
  const [regions, setRegions] = useState<Row[]>([])
  const [tripwires, setTripwires] = useState<Row[]>([])
  useEffect(() => { void apiFetch<Row[]>('/api/v2/regions').then(setRegions); void apiFetch<Row[]>('/api/v2/tripwires').then(setTripwires) }, [])
  const rows: Array<Row & { _kind: 'Region' | 'Tripwire' }> = [
    ...regions.map((row) => ({ ...row, _kind: 'Region' as const })),
    ...tripwires.map((row) => ({ ...row, _kind: 'Tripwire' as const })),
  ]
  return <><Header kicker="Configuration · control plane" title="Zones & tripwires"/><div className="metric-grid compact"><div className="metric"><span>Regions</span><strong>{regions.length}</strong><small>Polygon / volumetric occupancy areas</small></div><div className="metric"><span>Tripwires</span><strong>{tripwires.length}</strong><small>Directional crossing boundaries</small></div><div className="metric"><span>Authoring</span><strong className="small-value ok">Visual</strong><small>Scene map vertex editor</small></div></div><section className="panel table-wrap"><table><thead><tr><th>Type</th><th>Name</th><th>Scene</th><th>Geometry</th><th>State</th><th></th></tr></thead><tbody>{rows.map((row)=><tr key={`${row._kind}-${rowId(row)}`}><td>{row._kind}</td><td><b>{rowName(row)}</b></td><td><code>{String(row.scene||'—')}</code></td><td>{(row.points||[]).length} points · {Number(row.height||1).toFixed(2)} m</td><td>{row.visible?'Visible':'Hidden'}{row._kind==='Region'&&row.volumetric?' · volumetric':''}</td><td>{row.scene&&<button className="text-button" onClick={()=>goTo(`scene/${row.scene}/geometry`)}>Open editor</button>}</td></tr>)}</tbody></table>{!rows.length&&<div className="table-empty">No regions or tripwires configured.</div>}</section></>
}

function Incidents() {
  const [rows, setRows] = useState<Row[]>([])
  const [selected, setSelected] = useState<Row | null>(null)
  const [status, setStatus] = useState('new')
  const [note, setNote] = useState('')
  const [assignee, setAssignee] = useState('')
  const load = () => void apiFetch<Row[]>('/api/v2/incidents').then(setRows)
  useEffect(load, [])
  const open = (row: Row) => { setSelected(row); setStatus(row.status); setAssignee(row.assignee || ''); setNote('') }
  const save = async () => {
    if (!selected) return
    const value = await apiFetch<Row>(`/api/v2/incidents/${selected.id}/action`, { method: 'POST', body: JSON.stringify({ status, note, assignee }) })
    setSelected({ ...selected, ...value }); load()
  }
  return <><Header kicker="Operations · data plane" title="Incidents"/><div className="incident-layout"><section className="panel incident-list">{rows.map((row) => <button key={row.id} onClick={() => open(row)} className={selected?.id === row.id ? 'incident-row active' : 'incident-row'}><b>{row.title}</b><span>{row.status} · {row.scene_id || 'global'}</span></button>)}{!rows.length && <div className="table-empty">No analytics incidents have been retained yet.</div>}</section>{selected && <section className="panel incident-detail"><div className="panel-title"><div><h2>{selected.title}</h2><p>Incident #{selected.id}</p></div></div><label>Status<select value={status} onChange={(e) => setStatus(e.target.value)}><option>new</option><option>acknowledged</option><option>investigating</option><option>resolved</option><option>reopened</option></select></label><label>Assignee<input value={assignee} onChange={(e) => setAssignee(e.target.value)}/></label><label>Note<textarea value={note} onChange={(e) => setNote(e.target.value)}/></label><button className="btn btn-primary" onClick={() => void save()}>Save action</button><div className="audit-list">{(selected.audit || []).slice().reverse().map((entry: Row, i: number) => <div key={i}><b>{entry.status || entry.action}</b><span>{entry.at} · {entry.by || 'system'}</span></div>)}</div></section>}</div></>
}

function SceneAnalytics({ scenes, mode }: { scenes: Row[]; mode: 'history'|'trends' }) {
  const [sceneId, setSceneId] = useState('')
  const [rows, setRows] = useState<Row[]>([])
  useEffect(() => { if (!sceneId && scenes[0]) setSceneId(rowId(scenes[0])) }, [scenes])
  const load = () => sceneId && void apiFetch<Row[]>(`/api/v2/scenes/${sceneId}/${mode}`).then(setRows)
  return <><Header kicker="Operations · data plane" title={mode === 'history' ? 'History & replay' : 'Trends & analytics'}><select value={sceneId} onChange={(e) => setSceneId(e.target.value)}>{scenes.map((scene) => <option key={rowId(scene)} value={rowId(scene)}>{rowName(scene)}</option>)}</select><button className="btn btn-primary" onClick={load}>Load</button></Header><section className="panel table-wrap"><table><thead><tr>{mode === 'history' ? <><th>Timestamp</th><th>Objects</th><th>Sample ID</th></> : <><th>Hour</th><th>Average objects</th><th>Samples</th></>}</tr></thead><tbody>{rows.map((row) => mode === 'history' ? <tr key={row.id}><td>{row.timestamp}</td><td>{(row.payload?.objects || []).length}</td><td>{row.id}</td></tr> : <tr key={row.bucket}><td>{row.bucket}</td><td>{row.average_objects}</td><td>{row.samples}</td></tr>)}</tbody></table>{!rows.length && <div className="table-empty">Load a scene to inspect retained native data.</div>}</section></>
}

function App() {
  const auth = useAuth()
  const [path, setPath] = useState(route())
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [scenes, setScenes] = useState<Row[]>([])
  const [apiError, setApiError] = useState('')

  const refresh = () => {
    setApiError('')
    void apiFetch<Overview>('/api/v2/overview').then(setOverview).catch((e) => setApiError(String(e)))
    void apiFetch<Row[]>('/api/v2/scenes').then(setScenes).catch((e) => setApiError(String(e)))
  }
  useEffect(() => { const listener = () => setPath(route()); addEventListener('hashchange', listener); return () => removeEventListener('hashchange', listener) }, [])
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('scenescape-theme', theme) }, [theme])
  useEffect(() => { if (auth.authenticated) refresh() }, [auth.authenticated])

  if (!auth.ready) return <div className="center-state"><div className="spinner"/><h1>Securing SceneScape</h1><p>Establishing your Keycloak session…</p></div>
  if (!auth.authenticated) return <div className="center-state"><h1>Identity service unavailable</h1><p>Verify the Keycloak realm/client configuration.</p><button className="btn btn-primary" onClick={() => void auth.login()}>Try sign in again</button></div>

  const sceneMatch = path.match(/^scene\/([^/]+)(?:\/(geometry|hierarchy))?$/)
  const activeScene = sceneMatch ? scenes.find((scene) => rowId(scene) === sceneMatch[1]) : undefined
  let page: ReactNode
  if (sceneMatch && activeScene) page = <SceneWorkspace scene={activeScene} scenes={scenes} onBack={() => go('live')} onNavigate={go} isAdmin={auth.isAdmin} initialTab={sceneMatch[2] === 'geometry' ? 'Geometry' : sceneMatch[2] === 'hierarchy' ? 'Hierarchy' : 'Live 2D'}/>
  else if (path === 'live') page = <><Header kicker="Operations · data plane" title="Live scenes"><button className="btn" onClick={refresh}>Refresh</button></Header><div className="card-grid">{scenes.map((scene) => <section className="panel scene-card" key={rowId(scene)}><div className="mini-scene"><div className="floor-shape"/><span className="track track-a"/><span className="track track-b"/></div><h2>{rowName(scene)}</h2><code>{rowId(scene)}</code><div className="scene-meta"><span>{scene.map ? 'Map configured' : 'No map'}</span><span>{scene.scale ? `${scene.scale} px/m` : 'Scale unknown'}</span></div><button className="btn btn-primary full" onClick={() => go(`scene/${rowId(scene)}`)}>Open native 2D / 3D scene</button></section>)}</div>{!scenes.length && <div className="empty-state"><h2>No native scenes yet</h2><p>Run <code>./scenescape.sh recover-legacy-data</code> to copy existing Django configuration, or <code>./scenescape.sh seed-native-data</code> for the upstream Retail sample.</p></div>}</>
  else if (path === 'incidents') page = <Incidents/>
  else if (path === 'history') page = <SceneAnalytics scenes={scenes} mode="history"/>
  else if (path === 'trends') page = <SceneAnalytics scenes={scenes} mode="trends"/>
  else if (path === 'health') page = <><Header kicker="Operations · data plane" title="Feed & service health"><button className="btn" onClick={refresh}>Refresh</button></Header><div className="metric-grid compact"><div className="metric"><span>Native API</span><strong className="small-value ok">Connected</strong><small>FastAPI /api/v2</small></div><div className="metric"><span>Database</span><strong className="small-value ok">{overview?.health.database || 'Unknown'}</strong><small>PostgreSQL/native tables</small></div><div className="metric"><span>MQTT historian</span><strong className="small-value">{overview?.health.mqtt || 'Unknown'}</strong><small>Last observation: {overview?.health.last_observation || 'none'}</small></div></div></>
  else if (path === 'scenes') page = <SceneInventory isAdmin={auth.isAdmin}/>
  else if (path === 'cameras') page = <CameraInventory isAdmin={auth.isAdmin}/>
  else if (path === 'sensors') page = <SensorInventory isAdmin={auth.isAdmin}/>
  else if (path === 'zones') page = <Zones goTo={go}/>
  else if (path === 'assets') page = <AssetInventory isAdmin={auth.isAdmin}/>
  else if (path === 'models') page = <ModelLibrary isAdmin={auth.isAdmin}/>
  else if (path === 'hierarchy') page = <><Header kicker="Configuration · scene composition" title="Scene hierarchy"/><HierarchyEditor scenes={scenes} isAdmin={auth.isAdmin}/></>
  else if (path === 'settings') page = <><Header kicker="Administration" title="Identity, access & native migration"/>{auth.isAdmin ? <SecurityAdmin scenes={scenes}/> : <section className="panel settings-list"><div><b>Signed in as</b><span>{auth.displayName}{auth.email ? ` · ${auth.email}` : ''}</span></div><div><b>Roles</b><span>{auth.roles.filter((role) => role.startsWith('scenescape-')).join(', ') || 'authenticated'}</span></div><div><b>Access administration</b><span>Administrator role is required.</span></div></section>}<section className="panel settings-list admin-runtime"><div><b>Browser backend</b><span>FastAPI /api/v2/* with Keycloak OIDC; no Django identity store.</span></div><div><b>Recover existing data</b><code>./scenescape.sh recover-legacy-data</code></div><div><b>Reconcile identity</b><code>./scenescape.sh reconcile-identity</code></div><div><b>Load upstream sample</b><code>./scenescape.sh seed-native-data</code></div></section></>
  else page = <><Header kicker="Operations · data plane" title="Shift overview"><button className="btn" onClick={refresh}>Refresh</button></Header>{apiError && <div className="error-box">{apiError}</div>}<div className="metric-grid"><button className="metric actionable" onClick={() => go('live')}><span>Active scenes</span><strong>{overview?.counts.scenes ?? scenes.length}</strong><small>Open native scene workspace →</small></button><button className="metric actionable" onClick={() => go('cameras')}><span>Camera inputs</span><strong>{overview?.counts.cameras ?? 0}</strong><small>Inspect native configuration →</small></button><button className="metric actionable" onClick={() => go('zones')}><span>Spatial rules</span><strong>{(overview?.counts.regions ?? 0) + (overview?.counts.tripwires ?? 0)}</strong><small>Regions + tripwires →</small></button><button className="metric actionable" onClick={() => go('incidents')}><span>Incidents</span><strong>{overview?.counts.incidents ?? 0}</strong><small>Durable operator workflow →</small></button></div><div className="workspace-grid"><section className="panel scene-panel"><div className="panel-title"><div><h2>Native live scene workspace</h2><p>2D maps, live objects, geometry, calibration and WebGL 3D without Django navigation.</p></div><button className="btn" onClick={() => go('live')}>All scenes</button></div><div className="scene-canvas"><div className="floor-shape"/><div className="zone-shape"/><span className="track track-a"/><span className="track track-b"/><span className="tripwire-shape"/><div className="coverage-note">{scenes.length ? `${scenes.length} scene(s) available in native configuration` : 'No native scene data yet — recover or seed it from Administration'}</div></div></section><section className="panel incident-panel"><div className="panel-title"><div><h2>Operator attention</h2><p>Current native runtime state.</p></div></div><div className="attention-card"><b>MQTT historian</b><span>{overview?.health.mqtt || 'Unknown'} · {(overview?.counts.observations ?? 0)} retained observations</span></div><div className="attention-card"><b>Keycloak session</b><span>{auth.displayName} · {auth.isAdmin ? 'Administrator' : 'Operator'}</span></div><div className="attention-card"><b>Native configuration</b><span>{scenes.length ? 'Scene data available' : 'Recover existing legacy data or load the Retail sample'}</span></div><button className="btn btn-primary full" onClick={() => go('health')}>Open health workspace</button></section></div><section className="panel"><div className="panel-title"><div><h2>Configured scenes</h2><p>All actions remain inside the React/FastAPI application.</p></div></div><div className="scene-list">{scenes.slice(0, 8).map((scene) => <div className="scene-row" key={rowId(scene)}><div><b>{rowName(scene)}</b><span>{rowId(scene)}</span></div><button className="btn" onClick={() => go(`scene/${rowId(scene)}`)}>Open native scene</button></div>)}{!scenes.length && <div className="table-empty">No scenes imported into native tables yet.</div>}</div></section></>

  return <div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-mark">S</div><div><b>SceneScape</b><span>Native operations console</span></div></div><div className="nav-label">Operations · data plane</div>{operations.map(([key, label]) => <button key={key} className={path === key ? 'nav-item active' : 'nav-item'} onClick={() => go(key)}>{label}</button>)}<div className="nav-label">Configuration · control plane</div>{configuration.map(([key, label]) => <button key={key} className={path === key ? 'nav-item active' : 'nav-item'} onClick={() => go(key)}>{label}</button>)}<div className="nav-label">Administration</div><button className={path === 'settings' ? 'nav-item active' : 'nav-item'} onClick={() => go('settings')}>Access & migration</button></aside><div className="content-shell"><header className="topbar"><div className="environment"><span className="status-dot"/>SceneScape 2026.2.0 · Native</div><div className="top-actions"><label className="theme-picker"><span>Theme</span><select aria-label="Visual theme" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>{themes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><div className="identity"><b>{auth.displayName}</b><span>{auth.isAdmin ? 'Administrator' : 'Operator'}</span></div><button className="btn" onClick={() => void auth.logout()}>Sign out</button></div></header><main>{page}</main></div></div>
}

export default App
