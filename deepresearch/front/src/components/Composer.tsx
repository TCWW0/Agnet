import React, { useState, useRef, useEffect } from 'react'

type ComposerProps = {
  onSend: (text: string) => void
  onStop?: () => void
  isStreaming?: boolean
}

export default function Composer({ onSend, onStop, isStreaming = false }: ComposerProps){
  const [text, setText] = useState('')
  const taRef = useRef<HTMLTextAreaElement | null>(null)

  const getComposerMinHeight = ()=>{
    if(typeof window === 'undefined') return '48px'
    const v = getComputedStyle(document.documentElement).getPropertyValue('--composer-min-height')
    return v ? v.trim() : '48px'
  }

  const getComposerMaxHeight = ()=>{
    if(typeof window === 'undefined') return '160px'
    const v = getComputedStyle(document.documentElement).getPropertyValue('--composer-max-height')
    return v ? v.trim() : '160px'
  }

  useEffect(()=>{
    const ta = taRef.current
    if(!ta) return
    // initialize height
    const minHStr = getComposerMinHeight()
    const maxHStr = getComposerMaxHeight()
    const minH = parseInt(minHStr, 10) || 48
    const maxH = parseInt(maxHStr, 10) || 160
    ta.style.height = 'auto'
    const h = Math.max(minH, Math.min(ta.scrollHeight, maxH))
    ta.style.height = h + 'px'
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>)=>{
    if (isStreaming && e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      return
    }

    if(e.key === 'Enter' && !e.shiftKey){
      e.preventDefault()
      if(text.trim()){
        onSend(text)
        setText('')
        if(taRef.current){
          const minH = getComposerMinHeight()
          taRef.current.style.height = minH
        }
      }
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>)=>{
    const ta = e.target as HTMLTextAreaElement
    setText(ta.value)
    ta.style.height = 'auto'
    const maxHStr = getComposerMaxHeight()
    const maxH = parseInt(maxHStr, 10) || 160
    const minH = parseInt(getComposerMinHeight(), 10) || 48
    const newHeight = Math.max(minH, Math.min(ta.scrollHeight, maxH))
    ta.style.height = `${newHeight}px`
    ta.style.overflowY = ta.scrollHeight > maxH ? 'auto' : 'hidden'
  }

  const handleClickSend = ()=>{
    if(!text.trim()) return
    onSend(text)
    setText('')
    if(taRef.current){
      taRef.current.style.height = getComposerMinHeight()
    }
  }

  const handleClickStop = () => {
    if (onStop) onStop()
  }

  return (
    <div className={`composer`}>
      <textarea
        ref={taRef}
        placeholder="请输入消息..."
        value={text}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
      />
      <div className="controls">
        {isStreaming ? (
          <button className="send-btn stop-btn" aria-label="暂停当前回复" onClick={handleClickStop}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" stroke="currentColor">
              <rect x="7" y="7" width="10" height="10" rx="1.5" strokeWidth="1.8" />
            </svg>
          </button>
        ) : (
          <button className="send-btn" aria-label="发送" disabled={!text.trim()} aria-disabled={!text.trim()} onClick={handleClickSend}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" stroke="currentColor">
              <path d="M12 19V6" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M5 12l7-7 7 7" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
