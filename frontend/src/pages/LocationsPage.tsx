import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Form, Input, List, Modal, Popconfirm, Space, Switch, Tag, Typography, message } from 'antd'
import { api } from '../api'
import LocationPicker from '../components/LocationPicker'
import type { Location } from '../types'

interface PickedPlace { name: string; address: string; province: string; city: string; district: string; latitude: number; longitude: number }

export default function LocationsPage() {
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState<PickedPlace | null>(null)
  const [form] = Form.useForm()
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['locations'], queryFn: () => api<Location[]>('/locations') })
  const refresh = () => void client.invalidateQueries({ queryKey: ['locations'] })
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Location>('/locations', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => { refresh(); setOpen(false); form.resetFields(); setPicked(null); message.success('关注地点已添加') },
  })
  const remove = useMutation({ mutationFn: (id: string) => api<void>(`/locations/${id}`, { method: 'DELETE' }), onSuccess: refresh })
  const toggle = useMutation({ mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api(`/locations/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) }), onSuccess: refresh })
  const handlePick = useCallback((place: PickedPlace) => {
    setPicked(place)
    form.setFieldsValue({ name: place.name, address: place.address, province: place.province, city: place.city, district: place.district })
  }, [form])
  return (
    <Space direction="vertical" size="large" className="full-width">
      <Space className="page-heading"><Typography.Title level={2}>关注地点</Typography.Title><Button type="primary" onClick={() => setOpen(true)}>添加地点</Button></Space>
      <Card>
        <List loading={query.isLoading} dataSource={query.data} renderItem={(item) => (
          <List.Item actions={[
            <Switch key="enabled" checked={item.enabled} onChange={(enabled) => toggle.mutate({ id: item.id, enabled })} />,
            <Popconfirm key="delete" title="永久删除这个关注地点？" description="该地点的所有历史地震影响记录也会被永久删除，无法恢复。" okText="永久删除" okButtonProps={{ danger: true }} cancelText="取消" onConfirm={() => remove.mutate(item.id)}><Button danger type="link">删除</Button></Popconfirm>,
          ]}>
            <List.Item.Meta title={<Space>{item.name}{(!item.province || (!item.city && !item.district)) && <Tag color="gold">需重新添加以启用气象匹配</Tag>}</Space>} description={<>
              <div>{item.address || '无地址'} · {item.latitude.toFixed(5)}, {item.longitude.toFixed(5)}</div>
              {item.province && <div>行政区：{[item.province, item.city, item.district].filter(Boolean).join(' / ')}</div>}
            </>} />
          </List.Item>
        )} />
      </Card>
      <Modal title="添加关注地点" open={open} width={820} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending} okButtonProps={{ disabled: !picked || !picked.province || (!picked.city && !picked.district) }}>
        <LocationPicker onPick={handlePick} />
        {picked && (!picked.province || (!picked.city && !picked.district)) && <Alert className="location-admin-warning" type="warning" showIcon message="高德未返回完整行政区信息，请换一个搜索结果或重新选点。" />}
        <Form form={form} layout="vertical" className="location-form" onFinish={(values) => picked && create.mutate({ ...values, province: picked.province, city: picked.city, district: picked.district, latitude: picked.latitude, longitude: picked.longitude, coordinate_system: 'gcj02' })}>
          <Form.Item label="名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="地址" name="address"><Input /></Form.Item>
          <Space className="full-width" size="middle">
            <Form.Item label="省级行政区" name="province"><Input readOnly /></Form.Item>
            <Form.Item label="城市" name="city"><Input readOnly /></Form.Item>
            <Form.Item label="区县" name="district"><Input readOnly /></Form.Item>
          </Space>
        </Form>
      </Modal>
    </Space>
  )
}
