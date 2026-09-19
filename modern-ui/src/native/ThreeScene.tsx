// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { apiFetch, apiObjectUrl } from '../api/client'

type Row = Record<string, any>

export default function ThreeScene({
  mapPath,
  objects,
  scale = 100,
  meshTranslation,
  meshRotation,
  meshScale,
  onPick,
  pickedPoints = [],
  regions = [],
  tripwires = [],
  sensors = [],
  childRegions = [],
  childTripwires = [],
  childSensors = [],
  mediaOverrideUrl,
  previewAsset,
  showTrackedObjects = true,
  showSpatial = true,
  showFloor = true,
  cameras = [],
  projectCameraFrames = false,
  cameraOpacity = 0.8,
  selectedCameraId = '',
  useSelectedCameraView = false,
  lightIntensity = 1,
}: {
  mapPath?: string
  objects: Row[]
  scale?: number
  meshTranslation?: number[]
  meshRotation?: number[]
  meshScale?: number[]
  onPick?: (point: number[]) => void
  pickedPoints?: number[][]
  regions?: Row[]
  tripwires?: Row[]
  sensors?: Row[]
  childRegions?: Row[]
  childTripwires?: Row[]
  childSensors?: Row[]
  mediaOverrideUrl?: string
  previewAsset?: Row
  showTrackedObjects?: boolean
  showSpatial?: boolean
  showFloor?: boolean
  cameras?: Row[]
  projectCameraFrames?: boolean
  cameraOpacity?: number
  selectedCameraId?: string
  useSelectedCameraView?: boolean
  lightIntensity?: number
}) {
  const host = useRef<HTMLDivElement | null>(null)
  const surface = useRef<HTMLDivElement | null>(null)
  const objectGroup = useRef<THREE.Group | null>(null)
  const calibrationGroup = useRef<THREE.Group | null>(null)
  const spatialGroup = useRef<THREE.Group | null>(null)
  const cameraGroup = useRef<THREE.Group | null>(null)
  const cameraViewRef = useRef<Record<string, THREE.PerspectiveCamera>>({})
  const onPickRef = useRef(onPick)
  const assetPrototypes = useRef<Record<string, THREE.Object3D>>({})
  const [assets, setAssets] = useState<Row[]>([])
  const [assetVersion, setAssetVersion] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => { onPickRef.current = onPick }, [onPick])

  useEffect(() => {
    if (previewAsset) {
      setAssets([previewAsset])
      return
    }
    let active = true
    void apiFetch<Row[]>('/api/v2/assets').then((rows) => { if (active) setAssets(rows) }).catch(() => { if (active) setAssets([]) })
    return () => { active = false }
  }, [previewAsset])

  useEffect(() => {
    let active = true
    const urls: string[] = []
    const load = async () => {
      const next: Record<string, THREE.Object3D> = {}
      for (const asset of assets) {
        const path = String(asset.model_3d || '')
        if (!path && !(previewAsset && mediaOverrideUrl)) continue
        try {
          const url = previewAsset && mediaOverrideUrl ? mediaOverrideUrl : await apiObjectUrl(path)
          if (!(previewAsset && mediaOverrideUrl)) urls.push(url)
          const gltf = await new GLTFLoader().loadAsync(url)
          if (!active) return
          const model = gltf.scene
          model.rotation.set(
            THREE.MathUtils.degToRad(Number(asset.rotation_x || 0)),
            THREE.MathUtils.degToRad(Number(asset.rotation_y || 0)),
            THREE.MathUtils.degToRad(Number(asset.rotation_z || 0)),
          )
          model.position.set(Number(asset.translation_x || 0), Number(asset.translation_y || 0), Number(asset.translation_z || 0))
          next[String(asset.name || '')] = model
        } catch {
          // Invalid/unavailable asset models fall back to configured box geometry.
        }
      }
      if (active) {
        assetPrototypes.current = next
        setAssetVersion((value) => value + 1)
      }
    }
    void load()
    return () => { active = false; urls.forEach((url) => URL.revokeObjectURL(url)) }
  }, [assets, mediaOverrideUrl, previewAsset])

  useEffect(() => {
    if (!host.current || !surface.current) return
    let disposed = false
    let frame = 0
    let mediaUrl = ''
    let resize: ResizeObserver | undefined
    const container = host.current
    const renderSurface = surface.current
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    } catch {
      setError('WebGL is unavailable in this browser. The native 2D workspace remains available.')
      return
    }

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0b151a)
    scene.up.set(0, 0, 1)
    const camera = new THREE.PerspectiveCamera(48, 1, 0.01, 5000)
    camera.up.set(0, 0, 1)
    camera.position.set(8, -10, 9)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.target.set(3, 3, 0)

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.domElement.className = 'three-canvas'
    renderSurface.replaceChildren(renderer.domElement)

    const hemisphere = new THREE.HemisphereLight(0xffffff, 0x334455, 1.8 * lightIntensity)
    scene.add(hemisphere)
    const sun = new THREE.DirectionalLight(0xffffff, 2.2 * lightIntensity)
    sun.position.set(10, -8, 14)
    scene.add(sun)
    const grid = new THREE.GridHelper(20, 20, 0x3a6168, 0x244047)
    grid.rotation.x = Math.PI / 2
    grid.visible = showFloor
    scene.add(grid)
    const group = new THREE.Group()
    objectGroup.current = group
    scene.add(group)
    const calibration = new THREE.Group()
    calibrationGroup.current = calibration
    scene.add(calibration)
    const spatial = new THREE.Group()
    spatialGroup.current = spatial
    scene.add(spatial)
    const cameraVisuals = new THREE.Group()
    cameraGroup.current = cameraVisuals
    scene.add(cameraVisuals)
    const pickTargets: THREE.Object3D[] = []

    const fit = (object: THREE.Object3D) => {
      const box = new THREE.Box3().setFromObject(object)
      if (box.isEmpty()) return
      const size = box.getSize(new THREE.Vector3())
      const center = box.getCenter(new THREE.Vector3())
      const radius = Math.max(size.x, size.y, size.z, 1)
      controls.target.copy(center)
      camera.position.set(center.x + radius * 1.15, center.y - radius * 1.35, center.z + radius * 1.1)
      camera.near = Math.max(radius / 1000, 0.01)
      camera.far = Math.max(radius * 100, 100)
      camera.updateProjectionMatrix()
      controls.update()
    }

    const loadMap = async () => {
      if (!mapPath) return
      try {
        mediaUrl = mediaOverrideUrl || await apiObjectUrl(mapPath)
        if (disposed) return
        if (/\.glb(?:$|\?)/i.test(mapPath)) {
          new GLTFLoader().load(mediaUrl, (gltf) => {
            if (disposed) return
            const translation = Array.isArray(meshTranslation) ? meshTranslation : [0, 0, 0]
            const rotation = Array.isArray(meshRotation) ? meshRotation : [0, 0, 0]
            const objectScale = Array.isArray(meshScale) ? meshScale : [1, 1, 1]
            gltf.scene.position.set(Number(translation[0] || 0), Number(translation[1] || 0), Number(translation[2] || 0))
            gltf.scene.rotation.set(
              THREE.MathUtils.degToRad(Number(rotation[0] || 0)),
              THREE.MathUtils.degToRad(Number(rotation[1] || 0)),
              THREE.MathUtils.degToRad(Number(rotation[2] || 0)),
            )
            gltf.scene.scale.set(
              Number(objectScale[0] ?? 1),
              Number(objectScale[1] ?? 1),
              Number(objectScale[2] ?? 1),
            )
            scene.add(gltf.scene)
            pickTargets.push(gltf.scene)
            fit(gltf.scene)
          }, undefined, () => setError('The GLB map could not be rendered. Live data is still available in 2D.'))
        } else if (/\.(?:png|jpe?g|webp)(?:$|\?)/i.test(mapPath)) {
          new THREE.TextureLoader().load(mediaUrl, (texture) => {
            if (disposed) return
            texture.colorSpace = THREE.SRGBColorSpace
            const image = texture.image as { width?: number; height?: number }
            const width = Math.max(1, Number(image.width || 1000) / Math.max(scale, 1))
            const height = Math.max(1, Number(image.height || 700) / Math.max(scale, 1))
            const plane = new THREE.Mesh(
              new THREE.PlaneGeometry(width, height),
              new THREE.MeshBasicMaterial({ map: texture, side: THREE.DoubleSide }),
            )
            plane.position.set(width / 2, height / 2, -0.02)
            scene.add(plane)
            pickTargets.push(plane)
            fit(plane)
          }, undefined, () => setError('The map image could not be rendered in 3D.'))
        }
      } catch (e) {
        if (!disposed) setError(String(e))
      }
    }
    void loadMap()

    const resizeRenderer = () => {
      const width = Math.max(1, container.clientWidth)
      const height = Math.max(260, container.clientHeight)
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    resize = new ResizeObserver(resizeRenderer)
    resize.observe(container)
    resizeRenderer()

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    const handlePick = (event: MouseEvent) => {
      if (!onPickRef.current || !pickTargets.length) return
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 2 - 1
      pointer.y = -((event.clientY - rect.top) / Math.max(rect.height, 1)) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const hit = raycaster.intersectObjects(pickTargets, true)[0]
      if (hit) onPickRef.current([hit.point.x, hit.point.y, hit.point.z])
    }
    renderer.domElement.addEventListener('dblclick', handlePick)

    const loop = () => {
      controls.update()
      const activeCamera = useSelectedCameraView && selectedCameraId && cameraViewRef.current[selectedCameraId]
        ? cameraViewRef.current[selectedCameraId]
        : camera
      if (activeCamera instanceof THREE.PerspectiveCamera) {
        activeCamera.aspect = Math.max(1, container.clientWidth) / Math.max(260, container.clientHeight)
        activeCamera.updateProjectionMatrix()
      }
      renderer.render(scene, activeCamera)
      frame = requestAnimationFrame(loop)
    }
    loop()

    return () => {
      disposed = true
      cancelAnimationFrame(frame)
      resize?.disconnect()
      controls.dispose()
      renderer.domElement.removeEventListener('dblclick', handlePick)
      renderer.dispose()
      renderer.domElement.remove()
      if (mediaUrl && mediaUrl !== mediaOverrideUrl) URL.revokeObjectURL(mediaUrl)
      objectGroup.current = null
      calibrationGroup.current = null
      spatialGroup.current = null
      cameraGroup.current = null
      cameraViewRef.current = {}
    }
  }, [
    mapPath,
    scale,
    meshTranslation?.[0], meshTranslation?.[1], meshTranslation?.[2],
    meshRotation?.[0], meshRotation?.[1], meshRotation?.[2],
    meshScale?.[0], meshScale?.[1], meshScale?.[2],
    mediaOverrideUrl,
    showFloor,
    selectedCameraId,
    useSelectedCameraView,
    lightIntensity,
  ])

  useEffect(() => {
    const group = objectGroup.current
    if (!group) return
    while (group.children.length) {
      const child = group.children.pop()
      if (!child) continue
      child.traverse((node) => {
        if (node instanceof THREE.Mesh && node.userData.generatedGeometry) {
          node.geometry.dispose()
          const material = node.material
          if (Array.isArray(material)) material.forEach((m) => m.dispose())
          else material.dispose()
        }
      })
    }

    const assetByName = new Map(assets.map((asset) => [String(asset.name || ''), asset]))
    const renderItem = (item: Row, index: number) => {
      const category = String(item.category || 'unknown')
      const asset = assetByName.get(category)
      const root = new THREE.Group()
      const translation = Array.isArray(item.translation) ? item.translation : [0, 0, 0]
      const z = asset?.project_to_map ? 0 : Number(translation[2] || 0)
      root.position.set(Number(translation[0] || 0), Number(translation[1] || 0), z)

      if (Array.isArray(item.rotation) && item.rotation.length === 4) {
        root.quaternion.fromArray(item.rotation.map(Number))
      } else if (asset?.rotation_from_velocity && Array.isArray(item.velocity) && item.velocity.length >= 2) {
        root.rotation.z = Math.atan2(Number(item.velocity[1] || 0), Number(item.velocity[0] || 0))
      }

      let model: THREE.Object3D
      const prototype = assetPrototypes.current[category]
      if (prototype) {
        model = prototype.clone(true)
      } else {
        const color = asset?.mark_color ? new THREE.Color(String(asset.mark_color)) : new THREE.Color(0x4ed1ce)
        const geometry = new THREE.BoxGeometry(1, 1, 1)
        const material = new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.82 })
        const mesh = new THREE.Mesh(geometry, material)
        mesh.userData.generatedGeometry = true
        model = mesh
      }
      model.name = 'model'

      if (Number.isFinite(Number(item.asset_scale))) {
        const s = Number(item.asset_scale)
        root.scale.set(s, s, s)
      } else if (Array.isArray(item.size) && item.size.length >= 3) {
        root.scale.set(Number(item.size[0] || 1), Number(item.size[1] || 1), Number(item.size[2] || 1))
        root.translateZ(root.scale.z / 2)
      } else if (asset) {
        const s = Number(asset.scale || 1)
        if (prototype) root.scale.set(s, s, s)
        else root.scale.set(Number(asset.x_size || 1) * s, Number(asset.y_size || 1) * s, Number(asset.z_size || 1) * s)
      } else {
        root.scale.set(0.24, 0.24, 0.24)
      }

      root.add(model)
      root.userData.objectId = item.id ?? index
      root.userData.category = category
      group.add(root)
    }

    if (previewAsset) {
      renderItem({ id: 'preview', category: previewAsset.name, translation: [0, 0, 0] }, 0)
    } else if (showTrackedObjects) {
      ;(objects || []).forEach(renderItem)
    }
  }, [objects, assets, assetVersion, mapPath, previewAsset, showTrackedObjects])

  useEffect(() => {
    const group = spatialGroup.current
    if (!group) return
    while (group.children.length) {
      const child = group.children.pop()
      if (!child) continue
      child.traverse((node) => {
        if (node instanceof THREE.Mesh || node instanceof THREE.Line) {
          node.geometry.dispose()
          const material = node.material
          if (Array.isArray(material)) material.forEach((item) => item.dispose())
          else material.dispose()
        }
      })
    }

    const addPolygon = (points: any[], height: number, material: THREE.Material) => {
      if (!Array.isArray(points) || points.length < 3) return
      const shape = new THREE.Shape(points.map((point) => new THREE.Vector2(Number(point[0] || 0), Number(point[1] || 0))))
      const geometry = new THREE.ExtrudeGeometry(shape, { depth: Math.max(0.01, height), bevelEnabled: false })
      const mesh = new THREE.Mesh(geometry, material)
      group.add(mesh)
    }

    if (!showSpatial) return

    for (const region of regions) {
      if (!region.visible) continue
      addPolygon(
        region.points || [],
        Number(region.height || 1),
        new THREE.MeshStandardMaterial({ color: 0x4ed1ce, transparent: true, opacity: region.volumetric ? 0.22 : 0.12, side: THREE.DoubleSide }),
      )
    }

    for (const region of childRegions) {
      addPolygon(
        region.points || [],
        Number(region.height || 1),
        new THREE.MeshStandardMaterial({ color: 0x6187ff, transparent: true, opacity: 0.12, side: THREE.DoubleSide }),
      )
    }

    for (const tripwire of tripwires) {
      if (!tripwire.visible || !Array.isArray(tripwire.points) || tripwire.points.length < 2) continue
      const z = Math.max(0.03, Number(tripwire.height || 1))
      const points = tripwire.points.map((point: any) => new THREE.Vector3(Number(point[0] || 0), Number(point[1] || 0), z))
      const geometry = new THREE.BufferGeometry().setFromPoints(points)
      group.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0xff7859 })))
      for (const point of tripwire.points) {
        const pillar = new THREE.Mesh(
          new THREE.CylinderGeometry(0.018, 0.018, z, 8),
          new THREE.MeshBasicMaterial({ color: 0xff7859, transparent: true, opacity: 0.55 }),
        )
        pillar.rotation.x = Math.PI / 2
        pillar.position.set(Number(point[0] || 0), Number(point[1] || 0), z / 2)
        group.add(pillar)
      }
    }

    for (const tripwire of childTripwires) {
      if (!Array.isArray(tripwire.points) || tripwire.points.length < 2) continue
      const z = Math.max(0.03, Number(tripwire.height || 1))
      const points = tripwire.points.map((point: any) => new THREE.Vector3(Number(point[0] || 0), Number(point[1] || 0), z))
      const geometry = new THREE.BufferGeometry().setFromPoints(points)
      group.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0x6187ff, transparent: true, opacity: 0.75 })))
    }

    for (const sensor of sensors) {
      if (!sensor.visible) continue
      const material = new THREE.MeshStandardMaterial({ color: 0xffb454, transparent: true, opacity: 0.16, side: THREE.DoubleSide })
      if (sensor.area === 'poly') {
        addPolygon(sensor.points || [], 0.08, material)
      } else if (sensor.area === 'circle' && Array.isArray(sensor.center)) {
        const geometry = new THREE.CylinderGeometry(Number(sensor.radius || 0), Number(sensor.radius || 0), 0.08, 48)
        const mesh = new THREE.Mesh(geometry, material)
        mesh.rotation.x = Math.PI / 2
        mesh.position.set(Number(sensor.center[0] || 0), Number(sensor.center[1] || 0), 0.04)
        group.add(mesh)
      }
      const center = Array.isArray(sensor.center)
        ? sensor.center
        : Array.isArray(sensor.translation) && sensor.translation[0] != null
          ? sensor.translation
          : null
      if (center) {
        const marker = new THREE.Mesh(
          new THREE.SphereGeometry(0.08, 12, 8),
          new THREE.MeshStandardMaterial({ color: 0xffb454 }),
        )
        marker.position.set(Number(center[0] || 0), Number(center[1] || 0), 0.1)
        group.add(marker)
      }
    }

    for (const sensor of childSensors) {
      if (sensor.area === 'scene') continue
      const material = new THREE.MeshStandardMaterial({ color: 0x8ca6ff, transparent: true, opacity: 0.13, side: THREE.DoubleSide })
      const center = Array.isArray(sensor.center)
        ? sensor.center
        : Array.isArray(sensor.translation) && sensor.translation[0] != null
          ? sensor.translation
          : sensor.x != null && sensor.y != null
            ? [sensor.x, sensor.y, 0]
            : null
      if (sensor.area === 'poly') {
        addPolygon(sensor.points || [], 0.06, material)
      } else if (sensor.area === 'circle' && center) {
        const geometry = new THREE.CylinderGeometry(Number(sensor.radius || 0), Number(sensor.radius || 0), 0.06, 48)
        const mesh = new THREE.Mesh(geometry, material)
        mesh.rotation.x = Math.PI / 2
        mesh.position.set(Number(center[0] || 0), Number(center[1] || 0), 0.03)
        group.add(mesh)
      }
      if (center) {
        const marker = new THREE.Mesh(
          new THREE.SphereGeometry(0.07, 12, 8),
          new THREE.MeshStandardMaterial({ color: 0x8ca6ff }),
        )
        marker.position.set(Number(center[0] || 0), Number(center[1] || 0), 0.09)
        group.add(marker)
      }
    }
  }, [regions, tripwires, sensors, childRegions, childTripwires, childSensors, mapPath, showSpatial])


  useEffect(() => {
    const group = cameraGroup.current
    if (!group) return
    while (group.children.length) {
      const child = group.children.pop()
      if (!child) continue
      child.traverse((node) => {
        if (node instanceof THREE.Mesh || node instanceof THREE.LineSegments) {
          node.geometry?.dispose?.()
          const material = (node as THREE.Mesh).material
          if (Array.isArray(material)) material.forEach((item) => item.dispose())
          else material?.dispose?.()
        }
      })
    }
    cameraViewRef.current = {}

    let active = true
    const objectUrls: string[] = []
    const build = async () => {
      for (const cameraData of cameras) {
        if (!active) return
        const id = String(cameraData.uid ?? cameraData.id ?? '')
        if (!id) continue
        const resolution = Array.isArray(cameraData.resolution) ? cameraData.resolution : [640, 480]
        const intrinsics = cameraData.intrinsics || {}
        const fy = Number(intrinsics.fy || 570)
        const height = Math.max(1, Number(resolution[1] || 480))
        const vfov = THREE.MathUtils.radToDeg(2 * Math.atan(height / (2 * Math.max(fy, 1))))
        const view = new THREE.PerspectiveCamera(vfov, Math.max(1, Number(resolution[0] || 640)) / height, 0.05, 50)
        view.up.set(0, 0, 1)
        const translation = Array.isArray(cameraData.translation) ? cameraData.translation : [0, 0, 0]
        const rotation = Array.isArray(cameraData.rotation) ? cameraData.rotation : [0, 0, 0]
        view.position.set(Number(translation[0] || 0), Number(translation[1] || 0), Number(translation[2] || 0))
        view.rotation.set(
          THREE.MathUtils.degToRad(Number(rotation[0] || 0)),
          THREE.MathUtils.degToRad(Number(rotation[1] || 0)),
          THREE.MathUtils.degToRad(Number(rotation[2] || 0)),
          'XYZ',
        )
        cameraViewRef.current[id] = view

        const rig = new THREE.Group()
        rig.name = 'camera-rig-' + id
        rig.add(view)
        const helper = new THREE.CameraHelper(view)
        helper.material.transparent = true
        helper.material.opacity = selectedCameraId === id ? 1 : 0.55
        rig.add(helper)

        const marker = new THREE.Mesh(
          new THREE.BoxGeometry(0.18, 0.12, 0.12),
          new THREE.MeshStandardMaterial({ color: selectedCameraId === id ? 0xffb454 : 0x4ed1ce }),
        )
        marker.position.copy(view.position)
        marker.rotation.copy(view.rotation)
        rig.add(marker)

        if (projectCameraFrames) {
          try {
            const url = await apiObjectUrl('/api/v2/cameras/' + encodeURIComponent(id) + '/snapshot?t=' + Date.now())
            if (!active) { URL.revokeObjectURL(url); return }
            objectUrls.push(url)
            const texture = await new THREE.TextureLoader().loadAsync(url)
            if (!active) return
            texture.colorSpace = THREE.SRGBColorSpace
            const distance = 1.25
            const planeHeight = 2 * Math.tan(THREE.MathUtils.degToRad(vfov / 2)) * distance
            const planeWidth = planeHeight * view.aspect
            const plane = new THREE.Mesh(
              new THREE.PlaneGeometry(planeWidth, planeHeight),
              new THREE.MeshBasicMaterial({ map: texture, transparent: true, opacity: Math.max(0, Math.min(1, cameraOpacity)), side: THREE.DoubleSide, depthWrite: false }),
            )
            plane.position.set(0, 0, -distance)
            view.add(plane)
          } catch {
            // Offline cameras retain their frustum but do not receive a projected frame.
          }
        }
        group.add(rig)
      }
    }
    void build()
    return () => {
      active = false
      objectUrls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [cameras, projectCameraFrames, cameraOpacity, selectedCameraId, mapPath])

  useEffect(() => {
    const group = calibrationGroup.current
    if (!group) return
    while (group.children.length) {
      const child = group.children.pop()
      if (child instanceof THREE.Mesh) {
        child.geometry.dispose()
        const material = child.material
        if (Array.isArray(material)) material.forEach((item) => item.dispose())
        else material.dispose()
      }
    }
    for (const point of pickedPoints) {
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(0.09, 14, 10),
        new THREE.MeshStandardMaterial({ color: 0xffb454, emissive: 0x6b3b00, emissiveIntensity: 0.3 }),
      )
      marker.position.set(Number(point[0] || 0), Number(point[1] || 0), Number(point[2] || 0))
      group.add(marker)
    }
  }, [pickedPoints])

  return <div className="three-viewer" ref={host}><div className="three-surface" ref={surface}/>{error && <div className="viewer-error">{error}</div>}</div>
}
