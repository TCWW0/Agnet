import React, { useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import type { ChatMessage } from '../store/chatStore.js'

function LoadingDots(){
  return (
    <div className="loading-dots" role="status" aria-live="polite">
      <span className="dot" />
      <span className="dot" />
      <span className="dot" />
    </div>
  )
}

export default function Message({ message }: { message: ChatMessage }){
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)
  const [showMore, setShowMore] = useState(false)

  const shouldShowLoading = !isUser && (message.streaming === true || (message.content === '' && message.streaming !== false))
  // Parse message into paragraph blocks, removing whitespace-only blank paragraphs
  const parseParagraphs = (txt: string) => {
    if (!txt) return [] as string[]
    const s = txt.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    const parts = s.split(/\n\s*\n+/).map(p => p.trim()).filter(p => p.length > 0)
    return parts
  }

  const hasStructuredParagraphs = Array.isArray(message.paragraphs) && message.paragraphs.length > 0
  const partialText = (message.partial || '').trim()

  // Build paragraph array with mutually-exclusive sources.
  // Streaming: render only `partial` before first finalized paragraph.
  // Finalized: render `paragraphs` (+ partial tail when still streaming).
  const rawParagraphs: string[] = []
  if (!shouldShowLoading) {
    if (hasStructuredParagraphs) {
      rawParagraphs.push(...(message.paragraphs || []))
      if (partialText) rawParagraphs.push(partialText)
    } else if (partialText) {
      rawParagraphs.push(partialText)
    } else {
      rawParagraphs.push(...parseParagraphs(message.content || ''))
    }
  }

  const actionText = useMemo(() => {
    const merged = rawParagraphs.join('\n\n').trim()
    return merged || (message.content || '').trim()
  }, [rawParagraphs, message.content])

  const copyByFallback = (text: string) => {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', 'true')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }

  const handleCopy = async () => {
    if (!actionText) return
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(actionText)
      } else {
        copyByFallback(actionText)
      }
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1400)
    } catch {
      try {
        copyByFallback(actionText)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1400)
      } catch {
        setCopied(false)
      }
    }
  }

  return (
    <div className={`msg-row ${isUser ? 'user' : 'assistant'}`}>
      <div className={`bubble ${isUser ? 'user' : 'assistant'}`}>
        <div className="content">
          {shouldShowLoading ? (
            <LoadingDots />
          ) : (
            <>
              {rawParagraphs.map((p, i) => (
                <ReactMarkdown key={i} remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
                  {p}
                </ReactMarkdown>
              ))}
            </>
          )}
        </div>

        {!isUser && !shouldShowLoading && actionText && (
          <>
            <div className="message-actions" role="group" aria-label="消息操作">
              <button type="button" className="action-btn" onClick={handleCopy}>
                {copied ? '已复制' : '复制'}
              </button>
              <button type="button" className="action-btn" onClick={() => setShowMore(v => !v)}>
                {showMore ? '收起' : '更多'}
              </button>
            </div>
            {showMore && (
              <div className="message-more-panel" aria-label="更多信息">
                <span>字数：{actionText.length}</span>
                <span>段落：{rawParagraphs.length || 1}</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
