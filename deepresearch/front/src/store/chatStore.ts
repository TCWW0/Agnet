import create from 'zustand'

export type Message = { 
  id: string; role: 'user'|'assistant'; 
  content: string; 
  paragraphs?: string[]; 
  partial?: string; 
  streaming?: boolean 
}

export type ConversationSummary = {
  id: string
  title: string
  ts: number
}

export type State = {
  messages: Message[]
  conversations: ConversationSummary[]
  addMessage: (m: Message)=>void
  appendToMessage: (id: string, chunk: string)=>void
  appendPartial: (id: string, chunk: string)=>void
  pushParagraph: (id: string, paragraph: string)=>void
  finalizeMessage: (id: string)=>void
  updateMessage: (id: string, diff: Partial<Message>)=>void
  createConversation: (title?: string, conversationId?: string)=>string
  ensureConversationForMessage: (text: string)=>string
  touchConversation: (id: string, title?: string)=>void
  clear: ()=>void
  setMessages: (msgs: Message[])=>void
  activeConversationId: string | null
  setActiveConversationId: (id: string | null)=>void
}

export type ChatMessage = Message
export type ChatState = State

const STORAGE_PREFIX = 'dr_session_conv_'
const CONVERSATIONS_KEY = 'dr_session_conversations'
const DEFAULT_CONVERSATION_TITLE = '新聊天'
const FIRST_MESSAGE_TITLE_MAX = 18

function storageKey(convId: string){ return STORAGE_PREFIX + convId }

function normalizeTitle(raw?: string){
  const value = (raw || '').replace(/\s+/g, ' ').trim()
  return value || DEFAULT_CONVERSATION_TITLE
}

function buildConversationTitleFromMessage(text: string){
  const normalized = (text || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return DEFAULT_CONVERSATION_TITLE
  if (normalized.length <= FIRST_MESSAGE_TITLE_MAX) return normalized
  return normalized.slice(0, FIRST_MESSAGE_TITLE_MAX) + '...'
}

function moveConversationToFront(
  list: ConversationSummary[],
  id: string,
  title?: string,
  forceCreate: boolean = true
){
  const idx = list.findIndex(c => c.id === id)
  if (idx < 0) {
    if (!forceCreate) return list
    const nextItem: ConversationSummary = {
      id,
      title: normalizeTitle(title),
      ts: Date.now()
    }
    return [nextItem, ...list]
  }

  const current = list[idx]
  const updated: ConversationSummary = {
    ...current,
    title: title ? normalizeTitle(title) : current.title,
    ts: Date.now()
  }
  return [updated, ...list.slice(0, idx), ...list.slice(idx + 1)]
}

function safeLoadConversations(){
  try {
    const raw = sessionStorage.getItem(CONVERSATIONS_KEY)
    if (!raw) return [] as ConversationSummary[]
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return [] as ConversationSummary[]

    return parsed
      .filter((item: any) => item && typeof item.id === 'string')
      .map((item: any) => ({
        id: item.id,
        title: normalizeTitle(item.title),
        ts: typeof item.ts === 'number' ? item.ts : Date.now()
      }))
  } catch {
    return [] as ConversationSummary[]
  }
}

function safeSaveConversations(conversations: ConversationSummary[]){
  try {
    sessionStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations))
  } catch {}
}

function safeLoad(convId?: string){
  if(!convId) return [] as Message[]
  try{
    const raw = sessionStorage.getItem(storageKey(convId))
    if(!raw) return []
    return JSON.parse(raw) as Message[]
  }catch{ return [] }
}

function safeSave(convId: string | null, messages: Message[]){
  if(!convId) return
  try{ sessionStorage.setItem(storageKey(convId), JSON.stringify(messages)) }catch{}
}

export const useChatStore = create<State>((set, get) => ({
  messages: [],
  conversations: safeLoadConversations(),
  addMessage: (m) => set(s => {
    // ensure paragraphs/partial present for assistant messages
    const msg: Message = {
      ...m,
      paragraphs: m.paragraphs ?? [],
      partial: m.partial ?? '',
      content: m.content ?? ''
    }
    const msgs = [...s.messages, msg]
    safeSave(s.activeConversationId, msgs)
    return { messages: msgs }
  }),
  appendToMessage: (id, chunk) => set(s => {
    const msgs = s.messages.map(m => m.id === id ? { ...m, content: (m.content || '') + chunk } : m)
    safeSave(s.activeConversationId, msgs)
    return { messages: msgs }
  }),
  appendPartial: (id, chunk) => set(s => {
    const msgs = s.messages.map(m => {
      if (m.id !== id) return m
      const partial = (m.partial || '') + chunk
      const persistedParagraphs = (m.paragraphs || []).join('\n\n')
      // keep content for backward compatibility without creating leading blank lines
      const content = persistedParagraphs
        ? (partial ? persistedParagraphs + '\n\n' + partial : persistedParagraphs)
        : partial
      return { ...m, partial, content }
    })
    safeSave(s.activeConversationId, msgs)
    return { messages: msgs }
  }),
  pushParagraph: (id, paragraph) => set(s => {
    const msgs = s.messages.map(m => {
      if (m.id !== id) return m
      const pars = Array.isArray(m.paragraphs) ? [...m.paragraphs, paragraph] : [paragraph]
      // clear partial when a paragraph is finalized
      const content = pars.join('\n\n')
      return { ...m, paragraphs: pars, partial: '', content }
    })
    safeSave(s.activeConversationId, msgs)
    return { messages: msgs }
  }),
  finalizeMessage: (id) => set(s => {
    const msgs = s.messages.map(m => {
      if (m.id !== id) return m
      const pars = Array.isArray(m.paragraphs) ? [...m.paragraphs] : []
      if (m.partial && m.partial.trim()) pars.push(m.partial)
      const content = pars.join('\n\n')
      return { ...m, paragraphs: pars, partial: '', content, streaming: false }
    })
    safeSave(s.activeConversationId, msgs)
    return { messages: msgs }
  }),
  updateMessage: (id, diff) => set(s => {
    const msgs = s.messages.map(m => m.id === id ? { ...m, ...diff } : m)
    safeSave(s.activeConversationId, msgs)
    return { messages: msgs }
  }),
  createConversation: (title, conversationId) => {
    const id = conversationId || ('conv_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8))
    const nextTitle = normalizeTitle(title)

    set(s => {
      const conversations = moveConversationToFront(s.conversations, id, nextTitle, true)
      safeSaveConversations(conversations)
      const msgs = safeLoad(id)
      return { conversations, activeConversationId: id, messages: msgs }
    })

    return id
  },
  ensureConversationForMessage: (text) => {
    const state = get()
    const currentId = state.activeConversationId
    if (currentId) {
      const currentConversation = state.conversations.find(c => c.id === currentId)
      const normalizedTitle = normalizeTitle(currentConversation?.title)
      const hasAnyMessage = state.messages.length > 0

      // 新建会话第一次真正发送消息时，自动把标题从“新聊天”更新为消息摘要。
      if (!hasAnyMessage && normalizedTitle === DEFAULT_CONVERSATION_TITLE) {
        state.touchConversation(currentId, buildConversationTitleFromMessage(text))
      } else {
        state.touchConversation(currentId)
      }
      return currentId
    }

    const generatedId = 'conv_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
    const title = buildConversationTitleFromMessage(text)
    get().createConversation(title, generatedId)
    return generatedId
  },
  touchConversation: (id, title) => set(s => {
    if (!id) return {}
    const conversations = moveConversationToFront(s.conversations, id, title, true)
    safeSaveConversations(conversations)
    return { conversations }
  }),
  clear: () => set(s => {
    try{ if(s.activeConversationId) sessionStorage.removeItem(storageKey(s.activeConversationId)) }catch{}
    return { messages: [] }
  }),
  setMessages: (msgs) => set(s => {
    safeSave(s.activeConversationId, msgs)
    return { messages: msgs }
  }),
  activeConversationId: null,
  setActiveConversationId: (id) => set(s => {
    const msgs = safeLoad(id ?? undefined)
    safeSaveConversations(s.conversations)
    // 仅切换选中态，不因“选中操作”改变会话顺序。
    return { activeConversationId: id, messages: msgs, conversations: s.conversations }
  })
}))
