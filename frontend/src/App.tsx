import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Alert, Layout, Menu, Typography } from 'antd'
import { Link, Route, Routes, useLocation } from 'react-router-dom'
import EventsPage from './pages/EventsPage'
import EventDetailPage from './pages/EventDetailPage'
import LocationsPage from './pages/LocationsPage'
import OverviewPage from './pages/OverviewPage'
import SourcesPage from './pages/SourcesPage'
import WebhooksPage from './pages/WebhooksPage'
import WeatherPage from './pages/WeatherPage'

const { Header, Content, Footer } = Layout

export default function App() {
  const location = useLocation()
  const queryClient = useQueryClient()

  useEffect(() => {
    const source = new EventSource('/api/v1/stream')
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as { type?: string }
        if (event.type === 'source_health') {
          void queryClient.invalidateQueries({ queryKey: ['overview'] })
          void queryClient.invalidateQueries({ queryKey: ['sources'] })
          return
        }
        if (event.type === 'weather') {
          void queryClient.invalidateQueries({ queryKey: ['weather'] })
          void queryClient.invalidateQueries({ queryKey: ['sources'] })
          return
        }
      } catch {
        // Unknown SSE payloads fall back to refreshing all active data.
      }
      void queryClient.invalidateQueries()
    }
    return () => source.close()
  }, [queryClient])

  const selected = location.pathname.startsWith('/events') ? '/events' : location.pathname
  return (
    <Layout className="app-shell">
      <Header className="header">
        <Link to="/" className="brand">QuakeRelay</Link>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selected]}
          items={[
            { key: '/', label: <Link to="/">概览</Link> },
            { key: '/events', label: <Link to="/events">地震记录</Link> },
            { key: '/weather', label: <Link to="/weather">气象情况</Link> },
            { key: '/sources', label: <Link to="/sources">数据源状态</Link> },
            { key: '/locations', label: <Link to="/locations">关注地点</Link> },
            { key: '/webhooks', label: <Link to="/webhooks">推送渠道</Link> },
          ]}
        />
      </Header>
      <Content className="content">
        <Alert
          className="disclaimer"
          type="warning"
          showIcon
          message="第三方数据与模型估算，仅供辅助参考，请以官方信息为准。"
        />
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/events/:id" element={<EventDetailPage />} />
          <Route path="/weather" element={<WeatherPage />} />
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="/locations" element={<LocationsPage />} />
          <Route path="/webhooks" element={<WebhooksPage />} />
        </Routes>
      </Content>
      <Footer className="footer">
        <Typography.Text type="secondary">QuakeRelay · 非官方地震预警服务</Typography.Text>
      </Footer>
    </Layout>
  )
}
