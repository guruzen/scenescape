import { useEffect, useMemo, useState } from 'react'
import { apiFetch, normalizeList } from './api/client'
import { legacyUrl, runtimeConfig } from './config'
import { useAuth } from './auth/AuthProvider'

type RouteKey = 'overview' | 'live' | 'incidents' | 'history' | 'trends' | 'health' | 'scenes' | 'cameras' | 'sensors' | 'zones' | 'settings'
type Theme = 'light' | 'light-air' | 'dark' | 'dark-command'
type Overview = { generated_at: string; counts: Record<string, number | null>; health: Record<string, string> }
type Row = Record<string, unknown>

const operations: Array<[RouteKey, string]> = [
  ['overview', 'Shift overview'], ['live', 'Live scenes'], ['incidents', 'Incidents'], ['history', 'History & replay'], ['trends', 'Trends & analytics'], ['health', 'Feed & service health'],
]
const configuration: Array<[RouteKey, string]> = [
  ['scenes', 'Sites, floors & scenes'], ['cameras', 'Cameras'], ['sensors', 'Sensors'], ['zones', 'Zones & tripwires'],
]
const themes: Array<{ value: Theme; label: string }> = [
  { value: 'light', label: 'Light' },
  { value: 'light-air', label: 'Light Air' },
  { value: 'dark', label: 'Dark' },
  { value: 'dark-command', label: 'Dark Command' },
]

const routeFromHash = (): RouteKey => {
  const key = window.location.hash.replace(/^#\/?/, '').split('/')[0] as RouteKey
  return [...operations, ...configuration, ['settings', 'Administration'] as [RouteKey, string]].some(([candidate]) => candidate === key) ? key : 'overview'
}
const initialTheme = (): Theme => {
  const saved = localStorage.getItem('scenescape-theme')
  if (themes.some(({ value }) => value === saved)) return saved as Theme
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
const go = (route: RouteKey) => { window.location.hash = `#/${route}` }
const text = (value: unknown) => value === null || value === undefined || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)
const rowId = (row: Row) => String(row.uid ?? row.id ?? row.sensor_id ?? row.camera_id ?? row.uuid ?? row.pk ?? '')
const rowName = (row: Row) => String(row.name ?? row.title ?? row.sensor_id ?? row.camera_id ?? row.uid ?? row.id ?? 'Unnamed')

function Header({ title, kicker, children }: { title: string; kicker: string; children?: React.ReactNode }) {
  return <div className="page-header"><div><div className="kicker">{kicker}</div><h1>{title}</h1></div><div className="header-actions">{children}</div></div>
}

function EmptyCapability({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return <section className="panel empty-capability"><div className="capability-mark">+</div><h2>{title}</h2><p>{body}</p>{action}</section>
}

function Inventory({ kind, label, legacyPath }: { kind: 'scenes' | 'cameras' | 'sensors' | 'regions' | 'tripwires'; label: string; legacyPath: string }) {
  const [rows, setRows] = useState<Row[]>([])
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => {
    setError('')
    void apiFetch<unknown>(`/api/v2/${kind}`).then((payload) => setRows(normalizeList(payload))).catch((e) => setError(String(e)))
  }, [kind])
  const filtered = useMemo(() => rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase())), [rows, query])
  return <>
    <Header kicker="Configuration · control plane" title={label}><a className="btn" href={legacyUrl(legacyPath)}>Open advanced Django editor</a></Header>
    <div className="toolbar"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Search ${label.toLowerCase()}`} /><span className="muted">{filtered.length} configured</span></div>
    {error ? <div className="error-box">{error}</div> : <section className="panel table-wrap"><table><thead><tr><th>Name</th><th>Identifier</th><th>Scene / context</th><th></th></tr></thead><tbody>{filtered.map((row) => <tr key={rowId(row) || rowName(row)}><td><b>{rowName(row)}</b></td><td>{rowId(row) || '—'}</td><td>{text(row.scene ?? row.scene_id ?? row.parent)}</td><td><a className="text-link" href={legacyUrl(legacyPath)}>Configure</a></td></tr>)}</tbody></table>{!filtered.length && <div className="table-empty">No matching resources.</div>}</section>}
  </>
}

function Zones() {
  const [regions, setRegions] = useState<Row[]>([])
  const [tripwires, setTripwires] = useState<Row[]>([])
  useEffect(() => {
    void apiFetch<unknown>('/api/v2/regions').then((p) => setRegions(normalizeList(p))).catch(() => setRegions([]))
    void apiFetch<unknown>('/api/v2/tripwires').then((p) => setTripwires(normalizeList(p))).catch(() => setTripwires([]))
  }, [])
  return <>
    <Header kicker="Configuration · control plane" title="Zones & tripwires"><a className="btn btn-primary" href={legacyUrl()}>Open spatial editor</a></Header>
    <div className="metric-grid compact"><div className="metric"><span>Regions</span><strong>{regions.length}</strong><small>Scene-level areas</small></div><div className="metric"><span>Tripwires</span><strong>{tripwires.length}</strong><small>Directional boundaries</small></div><div className="metric"><span>Publication model</span><strong className="small-value">Legacy</strong><small>Draft → validate → publish is the migration target</small></div></div>
    <section className="panel"><div className="panel-title"><div><h2>Spatial analytics configuration</h2><p>Keep geometry authoring separate from operational alert handling.</p></div></div><div className="split-list"><div><h3>Regions</h3>{regions.map((r) => <div className="list-row" key={rowId(r)}><span>{rowName(r)}</span><code>{rowId(r)}</code></div>)}</div><div><h3>Tripwires</h3>{tripwires.map((r) => <div className="list-row" key={rowId(r)}><span>{rowName(r)}</span><code>{rowId(r)}</code></div>)}</div></div></section>
  </>
}

function App() {
  const auth = useAuth()
  const [route, setRoute] = useState<RouteKey>(routeFromHash)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [scenes, setScenes] = useState<Row[]>([])
  const [apiError, setApiError] = useState('')
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => { const onHash = () => setRoute(routeFromHash()); window.addEventListener('hashchange', onHash); return () => window.removeEventListener('hashchange', onHash) }, [])
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('scenescape-theme', theme) }, [theme])
  useEffect(() => {
    if (!auth.authenticated) return
    setApiError('')
    void apiFetch<Overview>('/api/v2/overview').then(setOverview).catch((e) => setApiError(String(e)))
    void apiFetch<unknown>('/api/v2/scenes').then((p) => setScenes(normalizeList(p))).catch(() => setScenes([]))
  }, [auth.authenticated])

  if (!auth.ready) return <div className="center-state"><div className="spinner"/><h1>Securing SceneScape</h1><p>Establishing your Keycloak session…</p></div>
  if (!auth.authenticated) return <div className="center-state"><h1>Identity service unavailable</h1><p>Verify the Keycloak URL, realm and client configuration.</p><button className="btn btn-primary" onClick={() => void auth.login()}>Try sign in again</button></div>

  const page = (() => {
    if (route === 'overview') return <>
      <Header kicker="Operations · data plane" title="Shift overview"><button className="btn" onClick={() => window.location.reload()}>Refresh</button></Header>
      {apiError && <div className="error-box">{apiError}</div>}
      <div className="metric-grid">
        <button className="metric actionable" onClick={() => go('scenes')}><span>Active scenes</span><strong>{overview?.counts.scenes ?? '—'}</strong><small>Review scene scope →</small></button>
        <button className="metric actionable" onClick={() => go('cameras')}><span>Camera inputs</span><strong>{overview?.counts.cameras ?? '—'}</strong><small>Inspect configuration →</small></button>
        <button className="metric actionable" onClick={() => go('zones')}><span>Spatial rules</span><strong>{(overview?.counts.regions ?? 0) + (overview?.counts.tripwires ?? 0)}</strong><small>Regions + tripwires →</small></button>
        <div className="metric"><span>Historical coverage</span><strong className="small-value warning">Not configured</strong><small>Historian required for replay/trends</small></div>
      </div>
      <div className="workspace-grid"><section className="panel scene-panel"><div className="panel-title"><div><h2>Live scene workspace</h2><p>Scene-first access to the existing 2D/3D visualization while the React renderer is migrated.</p></div><button className="btn" onClick={() => go('live')}>All scenes</button></div><div className="scene-canvas"><div className="floor-shape"/><div className="zone-shape"/><span className="track track-a"/><span className="track track-b"/><span className="tripwire-shape"/><div className="coverage-note">Live objects remain authoritative in the existing SceneScape viewer</div></div></section><section className="panel incident-panel"><div className="panel-title"><div><h2>Operator attention</h2><p>Durable incident workflow is a new backend capability.</p></div></div><div className="attention-card critical"><b>Incident service not configured</b><span>Raw region/tripwire events are available from Analytics; persistence, ownership and acknowledgement are not part of the core 2026.2.0 database.</span></div><div className="attention-card"><b>History collection required</b><span>Enable the planned collector before interpreting no historical data as zero activity.</span></div><button className="btn btn-primary full" onClick={() => go('incidents')}>Open incident workspace</button></section></div>
      <section className="panel"><div className="panel-title"><div><h2>Configured scenes</h2><p>Use the modern console for daily navigation; advanced scene creation/calibration remains available in Django during migration.</p></div></div><div className="scene-list">{scenes.slice(0, 6).map((scene) => <div className="scene-row" key={rowId(scene)}><div><b>{rowName(scene)}</b><span>{rowId(scene)}</span></div><a className="btn" href={legacyUrl(`${rowId(scene)}/`)}>Open live view</a></div>)}</div></section>
    </>
    if (route === 'live') return <><Header kicker="Operations · data plane" title="Live scenes"/><div className="card-grid">{scenes.map((scene) => <section className="panel scene-card" key={rowId(scene)}><div className="mini-scene"><div className="floor-shape"/><span className="track track-a"/></div><h2>{rowName(scene)}</h2><code>{rowId(scene)}</code><a className="btn btn-primary full" href={legacyUrl(`${rowId(scene)}/`)}>Open 2D / 3D scene</a></section>)}</div></>
    if (route === 'incidents') return <><Header kicker="Operations · data plane" title="Incidents"/><EmptyCapability title="Incident workflow backend required" body="The UX baseline defines New → Acknowledged → Investigating → Resolved, assignment, notes, evidence and response timing. SceneScape 2026.2.0 emits region/tripwire analytics events but does not provide this durable workflow store." action={<a className="btn" href="/docs/ux/operations-v2/scenescape-operations-ux-v2.html">Review UX prototype</a>}/></>
    if (route === 'history') return <><Header kicker="Operations · data plane" title="History & replay"/><EmptyCapability title="Historian not configured" body="Replay needs durable ingestion of regulated scene output plus analytics events, coverage intervals and historical configuration revisions. The UI intentionally reports unavailable rather than rendering an empty chart."/></>
    if (route === 'trends') return <><Header kicker="Operations · data plane" title="Trends & analytics"/><EmptyCapability title="Trend store not configured" body="Occupancy, directional crossings, dwell, throughput and data-quality trends require retained observations/events and time-bucket aggregates. Missing inputs must remain distinguishable from valid zero activity."/></>
    if (route === 'health') return <><Header kicker="Operations · data plane" title="Feed & service health"/><div className="metric-grid compact"><div className="metric"><span>Manager API</span><strong className="small-value ok">Connected</strong><small>/api/v2 overview responding</small></div><div className="metric"><span>Database</span><strong className="small-value ok">{overview?.health.database ?? 'Unknown'}</strong><small>Manager persistence</small></div><div className="metric"><span>Identity</span><strong className="small-value ok">Keycloak</strong><small>Bearer JWT via PKCE session</small></div></div></>
    if (route === 'scenes') return <Inventory kind="scenes" label="Sites, floors & scenes" legacyPath="scene/list/"/>
    if (route === 'cameras') return <Inventory kind="cameras" label="Cameras" legacyPath="cam/list/"/>
    if (route === 'sensors') return <Inventory kind="sensors" label="Sensors" legacyPath="singleton_sensor/list/"/>
    if (route === 'zones') return <Zones/>
    return <><Header kicker="Administration" title="Identity, migration & fallback"/><section className="panel settings-list"><div><b>Signed in as</b><span>{auth.displayName}{auth.email ? ` · ${auth.email}` : ''}</span></div><div><b>Roles</b><span>{auth.roles.filter((r) => r.startsWith('scenescape-')).join(', ') || 'authenticated'}</span></div><div><b>Modern API</b><span>/api/v2/* — Keycloak Bearer JWT</span></div><div><b>Legacy API compatibility</b><span>/api/v1/* — existing DRF Token behavior preserved</span></div><div><b>Django fallback</b><a className="text-link" href={legacyUrl()}>Open legacy UI</a></div></section></>
  })()

  return <div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-mark">S</div><div><b>{runtimeConfig.appTitle}</b><span>Operations console</span></div></div><div className="nav-label">Operations · data plane</div>{operations.map(([key, label]) => <button key={key} className={route === key ? 'nav-item active' : 'nav-item'} onClick={() => go(key)}>{label}</button>)}<div className="nav-label">Configuration · control plane</div>{configuration.map(([key, label]) => <button key={key} className={route === key ? 'nav-item active' : 'nav-item'} onClick={() => go(key)}>{label}</button>)}<div className="nav-label">Administration</div><button className={route === 'settings' ? 'nav-item active' : 'nav-item'} onClick={() => go('settings')}>Access & migration</button><a className="nav-item legacy" href={legacyUrl()}>Django fallback ↗</a></aside><div className="content-shell"><header className="topbar"><div className="environment"><span className="status-dot"/>SceneScape 2026.2.0</div><div className="top-actions"><label className="theme-picker"><span>Theme</span><select aria-label="Visual theme" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>{themes.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}</select></label><div className="identity"><b>{auth.displayName}</b><span>{auth.isAdmin ? 'Administrator' : 'Operator'}</span></div><button className="btn" onClick={() => void auth.logout()}>Sign out</button></div></header><main>{page}</main></div></div>
}

export default App
