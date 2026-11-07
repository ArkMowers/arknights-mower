import { afterEach, describe, expect, it, vi } from 'vitest'
import { copyMowerTestText } from './copyMowerTestText'

afterEach(() => vi.unstubAllGlobals())

describe('copyMowerTestText', () => {
  it('copies the full connection error without truncating the text', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const error = '连接失败：SSL unexpected EOF\n完整错误详情'
    expect(await copyMowerTestText(error)).toBe(true)
    expect(writeText).toHaveBeenCalledWith(error)
  })

  it('falls back when the desktop clipboard API is denied', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) }
    })
    const input = {
      value: '',
      readOnly: false,
      style: {},
      focus: vi.fn(),
      select: vi.fn(),
      remove: vi.fn()
    }
    const execCommand = vi.fn().mockReturnValue(true)
    vi.stubGlobal('document', {
      createElement: vi.fn().mockReturnValue(input),
      body: { appendChild: vi.fn() },
      execCommand
    })
    expect(await copyMowerTestText('connection error')).toBe(true)
    expect(input.value).toBe('connection error')
    expect(input.select).toHaveBeenCalledOnce()
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(input.remove).toHaveBeenCalledOnce()
  })

  it('does not copy an empty test result', async () => {
    expect(await copyMowerTestText('')).toBe(false)
  })
})
