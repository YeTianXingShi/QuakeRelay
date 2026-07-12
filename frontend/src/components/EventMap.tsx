import { useEffect, useRef } from 'react'
import AMapLoader from '@amap/amap-jsapi-loader'
import { Alert, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { PublicConfig } from '../types'

declare global {
  interface Window {
    _AMapSecurityConfig?: { securityJsCode: string }
  }
}

interface Marker {
  longitude: number
  latitude: number
  title: string
  kind: 'earthquake' | 'location'
}

export default function EventMap({ markers, onPick }: { markers: Marker[]; onPick?: (lat: number, lon: number) => void }) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<{ destroy: () => void } | null>(null)
  const { data: config, isLoading } = useQuery({ queryKey: ['public-config'], queryFn: () => api<PublicConfig>('/config/public') })

  useEffect(() => {
    if (!container.current || !config?.amap_js_key) return
    let cancelled = false
    window._AMapSecurityConfig = { securityJsCode: config.amap_security_code }
    AMapLoader.load({ key: config.amap_js_key, version: '2.0', plugins: ['AMap.Scale'] }).then((AMap: any) => {
      if (cancelled || !container.current) return
      const center = markers.length ? [markers[0].longitude, markers[0].latitude] : [104.1954, 35.8617]
      const map = new AMap.Map(container.current, { zoom: markers.length ? 6 : 4, center })
      map.addControl(new AMap.Scale())
      const points = markers.map((item) => new AMap.Marker({
        position: [item.longitude, item.latitude],
        title: item.title,
        label: { content: item.title, direction: 'top' },
        icon: item.kind === 'earthquake' ? undefined : new AMap.Icon({
          image: 'https://webapi.amap.com/theme/v1.3/markers/n/mark_b.png',
          size: new AMap.Size(25, 34),
          imageSize: new AMap.Size(25, 34),
        }),
      }))
      map.add(points)
      if (points.length > 1) map.setFitView(points, false, [60, 60, 60, 60])
      if (onPick) map.on('click', (event: any) => onPick(event.lnglat.getLat(), event.lnglat.getLng()))
      mapRef.current = map
    })
    return () => {
      cancelled = true
      mapRef.current?.destroy()
      mapRef.current = null
    }
  }, [config, markers, onPick])

  if (isLoading) return <Spin />
  if (!config?.amap_js_key) return <Alert type="info" message="请先通过环境变量配置高德地图 Key" />
  return <div ref={container} className="event-map" />
}

