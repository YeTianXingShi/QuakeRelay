import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Card, DatePicker, Descriptions, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { Dayjs } from 'dayjs'
import { api } from '../api'
import { sourceState, sourceStateLabel } from '../presentation'
import { formatChinaTime } from '../time'
import type { SourceStatus, WeatherRankEntry, WeatherSnapshot } from '../types'

const STATE_COLORS = { normal: 'green', abnormal: 'red', unreported: 'gold' }

function RankingTable({ entries }: { entries: WeatherRankEntry[] }) {
  return <Table
    rowKey={(row) => `${row.rank}-${row.province}-${row.city}`}
    pagination={false}
    size="small"
    dataSource={entries}
    rowClassName={(row) => row.matched ? 'weather-matched-row' : ''}
    columns={[
      { title: '名次', dataIndex: 'rank', width: 80, render: (value: number) => `第 ${value} 名` },
      { title: '省级行政区', dataIndex: 'province', width: 130 },
      { title: '观测站', dataIndex: 'city' },
      { title: '实况值', dataIndex: 'value', width: 130 },
      { title: '关注地点', dataIndex: 'location_names', render: (names: string[]) => names.length ? <Space wrap>{names.map((name) => <Tag color="orange" key={name}>{name}</Tag>)}</Space> : '—' },
    ]}
  />
}

export default function WeatherPage() {
  const [day, setDay] = useState<Dayjs | null>(null)
  const [hourKey, setHourKey] = useState<string>()
  const queryString = day ? `?date=${day.format('YYYY-MM-DD')}&limit=24` : '?limit=24'
  const weather = useQuery({ queryKey: ['weather', queryString], queryFn: () => api<{ items: WeatherSnapshot[] }>(`/weather${queryString}`) })
  const latestWeather = useQuery({ queryKey: ['weather', 'latest'], queryFn: () => api<{ items: WeatherSnapshot[] }>('/weather?limit=1') })
  const sources = useQuery({ queryKey: ['sources'], queryFn: () => api<SourceStatus[]>('/sources') })
  const status = sources.data?.find((source) => source.logical_source === 'weather_rank')
  const snapshot = useMemo(() => weather.data?.items.find((item) => item.hour_key === hourKey) ?? weather.data?.items[0], [weather.data, hourKey])
  const state = status ? sourceState(status) : 'unreported'

  return <Space direction="vertical" size="large" className="full-width">
    <div>
      <Typography.Title level={2}>气象情况</Typography.Title>
      <Typography.Text type="secondary">Wolfx 全国气象实况 Top 10 排行，每 5 分钟检查更新；橙色行表示与已启用关注地点匹配。</Typography.Text>
    </div>
    <Card title="气象数据源状态" loading={sources.isLoading}>
      <Descriptions column={{ xs: 1, md: 3 }}>
        <Descriptions.Item label="状态"><Tag color={STATE_COLORS[state]}>{sourceStateLabel(state)}</Tag></Descriptions.Item>
        <Descriptions.Item label="最后成功同步">{status?.last_message_at ? formatChinaTime(status.last_message_at) : '尚无同步记录'}</Descriptions.Item>
        <Descriptions.Item label="最新榜单小时">{latestWeather.data?.items[0] ? formatChinaTime(latestWeather.data.items[0].observed_at) : '尚无榜单'}</Descriptions.Item>
        <Descriptions.Item label="最近错误" span={3}>{status?.last_error || '—'}</Descriptions.Item>
      </Descriptions>
    </Card>
    <Card>
      <Space wrap className="weather-filters">
        <DatePicker allowClear value={day} onChange={(value) => { setDay(value); setHourKey(undefined) }} placeholder="选择历史日期" />
        <Select
          allowClear
          value={hourKey}
          onChange={setHourKey}
          placeholder="选择小时"
          style={{ width: 240 }}
          options={(weather.data?.items ?? []).map((item) => ({ value: item.hour_key, label: formatChinaTime(item.observed_at) }))}
        />
      </Space>
      {!snapshot && !weather.isLoading && <Alert type="info" showIcon message="所选日期暂无气象排行快照" />}
      {snapshot && <>
        <Typography.Title level={4}>{formatChinaTime(snapshot.observed_at)}</Typography.Title>
        <Tabs items={[
          { key: 'temperature', label: '高温排行', children: <RankingTable entries={snapshot.temperature_rank} /> },
          { key: 'rain', label: '降雨排行', children: <RankingTable entries={snapshot.rain_rank} /> },
          { key: 'wind', label: '风速排行', children: <RankingTable entries={snapshot.wind_rank} /> },
        ]} />
      </>}
    </Card>
  </Space>
}
