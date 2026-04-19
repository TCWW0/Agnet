import React from 'react'
import { render, screen } from '@testing-library/react'
import Message from '../Message'

describe('Message', ()=>{
  it('renders user message content', ()=>{
    render(<Message message={{ id: '1', role: 'user', content: 'hello user' }} />)
    expect(screen.getByText('hello user')).toBeTruthy()
  })

  it('renders assistant message content', ()=>{
    render(<Message message={{ id: '2', role: 'assistant', content: 'assistant reply' }} />)
    expect(screen.getByText('assistant reply')).toBeTruthy()
  })
})
