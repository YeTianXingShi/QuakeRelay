import { useQuery } from '@tanstack/react-query'
import { Card, Col, Row, Space, Statistic, Table, Typography } from 'antd'
import { api } from '../api'
import type { EventSummary, Overview } from '../types'
import { Link } from 'react-router-dom'
import { formatChinaTime } from '../time'
import { sourceState } from '../presentation'

export default function OverviewPage() {
  const overview = useQuery({ queryKey: ['overview'], queryFn: () => api<Overview>('/overview') })
  const events = useQuery({ queryKey: ['events', 'recent'], queryFn: () => api<{ items: EventSummary[] }>('/events?limit=8') })
  return (
    <Space direction="vertical" size="large" className="full-width">
      <Typography.Title level={2}>运行概览</Typography.Title>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}><Card><Statistic title="历史事件" value={overview.data?.event_count ?? 0} /></Card></Col>
        <Col xs={24} md={8}><Card><Statistic title="关注地点" value={overview.data?.location_count ?? 0} /></Card></Col>
        <Col xs={24} md={8}><Card><Statistic title="失败通知" value={overview.data?.failed_deliveries ?? 0} valueStyle={{ color: overview.data?.failed_deliveries ? '#cf1322' : undefined }} /></Card></Col>
      </Row>
      <Link to="/sources" className="source-summary-link">
        <Card title="数据源状态" hoverable loading={overview.isLoading}>
          {(() => {
            const sources = (overview.data?.sources ?? []).filter((source) => source.channel !== 'transport' && source.logical_source !== 'weather_rank')
            const counts = sources.reduce((result, source) => ({ ...result, [sourceState(source)]: result[sourceState(source)] + 1 }), { normal: 0, abnormal: 0, unreported: 0 })
            return <Space size="large" wrap>
              <Statistic title="数据源" value={sources.length} suffix="个" />
              <Statistic title="正常" value={counts.normal} valueStyle={{ color: '#389e0d' }} />
              <Statistic title="异常" value={counts.abnormal} valueStyle={{ color: counts.abnormal ? '#cf1322' : undefined }} />
              <Statistic title="未报告" value={counts.unreported} valueStyle={{ color: counts.unreported ? '#d48806' : undefined }} />
              <Typography.Text type="secondary">查看详情 →</Typography.Text>
            </Space>
          })()}
        </Card>
      </Link>
      <Card title="最近地震">
        <Table rowKey="id" pagination={false} loading={events.isLoading} dataSource={events.data?.items} columns={[
          { title: '时间', dataIndex: 'origin_time', render: (v: string) => formatChinaTime(v) },
          { title: '震中', dataIndex: 'hypocenter', render: (v: string, row: EventSummary) => <Link to={`/events/${row.id}`}>{v}</Link> },
          { title: '震级', dataIndex: 'magnitude', render: (v: number | null) => v ?? '—' },
          { title: '深度', dataIndex: 'depth_km', render: (v: number | null) => v == null ? '—' : `${v} km` },
          { title: '影响地点', dataIndex: 'affected_locations' },
        ]} />
      </Card>
    </Space>
  )
}
