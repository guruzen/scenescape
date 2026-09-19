import { useEffect, useRef, useState } from 'react'
import { runtimeConfig } from '../config'

type Provider = 'google' | 'mapbox'
type Settings = { lat: number; lng: number; zoom: number; bearing: number }
type Generated = Settings & { file: File; corners: number[][]; scale: number }

const EARTH_CIRCUMFERENCE = 40075016.686
const calculateScale = (lat: number, zoom: number) => {
  const pixelsPerDegree = (256 * Math.pow(2, zoom)) / 360
  const metersPerDegreeLng = (EARTH_CIRCUMFERENCE / 360) * Math.cos((lat * Math.PI) / 180)
  return pixelsPerDegree / metersPerDegreeLng
}
const loadScript = (id: string, src: string) => new Promise<void>((resolve, reject) => {
  const existing = document.getElementById(id) as HTMLScriptElement | null
  if (existing) {
    if (existing.dataset.loaded === 'true') resolve()
    else existing.addEventListener('load', () => resolve(), { once: true })
    return
  }
  const script = document.createElement('script')
  script.id = id
  script.src = src
  script.async = true
  script.defer = true
  script.onload = () => { script.dataset.loaded = 'true'; resolve() }
  script.onerror = () => reject(new Error('Unable to load geospatial map provider'))
  document.head.appendChild(script)
})
const loadImage = (url: string) => new Promise<HTMLImageElement>((resolve, reject) => {
  const image = new Image()
  image.crossOrigin = 'anonymous'
  image.onload = () => resolve(image)
  image.onerror = () => reject(new Error('Unable to load static map image'))
  image.src = url
})
const canvasFile = (canvas: HTMLCanvasElement) => new Promise<File>((resolve, reject) => {
  canvas.toBlob((blob) => blob
    ? resolve(new File([blob], `geospatial_map_${Date.now()}.png`, { type: 'image/png' }))
    : reject(new Error('Unable to generate geospatial PNG')), 'image/png')
})

export default function GeospatialMap({
  provider,
  settings,
  onSettings,
  onGenerated,
}: {
  provider: Provider
  settings: Settings
  onSettings: (settings: Settings) => void
  onGenerated: (value: Generated) => void
}) {
  const host = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<any>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let active = true
    let mapboxMap: any = null
    setReady(false)
    setError('')
    const initialize = async () => {
      if (!host.current) return
      const w = window as any
      try {
        if (provider === 'google') {
          const key = runtimeConfig.googleMapsApiKey
          if (!key) throw new Error('GOOGLE_MAPS_API_KEY is not configured.')
          if (!w.google?.maps) await loadScript('scenescape-google-maps', `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&libraries=places`)
          if (!active || !host.current) return
          const map = new w.google.maps.Map(host.current, {
            center: { lat: settings.lat, lng: settings.lng },
            zoom: settings.zoom,
            heading: settings.bearing,
            tilt: 0,
            mapTypeId: 'satellite',
            rotateControl: true,
            streetViewControl: false,
          })
          mapRef.current = map
          map.addListener('idle', () => {
            if (!active) return
            const center = map.getCenter()
            onSettings({
              lat: Number(center.lat()),
              lng: Number(center.lng()),
              zoom: Number(map.getZoom() || settings.zoom),
              bearing: Number(map.getHeading?.() || 0),
            })
          })
        } else {
          const key = runtimeConfig.mapboxApiKey
          if (!key) throw new Error('MAPBOX_API_KEY is not configured.')
          if (!document.getElementById('scenescape-mapbox-css')) {
            const link = document.createElement('link')
            link.id = 'scenescape-mapbox-css'
            link.rel = 'stylesheet'
            link.href = 'https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css'
            document.head.appendChild(link)
          }
          if (!w.mapboxgl) await loadScript('scenescape-mapbox-js', 'https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js')
          if (!active || !host.current) return
          w.mapboxgl.accessToken = key
          mapboxMap = new w.mapboxgl.Map({
            container: host.current,
            style: 'mapbox://styles/mapbox/satellite-v9',
            center: [settings.lng, settings.lat],
            zoom: settings.zoom,
            pitch: 0,
            bearing: settings.bearing,
            projection: 'mercator',
            pitchWithRotate: false,
          })
          mapboxMap.addControl(new w.mapboxgl.NavigationControl({ showCompass: true, showZoom: true }))
          mapboxMap.on('moveend', () => {
            if (!active) return
            const center = mapboxMap.getCenter()
            onSettings({
              lat: Number(center.lat),
              lng: Number(center.lng),
              zoom: Number(mapboxMap.getZoom()),
              bearing: Number(mapboxMap.getBearing() || 0),
            })
          })
          mapRef.current = mapboxMap
        }
        if (active) setReady(true)
      } catch (e) {
        if (active) setError(String(e))
      }
    }
    void initialize()
    return () => {
      active = false
      if (mapboxMap?.remove) mapboxMap.remove()
      mapRef.current = null
      if (host.current) host.current.replaceChildren()
    }
  }, [provider])

  const moveTo = async () => {
    const value = query.trim()
    if (!value || !mapRef.current) return
    const coordinate = value.match(/^(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)$/)
    try {
      if (coordinate) {
        const lat = Number(coordinate[1]), lng = Number(coordinate[2])
        provider === 'google' ? mapRef.current.setCenter({ lat, lng }) : mapRef.current.flyTo({ center: [lng, lat] })
        return
      }
      if (provider === 'google') {
        const w = window as any
        const geocoder = new w.google.maps.Geocoder()
        geocoder.geocode({ address: value }, (results: any[], status: string) => {
          if (status === 'OK' && results?.[0]) mapRef.current?.setCenter(results[0].geometry.location)
          else setError(`Location not found: ${status}`)
        })
      } else {
        const response = await fetch(`https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(value)}.json?access_token=${encodeURIComponent(runtimeConfig.mapboxApiKey)}`)
        const data = await response.json()
        const center = data.features?.[0]?.center
        if (!center) throw new Error('Location not found')
        mapRef.current.flyTo({ center })
      }
    } catch (e) {
      setError(String(e))
    }
  }

  const generate = async () => {
    const map = mapRef.current
    if (!map) return
    setError('')
    try {
      let current: Settings
      let corners: number[][]
      const canvas = document.createElement('canvas')
      canvas.width = 1280
      canvas.height = 1280
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Canvas is unavailable')

      if (provider === 'google') {
        const center = map.getCenter()
        const bounds = map.getBounds()
        if (!center || !bounds) throw new Error('Map bounds are not ready')
        const ne = bounds.getNorthEast(), sw = bounds.getSouthWest()
        current = {
          lat: Number(center.lat()), lng: Number(center.lng()),
          zoom: Number(map.getZoom()), bearing: Number(map.getHeading?.() || 0),
        }
        corners = [
          [Number(sw.lat()), Number(sw.lng()), 0],
          [Number(ne.lat()), Number(sw.lng()), 0],
          [Number(ne.lat()), Number(ne.lng()), 0],
          [Number(sw.lat()), Number(ne.lng()), 0],
        ]
        const latQuarter = (Number(ne.lat()) - Number(sw.lat())) / 4
        const lngQuarter = (Number(ne.lng()) - Number(sw.lng())) / 4
        const centers = [
          [current.lat + latQuarter, current.lng - lngQuarter, 0, 0],
          [current.lat + latQuarter, current.lng + lngQuarter, 640, 0],
          [current.lat - latQuarter, current.lng - lngQuarter, 0, 640],
          [current.lat - latQuarter, current.lng + lngQuarter, 640, 640],
        ]
        const images = await Promise.all(centers.map(([lat,lng]) => loadImage(
          `https://maps.googleapis.com/maps/api/staticmap?center=${lat},${lng}&zoom=${current.zoom}&size=640x640&maptype=satellite&key=${encodeURIComponent(runtimeConfig.googleMapsApiKey)}&format=png`
        )))
        images.forEach((image, index) => context.drawImage(image, Number(centers[index][2]), Number(centers[index][3]), 640, 640))
      } else {
        const center = map.getCenter(), bounds = map.getBounds()
        const ne = bounds.getNorthEast(), sw = bounds.getSouthWest()
        current = {
          lat: Number(center.lat), lng: Number(center.lng),
          zoom: Number(map.getZoom()), bearing: Number(map.getBearing() || 0),
        }
        corners = [
          [Number(sw.lat), Number(sw.lng), 0],
          [Number(ne.lat), Number(sw.lng), 0],
          [Number(ne.lat), Number(ne.lng), 0],
          [Number(sw.lat), Number(ne.lng), 0],
        ]
        const url = `https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/${current.lng},${current.lat},${current.zoom},${current.bearing},0/1280x1280?access_token=${encodeURIComponent(runtimeConfig.mapboxApiKey)}`
        context.drawImage(await loadImage(url), 0, 0, 1280, 1280)
      }
      const file = await canvasFile(canvas)
      onSettings(current)
      onGenerated({ ...current, file, corners, scale: calculateScale(current.lat, current.zoom) })
    } catch (e) {
      setError(String(e))
    }
  }

  return <div className="geo-workspace">
    <div className="geo-toolbar">
      <input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Address or lat,lng"/>
      <button type="button" className="btn" disabled={!ready} onClick={() => void moveTo()}>Go</button>
      <button type="button" className="btn btn-primary" disabled={!ready} onClick={() => void generate()}>Generate geospatial map</button>
    </div>
    <div ref={host} className="geo-map"/>
    {error && <div className="error-box geo-error">{error}</div>}
  </div>
}
