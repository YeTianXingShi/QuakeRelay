import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Form, Input, List, Modal, Popconfirm, Space, Switch, Typography, message } from 'antd'
import { api } from '../api'
import LocationPicker from '../components/LocationPicker'
import type { Location } from '../types'

interface PickedPlace { name: string; address: string; latitude: number; longitude: number }

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
    form.setFieldsValue({ name: place.name, address: place.address })
  }, [form])
  return (
    <Space direction="vertical" size="large" className="full-width">
      <Space className="page-heading"><Typography.Title level={2}>关注地点</Typography.Title><Button type="primary" onClick={() => setOpen(true)}>添加地点</Button></Space>
      <Card>
        <List loading={query.isLoading} dataSource={query.data} renderItem={(item) => (
          <List.Item actions={[
            <Switch key="enabled" checked={item.enabled} onChange={(enabled) => toggle.mutate({ id: item.id, enabled })} />,
            <Popconfirm key="delete" title="删除这个关注地点？" onConfirm={() => remove.mutate(item.id)}><Button danger type="link">删除</Button></Popconfirm>,
          ]}>
            <List.Item.Meta title={item.name} description={`${item.address || '无地址'} · ${item.latitude.toFixed(5)}, ${item.longitude.toFixed(5)}`} />
          </List.Item>
        )} />
      </Card>
      <Modal title="添加关注地点" open={open} width={820} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending} okButtonProps={{ disabled: !picked }}>
        <LocationPicker onPick={handlePick} />
        <Form form={form} layout="vertical" className="location-form" onFinish={(values) => picked && create.mutate({ ...values, latitude: picked.latitude, longitude: picked.longitude, coordinate_system: 'gcj02' })}>
          <Form.Item label="名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="地址" name="address"><Input /></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
