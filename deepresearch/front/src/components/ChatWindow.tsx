import React from 'react'
import Message from './Message.js'

type Msg = { id: string; role: 'user'|'assistant'; content: string }

export default function ChatWindow({ messages }: { messages: Msg[] }){
  return (
    <div className="chat-content">
      {messages.length === 0 ? (
        <div className="empty-state">欢迎使用 AI 对话 — 请选择左侧的会话或点击“新聊天”开始。</div>
      ) : (
        messages.map(m=> <Message key={m.id} message={m} />)
      )}
    </div>
  )
}
