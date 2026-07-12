import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Descriptions, Space, Table, Tag, Timeline, Typography } from 'antd'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import EventMap from '../components/EventMap'
import { estimationText } from '../estimation'
import { NO_CORE_CHANGES_TEXT, hasRevisionChanges } from '../revisions'
import { formatChinaTime } from '../time'
import type { EventDetail } from '../types'
import { confidenceLabel, eventStatusLabel, revisionChangeLines, sourceName } from '../presentation'

export default function EventDetailPage() {
  const { id } = useParams()
  const query = useQuery({ queryKey: ['event', id], queryFn: () => api<EventDetail>(`/events/${id}`), enabled: Boolean(id) })
  const event = query.data
  const markers = useMemo(() => event ? [
    { longitude: event.gcj02_longitude, latitude: event.gcj02_latitude, title: `${event.hypocenter} M${event.magnitude ?? '?'}`, kind: 'earthquake' as const },
    ...event.impacts.map((impact) => ({ longitude: impact.gcj02_longitude, latitude: impact.gcj02_latitude, title: `${impact.location_name} 预计${impact.estimated_intensity ?? '?'}度`, kind: 'location' as const })),
  ] : [], [event])
  if (!event) return <Card loading={query.isLoading}>未找到事件</Card>
  return (
    <Space direction="vertical" size="large" className="full-width">
      <Typography.Title level={2}>{event.hypocenter} M{event.magnitude ?? '未知'}</Typography.Title>
      <Card>
        <Descriptions column={{ xs: 1, sm: 2, lg: 4 }}>
          <Descriptions.Item label="发震时间">{formatChinaTime(event.origin_time)}</Descriptions.Item>
          <Descriptions.Item label="震级">{event.magnitude ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="深度">{event.depth_km == null ? '—' : `${event.depth_km} km`}</Descriptions.Item>
          <Descriptions.Item label="状态"><Tag>{eventStatusLabel(event.status)}</Tag></Descriptions.Item>
          <Descriptions.Item label="坐标">{event.latitude.toFixed(4)}, {event.longitude.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="当前版本">#{event.revision}</Descriptions.Item>
          <Descriptions.Item label="最新来源">{sourceName(event.latest_source)}</Descriptions.Item>
        </Descriptions>
      </Card>
      <EventMap markers={markers} />
      <Card title="关注地点预计影响">
        <Table rowKey="location_id" pagination={false} dataSource={event.impacts} columns={[
          { title: '地点', dataIndex: 'location_name' },
          { title: '距离', dataIndex: 'distance_km', render: (v: number) => `${v.toFixed(1)} km` },
          { title: '预计烈度', dataIndex: 'estimated_intensity', render: (_v: number | null, row) => <Tag color={row.estimation_status === 'failed' ? 'red' : row.triggered ? 'orange' : 'default'}>{estimationText(row)}</Tag> },
          { title: '置信度', dataIndex: 'confidence', render: confidenceLabel },
          { title: '模型', dataIndex: 'model_version' },
        ]} />
      </Card>
      <Card title="多源报告">
        <Table rowKey="id" pagination={false} dataSource={event.reports} columns={[
          { title: '来源', dataIndex: 'source', render: sourceName },
          { title: '报次', dataIndex: 'report_number' },
          { title: '报告时间', dataIndex: 'report_time', render: (v: string) => formatChinaTime(v) },
          { title: '震中', dataIndex: 'hypocenter' },
          { title: '震级', dataIndex: 'magnitude' },
          { title: '深度', dataIndex: 'depth_km' },
          { title: '状态', dataIndex: 'status', render: eventStatusLabel },
        ]} />
      </Card>
      <Card title="版本时间线">
        <Timeline items={event.revisions.map((revision: any) => ({
          children: <><strong>版本 #{revision.revision}</strong> · {formatChinaTime(revision.created_at)}{hasRevisionChanges(revision.changes)
            ? <div className="revision-changes">{revisionChangeLines(revision.changes).map((line) => <div key={line}>{line}</div>)}</div>
            : <div className="revision-empty">{NO_CORE_CHANGES_TEXT}</div>}</>,
        }))} />
      </Card>
    </Space>
  )
}
