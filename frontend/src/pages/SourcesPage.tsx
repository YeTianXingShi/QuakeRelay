import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Col, Collapse, Descriptions, Input, Row, Select, Space, Statistic, Table, Tag, Typography } from 'antd'
import { api } from '../api'
import { sourceChannelLabel, sourceDisplayName, sourceState, sourceStateLabel, type SourceState } from '../presentation'
import { formatChinaTime } from '../time'
import type { SourceStatus } from '../types'

const STATE_COLORS = { normal: 'green', abnormal: 'red', unreported: 'gold' }

function lastActivity(row: SourceStatus): string | null {
  return row.channel === 'transport' ? row.last_heartbeat_at : row.last_message_at
}

export default function SourcesPage() {
  const [keyword, setKeyword] = useState('')
  const [channel, setChannel] = useState<string>()
  const [state, setState] = useState<SourceState>()
  const query = useQuery({ queryKey: ['sources'], queryFn: () => api<SourceStatus[]>('/sources') })
  const transport = useMemo(() => query.data?.find((source) => source.channel === 'transport'), [query.data])
  const sources = useMemo(() => (query.data ?? []).filter((source) => source.channel !== 'transport'), [query.data])
  const counts = useMemo(() => sources.reduce((result, source) => {
    const current = sourceState(source)
    result[current] += 1
    return result
  }, { normal: 0, abnormal: 0, unreported: 0 }), [sources])
  const filtered = useMemo(() => sources.filter((source) => {
    const text = `${sourceDisplayName(source)} ${source.source}`.toLowerCase()
    return (!keyword || text.includes(keyword.toLowerCase()))
      && (!channel || source.channel === channel)
      && (!state || sourceState(source) === state)
  }), [sources, keyword, channel, state])

  return (
    <Space direction="vertical" size="large" className="full-width">
      <div>
        <Typography.Title level={2}>数据源状态</Typography.Title>
        <Typography.Text type="secondary">分别展示采集连接、各逻辑实时源与 HTTP 补偿源。状态通过 SSE 实时刷新，原始 JSON 可展开查看。</Typography.Text>
      </div>
      <Card title="采集连接状态" loading={query.isLoading}>
        {transport ? <Space direction="vertical" size="middle" className="full-width">
          <Descriptions column={{ xs: 1, md: 3 }}>
            <Descriptions.Item label="连接通道">Wolfx WebSocket（wolfx_ws）</Descriptions.Item>
            <Descriptions.Item label="状态">{(() => {
              const current = sourceState(transport)
              return <Tag color={STATE_COLORS[current]}>{sourceStateLabel(current)}</Tag>
            })()}</Descriptions.Item>
            <Descriptions.Item label="最后心跳">{transport.last_heartbeat_at ? formatChinaTime(transport.last_heartbeat_at) : '尚无心跳记录'}</Descriptions.Item>
            <Descriptions.Item label="用途" span={2}>承载下方多个实时数据源的长连接，本身不计入数据源数量。</Descriptions.Item>
            <Descriptions.Item label="错误信息">{transport.last_error || '—'}</Descriptions.Item>
          </Descriptions>
          <Collapse size="small" items={[{
            key: 'heartbeat',
            label: '查看最近一次原始心跳 JSON',
            children: transport.latest_payload
              ? <pre className="source-payload">{JSON.stringify(transport.latest_payload, null, 2)}</pre>
              : <Typography.Text type="secondary">尚未收到原始心跳数据。</Typography.Text>,
          }]} />
        </Space> : <Typography.Text type="secondary">采集器尚未写入连接状态。</Typography.Text>}
      </Card>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}><Card><Statistic title="数据源" value={sources.length} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="正常" value={counts.normal} valueStyle={{ color: '#389e0d' }} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="异常" value={counts.abnormal} valueStyle={{ color: counts.abnormal ? '#cf1322' : undefined }} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="未报告" value={counts.unreported} valueStyle={{ color: counts.unreported ? '#d48806' : undefined }} /></Card></Col>
      </Row>
      <Card>
        <Space wrap className="source-filters">
          <Input.Search allowClear placeholder="搜索数据源名称或技术标识" value={keyword} onChange={(event) => setKeyword(event.target.value)} style={{ width: 280 }} />
          <Select allowClear placeholder="全部通道" value={channel} onChange={setChannel} style={{ width: 150 }} options={[
            { value: 'ws', label: '实时源' },
            { value: 'http', label: 'HTTP 补偿' },
          ]} />
          <Select allowClear placeholder="全部状态" value={state} onChange={setState} style={{ width: 140 }} options={[
            { value: 'normal', label: '正常' },
            { value: 'abnormal', label: '异常' },
            { value: 'unreported', label: '未报告' },
          ]} />
        </Space>
        <Table
          rowKey="source"
          loading={query.isLoading}
          pagination={false}
          dataSource={filtered}
          locale={{ emptyText: '没有符合条件的数据源' }}
          expandable={{
            rowExpandable: () => true,
            expandedRowRender: (row) => (
              <Space direction="vertical" className="full-width">
                <Typography.Text type="secondary">
                  技术标识：{row.source} · 状态更新时间：{row.updated_at ? formatChinaTime(row.updated_at) : '尚无记录'}
                </Typography.Text>
                <Typography.Text strong>最近一次接口原始 JSON</Typography.Text>
                {row.latest_payload
                  ? <pre className="source-payload">{JSON.stringify(row.latest_payload, null, 2)}</pre>
                  : <Typography.Text type="secondary">该通道尚未收到原始数据。</Typography.Text>}
              </Space>
            ),
          }}
          columns={[
            { title: '通道', dataIndex: 'channel', render: sourceChannelLabel, width: 110 },
            { title: '数据源', render: (_: unknown, row: SourceStatus) => sourceDisplayName(row) },
            { title: '状态', width: 90, render: (_: unknown, row: SourceStatus) => {
              const current = sourceState(row)
              return <Tag color={STATE_COLORS[current]}>{sourceStateLabel(current)}</Tag>
            } },
            { title: '最后活动', width: 270, render: (_: unknown, row: SourceStatus) => {
              const value = lastActivity(row)
              const prefix = row.channel === 'transport' ? '心跳' : row.channel === 'http' ? '同步' : '收报'
              return value ? `${prefix} ${formatChinaTime(value)}` : `尚无${prefix}记录`
            } },
            { title: '错误信息', dataIndex: 'last_error', ellipsis: true, render: (value: string | null) => value || '—' },
          ]}
        />
      </Card>
    </Space>
  )
}
