import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Checkbox, Form, Input, InputNumber, List, Modal, Popconfirm, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { formatChinaTime } from '../time'
import { api } from '../api'
import type { Webhook } from '../types'
import { deliveryKindLabel, deliveryStatusLabel } from '../presentation'

interface Delivery { id: string; endpoint_name: string; kind: string; status: string; attempts: number; last_error: string | null; created_at: string }

export default function WebhooksPage() {
  const [open, setOpen] = useState(false)
  const [telegramOpen, setTelegramOpen] = useState(false)
  const [savingAndTesting, setSavingAndTesting] = useState(false)
  const [form] = Form.useForm()
  const [telegramForm] = Form.useForm()
  const client = useQueryClient()
  const webhooks = useQuery({ queryKey: ['webhooks'], queryFn: () => api<Webhook[]>('/webhooks') })
  const deliveries = useQuery({ queryKey: ['deliveries'], queryFn: () => api<Delivery[]>('/deliveries') })
  const refresh = () => { void client.invalidateQueries({ queryKey: ['webhooks'] }); void client.invalidateQueries({ queryKey: ['deliveries'] }) }
  const create = useMutation({ mutationFn: (body: Record<string, unknown>) => api('/webhooks', { method: 'POST', body: JSON.stringify(body) }), onSuccess: () => { refresh(); setOpen(false); form.resetFields(); message.success('Webhook 已添加') } })
  const createTelegram = useMutation({ mutationFn: (body: Record<string, unknown>) => api('/webhooks/telegram', { method: 'POST', body: JSON.stringify(body) }), onSuccess: () => { refresh(); setTelegramOpen(false); telegramForm.resetFields(); message.success('Telegram 推送渠道已添加') } })
  const remove = useMutation({ mutationFn: (id: string) => api(`/webhooks/${id}`, { method: 'DELETE' }), onSuccess: refresh })
  const toggle = useMutation({ mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api(`/webhooks/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) }), onSuccess: refresh })
  const test = useMutation({ mutationFn: (id: string) => api(`/webhooks/${id}/test`, { method: 'POST' }), onSuccess: () => { message.success('测试消息已入队'); refresh() } })
  const retry = useMutation({ mutationFn: (id: string) => api(`/deliveries/${id}/retry`, { method: 'POST' }), onSuccess: refresh })

  async function saveGenericAndTest() {
    try {
      const values = await form.validateFields()
      const endpoint = await api<Webhook>('/webhooks', {
        method: 'POST',
        body: JSON.stringify({ name: values.name, url: values.url, timeout_seconds: values.timeout_seconds, headers: JSON.parse(values.headers_text) }),
      })
      await api(`/webhooks/${endpoint.id}/test`, { method: 'POST' })
      setOpen(false)
      form.resetFields()
      refresh()
      message.success('Webhook 已保存，测试推送已入队')
    } catch (error) {
      if (error instanceof SyntaxError) message.error('请求头必须是合法 JSON 对象')
      else if (error instanceof Error && !('errorFields' in error)) message.error(error.message)
    }
  }

  async function saveTelegramAndTest() {
    try {
      setSavingAndTesting(true)
      const values = await telegramForm.validateFields()
      const endpoint = await api<Webhook>('/webhooks/telegram', { method: 'POST', body: JSON.stringify(values) })
      await api(`/webhooks/${endpoint.id}/test`, { method: 'POST' })
      setTelegramOpen(false)
      telegramForm.resetFields()
      refresh()
      message.success('Telegram 渠道已保存，测试推送已入队')
    } catch (error) {
      if (error instanceof Error && !('errorFields' in error)) message.error(error.message)
    } finally {
      setSavingAndTesting(false)
    }
  }
  return (
    <Space direction="vertical" size="large" className="full-width">
      <Space className="page-heading"><Typography.Title level={2}>推送渠道</Typography.Title><Space><Button onClick={() => setOpen(true)}>添加 Webhook</Button><Button type="primary" onClick={() => setTelegramOpen(true)}>添加 Telegram</Button></Space></Space>
      <Card title="推送配置">
        <List dataSource={webhooks.data} loading={webhooks.isLoading} renderItem={(item) => (
          <List.Item actions={[
            <Switch key="enabled" checked={item.enabled} onChange={(enabled) => toggle.mutate({ id: item.id, enabled })} />,
            <Button key="test" size="small" loading={test.isPending && test.variables === item.id} onClick={() => test.mutate(item.id)}>测试推送</Button>,
            <Popconfirm key="delete" title="删除端点及其发送记录？" onConfirm={() => remove.mutate(item.id)}><Button danger type="link">删除</Button></Popconfirm>,
          ]}>
            <List.Item.Meta title={<Space>{item.name}<Tag color={item.channel_type === 'telegram' ? 'blue' : 'default'}>{item.channel_type === 'telegram' ? 'Telegram' : 'Webhook'}</Tag></Space>} description={item.channel_type === 'telegram'
              ? <>会话 ID：{item.chat_id} {item.message_thread_id ? `· 话题 ID ${item.message_thread_id}` : ''} · {item.disable_notification ? '静默发送' : '正常通知'} · 超时 {item.timeout_seconds} 秒</>
              : <>{item.url}<br />请求头：{item.header_names.join(', ') || '无'} · 超时 {item.timeout_seconds} 秒</>} />
          </List.Item>
        )} />
      </Card>
      <Card title="最近发送记录">
        <Table rowKey="id" pagination={{ pageSize: 20 }} dataSource={deliveries.data} columns={[
          { title: '时间', dataIndex: 'created_at', render: (v: string) => formatChinaTime(v) },
          { title: '端点', dataIndex: 'endpoint_name' },
          { title: '类型', dataIndex: 'kind', render: deliveryKindLabel },
          { title: '状态', dataIndex: 'status', render: (v: string) => <Tag color={v === 'delivered' ? 'green' : v === 'failed' ? 'red' : 'blue'}>{deliveryStatusLabel(v)}</Tag> },
          { title: '尝试', dataIndex: 'attempts' },
          { title: '错误', dataIndex: 'last_error', ellipsis: true },
          { title: '', render: (_: unknown, row: Delivery) => row.status === 'failed' && <Button type="link" onClick={() => retry.mutate(row.id)}>重新发送</Button> },
        ]} />
      </Card>
      <Modal
        title="添加 Webhook"
        open={open}
        onCancel={() => setOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setOpen(false)}>取消</Button>,
          <Button key="save" type="primary" loading={create.isPending} onClick={() => form.submit()}>保存</Button>,
          <Button key="save-test" onClick={() => void saveGenericAndTest()}>保存并测试推送</Button>,
        ]}
      >
        <Form form={form} layout="vertical" initialValues={{ timeout_seconds: 10, headers_text: '{}' }} onFinish={(values) => {
          try { create.mutate({ name: values.name, url: values.url, timeout_seconds: values.timeout_seconds, headers: JSON.parse(values.headers_text) }) }
          catch { message.error('请求头必须是合法 JSON 对象') }
        }}>
          <Form.Item label="名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="URL" name="url" rules={[{ required: true, type: 'url' }]}><Input placeholder="https://example.com/webhook" /></Form.Item>
          <Form.Item label="请求头（JSON）" name="headers_text" rules={[{ required: true }]}><Input.TextArea rows={4} placeholder={'{"Authorization":"Bearer ..."}'} /></Form.Item>
          <Form.Item label="超时秒数" name="timeout_seconds"><InputNumber min={1} max={60} /></Form.Item>
        </Form>
      </Modal>
      <Modal
        title="添加 Telegram 机器人"
        open={telegramOpen}
        onCancel={() => setTelegramOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setTelegramOpen(false)}>取消</Button>,
          <Button key="save" type="primary" loading={createTelegram.isPending} onClick={() => telegramForm.submit()}>保存</Button>,
          <Button key="save-test" loading={savingAndTesting} onClick={() => void saveTelegramAndTest()}>保存并测试推送</Button>,
        ]}
      >
        <Typography.Paragraph type="secondary">
          先通过 <Typography.Link href="https://t.me/BotFather" target="_blank">@BotFather</Typography.Link> 创建机器人并取得 Token，然后把机器人加入目标私聊、群组或频道。
        </Typography.Paragraph>
        <Form form={telegramForm} layout="vertical" initialValues={{ name: 'Telegram', timeout_seconds: 10, disable_notification: false }} onFinish={(values) => createTelegram.mutate(values)}>
          <Form.Item label="名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="机器人令牌（Bot Token）" name="bot_token" rules={[{ required: true }, { pattern: /^\d+:[A-Za-z0-9_-]{20,}$/, message: '令牌格式不正确' }]}><Input.Password autoComplete="new-password" placeholder="123456789:AA..." /></Form.Item>
          <Form.Item label="会话 ID（Chat ID）" name="chat_id" extra="私聊通常为正整数，群组通常以 -100 开头，频道也可填写 @username。" rules={[{ required: true }]}><Input placeholder="-1001234567890" /></Form.Item>
          <Form.Item label="话题 ID（可选）" name="message_thread_id" extra="仅论坛群组需要填写。"><InputNumber min={1} precision={0} className="full-width" /></Form.Item>
          <Form.Item label="超时秒数" name="timeout_seconds"><InputNumber min={1} max={60} /></Form.Item>
          <Form.Item name="disable_notification" valuePropName="checked"><Checkbox>静默发送，不产生声音提醒</Checkbox></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
