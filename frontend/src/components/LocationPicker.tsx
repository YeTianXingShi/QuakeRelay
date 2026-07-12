import { useCallback, useEffect, useRef, useState } from 'react'
import AMapLoader from '@amap/amap-jsapi-loader'
import { Alert, Button, Input, List, Space } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { PublicConfig } from '../types'

interface PickedPlace { name: string; address: string; latitude: number; longitude: number }

export default function LocationPicker({ onPick }: { onPick: (place: PickedPlace) => void }) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<any>(null)
  const amapRef = useRef<any>(null)
  const placeSearchRef = useRef<any>(null)
  const markerRef = useRef<any>(null)
  const [keyword, setKeyword] = useState('')
  const [results, setResults] = useState<any[]>([])
  const { data: config } = useQuery({ queryKey: ['public-config'], queryFn: () => api<PublicConfig>('/config/public') })

  const selectPlace = useCallback((AMap: any, place: PickedPlace) => {
    if (markerRef.current) mapRef.current?.remove(markerRef.current)
    markerRef.current = new AMap.Marker({ position: [place.longitude, place.latitude] })
    mapRef.current?.add(markerRef.current)
    mapRef.current?.setZoomAndCenter(13, [place.longitude, place.latitude])
    onPick(place)
  }, [onPick])

  useEffect(() => {
    if (!container.current || !config?.amap_js_key) return
    let cancelled = false
    window._AMapSecurityConfig = { securityJsCode: config.amap_security_code }
    AMapLoader.load({ key: config.amap_js_key, version: '2.0', plugins: ['AMap.PlaceSearch', 'AMap.Geocoder'] }).then((AMap: any) => {
      if (cancelled || !container.current) return
      const map = new AMap.Map(container.current, { zoom: 4, center: [104.1954, 35.8617] })
      amapRef.current = AMap
      mapRef.current = map
      placeSearchRef.current = new AMap.PlaceSearch({ pageSize: 10, extensions: 'all' })
      map.on('click', (event: any) => {
        const lng = event.lnglat.getLng()
        const lat = event.lnglat.getLat()
        const geocoder = new AMap.Geocoder()
        geocoder.getAddress([lng, lat], (_status: string, result: any) => {
          const address = result?.regeocode?.formattedAddress ?? ''
          selectPlace(AMap, { name: address || '自定义地点', address, latitude: lat, longitude: lng })
        })
      })
    })
    return () => {
      cancelled = true
      mapRef.current?.destroy()
    }
  }, [config, selectPlace])

  function search() {
    if (!keyword.trim() || !placeSearchRef.current) return
    placeSearchRef.current.search(keyword, (status: string, result: any) => {
      setResults(status === 'complete' ? result.poiList?.pois ?? [] : [])
    })
  }

  if (!config?.amap_js_key) return <Alert type="warning" message="未配置高德地图 Key，无法搜索地点" />
  return (
    <Space direction="vertical" className="full-width">
      <Space.Compact block>
        <Input value={keyword} onChange={(e) => setKeyword(e.target.value)} onPressEnter={search} placeholder="搜索城市或详细地址" />
        <Button type="primary" onClick={search}>搜索</Button>
      </Space.Compact>
      {results.length > 0 && <List size="small" bordered dataSource={results} renderItem={(item: any) => (
        <List.Item className="search-result" onClick={() => selectPlace(amapRef.current, {
          name: item.name,
          address: `${item.pname ?? ''}${item.cityname ?? ''}${item.adname ?? ''}${item.address ?? ''}`,
          latitude: item.location.lat,
          longitude: item.location.lng,
        })}>
          <List.Item.Meta title={item.name} description={item.address} />
        </List.Item>
      )} />}
      <div ref={container} className="location-map" />
    </Space>
  )
}
