import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import Composer from '../Composer'

describe('Composer', ()=>{
  it('calls onSend when pressing Enter without Shift', ()=>{
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)
    const ta = screen.getByPlaceholderText('请输入消息...') as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: 'hi there' } })
    fireEvent.keyDown(ta, { key: 'Enter', code: 'Enter', shiftKey: false })
    expect(onSend).toHaveBeenCalledWith('hi there')
  })

  it('shows stop button and calls onStop while streaming', ()=>{
    const onSend = vi.fn()
    const onStop = vi.fn()
    render(<Composer onSend={onSend} onStop={onStop} isStreaming={true} />)

    const stopBtn = screen.getByLabelText('暂停当前回复')
    fireEvent.click(stopBtn)
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('does not send on Enter while streaming', ()=>{
    const onSend = vi.fn()
    render(<Composer onSend={onSend} isStreaming={true} />)

    const ta = screen.getByPlaceholderText('请输入消息...') as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: 'streaming input' } })
    fireEvent.keyDown(ta, { key: 'Enter', code: 'Enter', shiftKey: false })
    expect(onSend).not.toHaveBeenCalled()
  })
})
