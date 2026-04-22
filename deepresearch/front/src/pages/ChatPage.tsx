import React, { useRef, useEffect, useState } from 'react'
import ChatWindow from '../components/ChatWindow.js'
import Composer from '../components/Composer.js'
import { useChatStore } from '../store/chatStore.js'
import { pauseStream, streamChat } from '../services/agentClient.js'
import type { ChatState } from '../store/chatStore.js'

type RunningStream = {
  assistantId: string
  conversationId: string
  streamId: string
  cancel: () => void
}

export default function ChatPage(){
  const messages = useChatStore((s: ChatState) => s.messages)
  const addMessage = useChatStore((s: ChatState) => s.addMessage)
  const appendToMessage = useChatStore((s: ChatState) => s.appendToMessage)
  const appendPartial = useChatStore((s: ChatState) => s.appendPartial)
  const pushParagraph = useChatStore((s: ChatState) => s.pushParagraph)
  const finalizeMessage = useChatStore((s: ChatState) => s.finalizeMessage)
  const updateMessage = useChatStore((s: ChatState) => s.updateMessage)
  const ensureConversationForMessage = useChatStore((s: ChatState) => s.ensureConversationForMessage)
  const touchConversation = useChatStore((s: ChatState) => s.touchConversation)

  const streamControllerRef = useRef<RunningStream | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [showScrollToBottom, setShowScrollToBottom] = useState(false)

  const getBottomThresholdPx = () => {
    if (typeof window === 'undefined') return 72
    const raw = getComputedStyle(document.documentElement).getPropertyValue('--scroll-bottom-threshold')
    const parsed = Number.parseInt(raw, 10)
    return Number.isFinite(parsed) ? parsed : 72
  }

  const isNearPageBottom = () => {
    if (typeof window === 'undefined') return true
    const threshold = getBottomThresholdPx()
    const distance = document.documentElement.scrollHeight - (window.scrollY + window.innerHeight)
    return distance <= threshold
  }

  const scrollToPageBottom = (behavior: ScrollBehavior = 'smooth') => {
    if (typeof window === 'undefined') return
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior })
  }

  const stopCurrentStream = (notifyServer: boolean) => {
    const running = streamControllerRef.current
    if (!running) return

    streamControllerRef.current = null
    setIsStreaming(false)

    if (notifyServer) {
      void pauseStream(running.streamId, running.conversationId)
    }

    running.cancel()
    try { updateMessage(running.assistantId, { streaming: false }) } catch {}
    try { finalizeMessage(running.assistantId) } catch {}
    try { touchConversation(running.conversationId) } catch {}
  }

  useEffect(()=>{
    return ()=>{
      stopCurrentStream(false)
    }
  }, [])

  useEffect(() => {
    const handleScroll = () => {
      setShowScrollToBottom(!isNearPageBottom())
    }

    handleScroll()
    window.addEventListener('scroll', handleScroll, { passive: true })
    window.addEventListener('resize', handleScroll)
    return () => {
      window.removeEventListener('scroll', handleScroll)
      window.removeEventListener('resize', handleScroll)
    }
  }, [])

  useEffect(() => {
    setShowScrollToBottom(!isNearPageBottom())
  }, [messages])

  const handleSend = (text: string) => {
    if (isStreaming) return
    if(!text.trim()) return

    const conversationId = ensureConversationForMessage(text)
    touchConversation(conversationId)

    const userMsg = { id: String(Date.now()), role: 'user' as const, content: text }
    addMessage(userMsg)

    const assistantId = String(Date.now() + 1)
    addMessage({ id: assistantId, role: 'assistant', content: '', paragraphs: [], partial: '', streaming: true })

    requestAnimationFrame(() => {
      scrollToPageBottom('smooth')
    })

    const streamId = 'stream_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
    setIsStreaming(true)

    const msgsForApi = useChatStore
      .getState()
      .messages
      .filter(m => (m.role === 'user' || m.role === 'assistant') && (m.content || '').trim().length > 0)
      .map(m => ({ id: m.id, role: m.role, content: m.content }))

    // start streaming via POST + ReadableStream
    const ctrl = streamChat(
      msgsForApi,
      conversationId,
      (chunk: string) => {
        if (streamControllerRef.current?.assistantId !== assistantId) return
        const shouldFollow = isNearPageBottom()
        // on first chunk, clear loading state
        try{ const msgs = useChatStore.getState().messages; const m = msgs.find(x=>x.id===assistantId); if(m && (m as any).streaming){ updateMessage(assistantId, { streaming: false }) } }catch{}
        // append to partial buffer (not committed paragraph yet)
        try{ appendPartial(assistantId, chunk) } catch { appendToMessage(assistantId, chunk) }
        if (shouldFollow) requestAnimationFrame(() => scrollToPageBottom('auto'))
      },
      (paragraph: string) => {
        if (streamControllerRef.current?.assistantId !== assistantId) return
        const shouldFollow = isNearPageBottom()
        // paragraph frame: finalize/loading off and commit paragraph
        try{ updateMessage(assistantId, { streaming: false }) }catch{}
        try{ pushParagraph(assistantId, paragraph) } catch { appendToMessage(assistantId, '\n\n' + paragraph) }
        if (shouldFollow) requestAnimationFrame(() => scrollToPageBottom('auto'))
      },
      (meta?: any) => {
        if (streamControllerRef.current?.assistantId !== assistantId) return
        const shouldFollow = isNearPageBottom()
        // stream done - finalize any partial and mark streaming false
        try{ finalizeMessage(assistantId) }catch{}
        streamControllerRef.current = null
        setIsStreaming(false)
        touchConversation(conversationId)
        if (shouldFollow) requestAnimationFrame(() => scrollToPageBottom('smooth'))
      }
      ,
      streamId
    )

    streamControllerRef.current = {
      assistantId,
      conversationId,
      streamId,
      cancel: ctrl.cancel
    }
  }

  return (
    <div className="chat-page">
      <div className="top-nav">
        <div>
          <div style={{fontWeight:600,fontSize:16}}>Local_Agent</div>
          <div style={{fontSize:13,color:'var(--muted-text)'}}>示例导航</div>
        </div>
      </div>

      <div className="content-wrap">
        <section className="chat-scroll">
          <div className="chat-container">
            <ChatWindow messages={messages} />
          </div>
        </section>

        <section className="composer-region" aria-hidden="true" />
      </div>

      <button
        type="button"
        className={`scroll-to-bottom-btn${showScrollToBottom ? ' visible' : ''}`}
        aria-label="回到底部"
        aria-hidden={!showScrollToBottom}
        tabIndex={showScrollToBottom ? 0 : -1}
        onClick={() => scrollToPageBottom('smooth')}
      >
        回到底部
      </button>

      <section className="composer-fixed-layer" aria-label="输入区域">
        <div className="composer-fixed-stack">
          <div className="chat-container">
            <Composer onSend={handleSend} onStop={() => stopCurrentStream(true)} isStreaming={isStreaming} />
          </div>

          <div className="composer-bottom-note" aria-hidden="true">
            <div className="chat-container">
              AI 也可能会犯错。请核查重要信息。测试版仅供参考
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
