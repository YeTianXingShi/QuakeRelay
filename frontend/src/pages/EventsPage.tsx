import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Form, Input, InputNumber, Select, Space, Table, Tag, Typography } from 'antd'
import { Link } from 'react-router-dom'
import { formatChinaTime } from '../time'
import { api } from '../api'
import type { EventSummary } from '../types'
import { eventStatusLabel, sourceName } from '../presentation'

const SOURCE_OPTIONS = ['cenc_eqlist', 'cenc_eew', 'sc_eew', 'fj_eew', 'cq_eew'].map(value => ({ value, label: sourceName(value) }))
const STATUS_OPTIONS = ['preliminary', 'reviewed', 'final', 'cancelled'].map(value => ({ value, label: eventStatusLabel(value) }))

export default function EventsPage() {
  const [filters, setFilters] = useState<Record<string, string>>({})
  const params = new URLSearchParams({ limit: '100', ...filters })
  const query = useQuery({ queryKey: ['events', params.toString()], queryFn: () => api<{ items: EventSummary[] }>(`/events?${params}`) })
  return (
    <Space direction="vertical" size="large" className="full-width">
      <Typography.Title level={2}>地震记录</Typography.Title>
      <Card>
        <Form layout="inline" onFinish={(values) => setFilters(Object.fromEntries(Object.entries(values).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => [k, String(v)])))}>
          <Form.Item name="q"><Input allowClear placeholder="震中关键词" /></Form.Item>
          <Form.Item name="min_magnitude"><InputNumber min={0} max={10} step={0.1} placeholder="最低震级" /></Form.Item>
          <Form.Item name="source"><Select allowClear placeholder="数据来源" style={{ width: 260 }} options={SOURCE_OPTIONS} /></Form.Item>
          <Form.Item name="status"><Select allowClear placeholder="事件状态" style={{ width: 130 }} options={STATUS_OPTIONS} /></Form.Item>
          <Form.Item name="affected"><Select allowClear placeholder="影响情况" style={{ width: 130 }} options={[{ value: 'true', label: '影响关注点' }, { value: 'false', label: '未影响' }]} /></Form.Item>
          <Button htmlType="submit" type="primary">筛选</Button>
        </Form>
      </Card>
      <Card>
        <Table rowKey="id" loading={query.isLoading} dataSource={query.data?.items} pagination={{ pageSize: 30 }} columns={[
          { title: '发震时间', dataIndex: 'origin_time', render: (v: string) => formatChinaTime(v) },
          { title: '震中', dataIndex: 'hypocenter', render: (v: string, row: EventSummary) => <Link to={`/events/${row.id}`}>{v}</Link> },
          { title: '震级', dataIndex: 'magnitude', sorter: (a: EventSummary, b: EventSummary) => (a.magnitude ?? 0) - (b.magnitude ?? 0) },
          { title: '深度', dataIndex: 'depth_km', render: (v: number | null) => v == null ? '—' : `${v} km` },
          { title: '来源', dataIndex: 'latest_source', render: sourceName },
          { title: '状态', dataIndex: 'status', render: (v: string) => <Tag>{eventStatusLabel(v)}</Tag> },
          { title: '影响地点', dataIndex: 'affected_locations', render: (v: number) => <Tag color={v ? 'orange' : 'default'}>{v}</Tag> },
        ]} />
      </Card>
    </Space>
  )
}
