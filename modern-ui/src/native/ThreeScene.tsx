import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { apiObjectUrl } from '../api/client'

type Row = Record<string, any>

export default function ThreeScene({ mapPath, objects, scale = 100 }: { mapPath?: string; objects: Row[]; scale?: number }) {
  const host = useRef<HTMLDivElement | null>(null)
  const surface = useRef<HTMLDivElement | null>(null)
  const objectGroup = useRef<THREE.Group | null>(null)
  const [error, setError] = useState('')

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

    scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.8))
    const sun = new THREE.DirectionalLight(0xffffff, 2.2)
    sun.position.set(10, -8, 14)
    scene.add(sun)
    const grid = new THREE.GridHelper(20, 20, 0x3a6168, 0x244047)
    grid.rotation.x = Math.PI / 2
    scene.add(grid)
    const group = new THREE.Group()
    objectGroup.current = group
    scene.add(group)

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
        mediaUrl = await apiObjectUrl(mapPath)
        if (disposed) return
        if (/\.glb(?:$|\?)/i.test(mapPath)) {
          new GLTFLoader().load(mediaUrl, (gltf) => {
            if (disposed) return
            scene.add(gltf.scene)
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

    const loop = () => {
      controls.update()
      renderer.render(scene, camera)
      frame = requestAnimationFrame(loop)
    }
    loop()

    return () => {
      disposed = true
      cancelAnimationFrame(frame)
      resize?.disconnect()
      controls.dispose()
      renderer.dispose()
      renderer.domElement.remove()
      if (mediaUrl) URL.revokeObjectURL(mediaUrl)
      objectGroup.current = null
    }
  }, [mapPath, scale])

  useEffect(() => {
    const group = objectGroup.current
    if (!group) return
    while (group.children.length) {
      const child = group.children.pop()
      if (child instanceof THREE.Mesh) {
        child.geometry.dispose()
        const material = child.material
        if (Array.isArray(material)) material.forEach((m) => m.dispose())
        else material.dispose()
      }
    }
    for (const item of objects || []) {
      const t = Array.isArray(item.translation) ? item.translation : [0, 0, 0]
      const geometry = new THREE.SphereGeometry(0.12, 16, 12)
      const material = new THREE.MeshStandardMaterial({ color: 0x4ed1ce, emissive: 0x0b4f55, emissiveIntensity: 0.35 })
      const marker = new THREE.Mesh(geometry, material)
      marker.position.set(Number(t[0] || 0), Number(t[1] || 0), Math.max(0.12, Number(t[2] || 0.12)))
      group.add(marker)
    }
  }, [objects, mapPath])

  return <div className="three-viewer" ref={host}><div className="three-surface" ref={surface}/>{error && <div className="viewer-error">{error}</div>}</div>
}
