import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

describe('api', () => {
  afterEach(() => vi.restoreAllMocks())

  it('returns parsed JSON for successful requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))
    await expect(api<{ ok: boolean }>('/health')).resolves.toEqual({ ok: true })
    expect(fetch).toHaveBeenCalledWith('/api/v1/health', expect.any(Object))
  })

  it('returns undefined for no-content responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(api<void>('/locations/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('throws response text for failed requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('bad request', { status: 400 })))
    await expect(api('/broken')).rejects.toThrow('bad request')
  })
})

