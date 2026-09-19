import { useEffect, useMemo, useState } from 'react'
import type { MouseEvent } from 'react'
import { apiFetch } from '../api/client'
import ThreeScene from './ThreeScene'

type Row = Record<string, any>

const idOf = (row: Row) => String(row.uid ?? row.id ?? '')
const nameOf = (row: Row) => String(row.name ?? row.uid ?? 'Camera')
const defaultIntrinsics = { fx: 570, fy: 570, cx: 320, cy: 240 }
const defaultDistortion = { k1: 0, k2: 0, p1: 0, p2: 0, k3: 0 }

function decodeTransforms(camera: Row): { cameraPoints: number[][]; scenePoints: number[][] } {
  if (camera.transform_type !== '3d-2d point correspondence' || !Array.isArray(camera.transforms)) {
    return { cameraPoints: [], scenePoints: [] }
  }
  const values = camera.transforms.map(Number)
  if (values.length >= 20 && values.length % 5 === 0) {
    const pairs = values.length / 5
    const split = pairs * 2
    const cameraPoints = Array.from({ length: pairs }, (_, i) => values.slice(i * 2, i * 2 + 2))
    const scenePoints = Array.from({ length: pairs }, (_, i) => values.slice(split + i * 3, split + i * 3 + 3))
    return { cameraPoints, scenePoints }
  }
  if (values.length >= 16 && values.length % 4 === 0) {
    const pairs = values.length / 4
    const split = pairs * 2
    const cameraPoints = Array.from({ length: pairs }, (_, i) => values.slice(i * 2, i * 2 + 2))
    const scenePoints = Array.from({ length: pairs }, (_, i) => [...values.slice(split + i * 2, split + i * 2 + 2), 0])
    return { cameraPoints, scenePoints }
  }
  return { cameraPoints: [], scenePoints: [] }
}

const matrixFromIntrinsics = (value: Row) => [
  [Number(value.fx), 0, Number(value.cx)],
  [0, Number(value.fy), Number(value.cy)],
  [0, 0, 1],
]

export default function CameraCalibration({
  scene,
  cameras,
  isAdmin,
  onSaved,
}: {
  scene: Row
  cameras: Row[]
  isAdmin: boolean
  onSaved: () => void
}) {
  const [cameraId, setCameraId] = useState('')
  const [frame, setFrame] = useState<Row | null>(null)
  const [imageSize, setImageSize] = useState<[number, number]>([640, 480])
  const [cameraPoints, setCameraPoints] = useState<number[][]>([])
  const [scenePoints, setScenePoints] = useState<number[][]>([])
  const [intrinsics, setIntrinsics] = useState<Row>({ ...defaultIntrinsics })
  const [distortion, setDistortion] = useState<Row>({ ...defaultDistortion })
  const [lockFx, setLockFx] = useState(true)
  const [lockFy, setLockFy] = useState(true)
  const [markers, setMarkers] = useState<Row[]>([])
  const [service, setService] = useState<Row | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const camera = useMemo(() => cameras.find((item) => idOf(item) === cameraId) || cameras[0] || null, [cameras, cameraId])
  const pairCount = Math.min(cameraPoints.length, scenePoints.length)
  const mapPath = String(scene.map || scene.thumbnail || '')

  useEffect(() => {
    if (!cameraId && cameras[0]) setCameraId(idOf(cameras[0]))
  }, [cameras, cameraId])

  useEffect(() => {
    if (!camera) return
    const initial = decodeTransforms(camera)
    setCameraPoints(initial.cameraPoints)
    setScenePoints(initial.scenePoints)
    setIntrinsics({ ...defaultIntrinsics, ...(camera.intrinsics || {}) })
    setDistortion({ ...defaultDistortion, ...(camera.distortion || {}) })
    const resolution = Array.isArray(camera.resolution) ? camera.resolution : [640, 480]
    setImageSize([Number(resolution[0] || 640), Number(resolution[1] || 480)])
    setFrame(null)
    setMessage('')
    setError('')
  }, [camera ? idOf(camera) : ''])

  useEffect(() => {
    void apiFetch<Row[]>('/api/v2/markers')
      .then((rows) => setMarkers(rows.filter((item) => String(item.scene || '') === String(scene.uid || scene.id || ''))))
      .catch(() => setMarkers([]))
    void apiFetch<Row>('/api/v2/autocalibration/status')
      .then(setService)
      .catch(() => setService({ status: 'unavailable' }))
  }, [scene.uid, scene.id])

  const refreshFrame = async () => {
    if (!camera) return
    setError('')
    try {
      const value = await apiFetch<Row>(`/api/v2/cameras/${encodeURIComponent(idOf(camera))}/calibration-frame?t=${Date.now()}`)
      setFrame(value)
      const runtimeIntrinsics = value.intrinsics
      if (Array.isArray(runtimeIntrinsics)) {
        const flat = runtimeIntrinsics.flat().map(Number)
        if (flat.length >= 9) setIntrinsics({ fx: flat[0], fy: flat[4], cx: flat[2], cy: flat[5] })
      } else if (runtimeIntrinsics && typeof runtimeIntrinsics === 'object') {
        setIntrinsics((old) => ({ ...old, ...runtimeIntrinsics }))
      }
      if (Array.isArray(value.distortion)) {
        const values = value.distortion.flat().map(Number)
        setDistortion({
          k1: values[0] ?? 0, k2: values[1] ?? 0, p1: values[2] ?? 0,
          p2: values[3] ?? 0, k3: values[4] ?? 0,
        })
      }
    } catch (e) {
      setError(String(e))
    }
  }

  const addCameraPoint = (event: MouseEvent<HTMLDivElement>) => {
    if (!frame?.image) return
    const image = event.currentTarget.querySelector('img')
    if (!image) return
    const rect = image.getBoundingClientRect()
    const width = image.naturalWidth || imageSize[0]
    const height = image.naturalHeight || imageSize[1]
    const x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * width
    const y = ((event.clientY - rect.top) / Math.max(rect.height, 1)) * height
    if (x < 0 || y < 0 || x > width || y > height) return
    setCameraPoints((old) => [...old, [x, y]])
  }

  const calculate = async () => {
    if (pairCount < 6) {
      setError('At least 6 matching point pairs are required to estimate camera intrinsics.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const value = await apiFetch<Row>('/api/v2/calculateintrinsics', {
        method: 'POST',
        body: JSON.stringify({
          camPoints: cameraPoints.slice(0, pairCount),
          mapPoints: scenePoints.slice(0, pairCount),
          fixIntrinsics: { fx: lockFx, fy: lockFy },
          intrinsics: matrixFromIntrinsics(intrinsics),
          distortion: [distortion.k1, distortion.k2, distortion.p1, distortion.p2, distortion.k3],
          imageSize,
        }),
      })
      const matrix = value.mtx
      const dist = Array.isArray(value.dist) ? value.dist.flat() : []
      if (Array.isArray(matrix) && matrix.length >= 3) {
        setIntrinsics({
          fx: Number(matrix[0][0]), fy: Number(matrix[1][1]),
          cx: Number(matrix[0][2]), cy: Number(matrix[1][2]),
        })
      }
      setDistortion({
        k1: Number(dist[0] || 0), k2: Number(dist[1] || 0),
        p1: Number(dist[2] || 0), p2: Number(dist[3] || 0), k3: Number(dist[4] || 0),
      })
      setMessage('Camera intrinsics recalculated from the matching point pairs.')
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const saveManual = async () => {
    if (!camera || !isAdmin) return
    if (cameraPoints.length !== scenePoints.length || pairCount < 4) {
      setError(`Saving calibration requires equal point counts with at least 4 pairs. Camera: ${cameraPoints.length}, scene: ${scenePoints.length}.`)
      return
    }
    setBusy(true)
    setError('')
    try {
      const transforms = [
        ...cameraPoints.flatMap((point) => point.slice(0, 2)),
        ...scenePoints.flatMap((point) => point.slice(0, 3)),
      ]
      const saved = await apiFetch<Row>(`/api/v2/cameras/${encodeURIComponent(idOf(camera))}?revision=${camera.revision}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: camera.name,
          scene: camera.scene,
          transform_type: '3d-2d point correspondence',
          transforms,
          intrinsics,
          distortion,
          resolution: imageSize,
        }),
      })
      await apiFetch(`/api/v2/cameras/${encodeURIComponent(idOf(saved))}/runtime-update`, {
        method: 'POST',
        body: JSON.stringify({ intrinsics, distortion }),
      }).catch(() => null)
      setMessage('Manual 2D/3D camera calibration saved.')
      onSaved()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const waitForRegistration = async () => {
    const sceneId = String(scene.uid || scene.id)
    let status = await apiFetch<Row>(`/api/v2/autocalibration/scenes/${encodeURIComponent(sceneId)}/registration`, { method: 'POST', body: '{}' })
    for (let i = 0; i < 90 && ['registering', 'busy'].includes(String(status.status)); i += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000))
      status = await apiFetch<Row>(`/api/v2/autocalibration/scenes/${encodeURIComponent(sceneId)}/registration`)
    }
    if (status.status !== 'success') throw new Error(String(status.message || status.status || 'Scene registration failed'))
    return status
  }

  const autoCalibrate = async () => {
    if (!camera || !isAdmin) return
    setBusy(true)
    setError('')
    setMessage('Registering scene with auto-calibration…')
    try {
      await waitForRegistration()
      let source = frame
      if (!source?.image) {
        source = await apiFetch<Row>(`/api/v2/cameras/${encodeURIComponent(idOf(camera))}/calibration-frame?t=${Date.now()}`)
        setFrame(source)
      }
      setMessage('Auto-calibrating camera…')
      const image = String(source?.image || '')
      if (!image) throw new Error('Calibration frame did not contain an image.')
      await apiFetch(`/api/v2/autocalibration/cameras/${encodeURIComponent(idOf(camera))}/calibration`, {
        method: 'POST',
        body: JSON.stringify({ image, intrinsics: matrixFromIntrinsics(intrinsics) }),
      })
      let result: Row = {}
      for (let i = 0; i < 90; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000))
        result = await apiFetch<Row>(`/api/v2/autocalibration/cameras/${encodeURIComponent(idOf(camera))}/calibration`)
        if (!['busy', 'calibrating', 'not_started'].includes(String(result.status))) break
      }
      if (result.status !== 'success') throw new Error(String(result.message || 'Auto-calibration failed'))
      if (Array.isArray(result.calibration_points_2d)) setCameraPoints(result.calibration_points_2d)
      if (Array.isArray(result.calibration_points_3d)) setScenePoints(result.calibration_points_3d)
      const quaternion = result.quaternion || result.pose?.quaternion
      const translation = result.translation || result.pose?.translation
      if (!Array.isArray(quaternion) || !Array.isArray(translation)) {
        throw new Error('Auto-calibration did not return a camera pose.')
      }
      const saved = await apiFetch<Row>(`/api/v2/cameras/${encodeURIComponent(idOf(camera))}?revision=${camera.revision}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: camera.name,
          scene: camera.scene,
          translation,
          rotation: quaternion,
          scale: camera.scale || [1, 1, 1],
          transform_type: 'quaternion',
          intrinsics,
          distortion,
          resolution: imageSize,
        }),
      })
      await apiFetch(`/api/v2/cameras/${encodeURIComponent(idOf(saved))}/runtime-update`, {
        method: 'POST',
        body: JSON.stringify({
          translation: saved.translation,
          rotation: saved.rotation,
          intrinsics,
          distortion,
        }),
      }).catch(() => null)
      setMessage(`${scene.camera_calibration || 'Auto'} calibration completed and camera pose saved.`)
      onSaved()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const removePair = (index: number) => {
    setCameraPoints((old) => old.filter((_, i) => i !== index))
    setScenePoints((old) => old.filter((_, i) => i !== index))
  }

  if (!camera) return <div className="empty-state"><h2>No cameras configured</h2><p>Add a camera before calibrating this scene.</p></div>

  return <div className="calibration-workspace">
    <div className="panel calibration-controls">
      <div className="panel-title"><div><h2>Camera calibration</h2><p>2026.2-compatible point correspondence and auto-calibration workflow</p></div></div>
      <div className="scene-form-grid calibration-form">
        <label>Camera<select value={idOf(camera)} onChange={(e)=>setCameraId(e.target.value)}>{cameras.map((item)=><option key={idOf(item)} value={idOf(item)}>{nameOf(item)}</option>)}</select></label>
        <label>Strategy<input value={String(scene.camera_calibration || 'Manual')} readOnly/></label>
        {(['fx','fy','cx','cy'] as const).map((key)=><label key={key}>{key.toUpperCase()}<input type="number" step="any" value={Number(intrinsics[key] ?? 0)} onChange={(e)=>setIntrinsics((old)=>({...old,[key]:Number(e.target.value)}))}/></label>)}
        {(['k1','k2','p1','p2','k3'] as const).map((key)=><label key={key}>{key}<input type="number" step="any" value={Number(distortion[key] ?? 0)} onChange={(e)=>setDistortion((old)=>({...old,[key]:Number(e.target.value)}))}/></label>)}
        <label className="checkbox-label"><input type="checkbox" checked={lockFx} onChange={(e)=>setLockFx(e.target.checked)}/>Lock FX</label>
        <label className="checkbox-label"><input type="checkbox" checked={lockFy} onChange={(e)=>setLockFy(e.target.checked)}/>Lock FY</label>
      </div>
      <div className="editor-actions">
        <button className="btn" disabled={busy} onClick={() => void refreshFrame()}>Refresh calibration frame</button>
        <button className="btn" disabled={busy || pairCount < 6} onClick={() => void calculate()}>Recalculate intrinsics</button>
        <button className="btn" onClick={() => { setCameraPoints([]); setScenePoints([]) }}>Reset points</button>
        {scene.camera_calibration !== 'Manual' && <button className="btn" disabled={busy || service?.status !== 'running'} onClick={() => void autoCalibrate()}>Auto calibrate</button>}
        <button className="btn btn-primary" disabled={!isAdmin || busy} onClick={() => void saveManual()}>Save calibration</button>
      </div>
      {message && <div className="notice-box calibration-message">{message}</div>}
      {error && <div className="error-box calibration-message">{error}</div>}
    </div>

    <div className="calibration-panes">
      <section className="panel">
        <div className="panel-title"><div><h2>Camera image</h2><p>Double-click image points in order.</p></div><span className="status-pill">{cameraPoints.length} points</span></div>
        <div className="camera-cal-frame">
          {frame?.image ? <div className="camera-cal-image" onDoubleClick={addCameraPoint}><img src={`data:image/jpeg;base64,${frame.image}`} alt={nameOf(camera)} onLoad={(e)=>setImageSize([e.currentTarget.naturalWidth,e.currentTarget.naturalHeight])}/><svg viewBox={`0 0 ${imageSize[0]} ${imageSize[1]}`} preserveAspectRatio="none">{cameraPoints.map((point,index)=><g key={index}><circle cx={point[0]} cy={point[1]} r="8" className="calibration-point"/><text x={point[0]+10} y={point[1]-10} className="map-label">{index+1}</text></g>)}</svg></div> : <div className="camera-feed-placeholder">Refresh the calibration frame to begin.</div>}
        </div>
      </section>
      <section className="panel">
        <div className="panel-title"><div><h2>Scene map</h2><p>Double-click the corresponding 3D points in the same order.</p></div><span className="status-pill">{scenePoints.length} points</span></div>
        <ThreeScene
          mapPath={mapPath}
          objects={[]}
          scale={Number(scene.scale || 100)}
          meshTranslation={scene.mesh_translation}
          meshRotation={scene.mesh_rotation}
          meshScale={scene.mesh_scale}
          pickedPoints={scenePoints}
          onPick={(point)=>setScenePoints((old)=>[...old,point])}
        />
      </section>
    </div>

    <div className="workspace-grid calibration-bottom">
      <section className="panel">
        <div className="panel-title"><div><h2>Point pairs</h2><p>Minimum 4; 6+ enables focal-length estimation.</p></div><span className={cameraPoints.length===scenePoints.length && pairCount>=4 ? 'status-pill ok-pill':'status-pill warning-pill'}>{cameraPoints.length} / {scenePoints.length}</span></div>
        <div className="table-wrap"><table><thead><tr><th>#</th><th>Camera x,y</th><th>Scene x,y,z</th><th></th></tr></thead><tbody>{Array.from({length:Math.max(cameraPoints.length,scenePoints.length)},(_,index)=><tr key={index}><td>{index+1}</td><td>{cameraPoints[index]?.map((v)=>v.toFixed(1)).join(', ') || '—'}</td><td>{scenePoints[index]?.map((v)=>v.toFixed(3)).join(', ') || '—'}</td><td><button className="text-button" onClick={()=>removePair(index)}>Remove</button></td></tr>)}</tbody></table>{!cameraPoints.length && !scenePoints.length && <div className="table-empty">No calibration points placed yet.</div>}</div>
      </section>
      <section className="panel">
        <div className="panel-title"><div><h2>Auto-calibration context</h2><p>{service?.status || 'unavailable'} · {scene.camera_calibration || 'Manual'}</p></div></div>
        <div className="stack-list">{markers.map((marker)=><div key={String(marker.marker_id || marker.uid)}><b>AprilTag {String(marker.apriltag_id ?? marker.marker_id)}</b><span>{Array.isArray(marker.dims) ? marker.dims.map((v:number)=>Number(v).toFixed(3)).join(', ') : 'No 3D position'}</span></div>)}{!markers.length && <div className="table-empty">{scene.camera_calibration === 'AprilTag' ? 'No registered AprilTag markers yet.' : 'Calibration markers are used by AprilTag scenes.'}</div>}</div>
      </section>
    </div>
  </div>
}
