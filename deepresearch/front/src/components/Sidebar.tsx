import React, { useState, useRef, useEffect } from 'react'
import Popover from './Popover.js'
import { useChatStore } from '../store/chatStore.js'

function getInitials(name: string){
  if(!name) return 'U'
  const s = name.trim()
  const first = s[0]
  // latin letters -> collect up to two
  const letters = s.match(/[A-Za-z]/g)
  if(letters && letters.length>0){
    const a = letters[0].toUpperCase()
    const b = letters[1] ? letters[1].toUpperCase() : ''
    return (a + b).slice(0,2)
  }
  // fallback: return first character (works for Chinese)
  return first
}

export default function Sidebar(){
  const username = '张三'
  const [collapsed, setCollapsed] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [draftQuery, setDraftQuery] = useState('')
  const [appliedQuery, setAppliedQuery] = useState('')
  const [moreOpen, setMoreOpen] = useState(false)
  const [moreAnchor, setMoreAnchor] = useState<DOMRect | null>(null)
  const searchRef = useRef<HTMLInputElement | null>(null)
  const moreBtnRef = useRef<HTMLButtonElement | null>(null)

  const conversations = useChatStore(s => s.conversations)
  const activeConversationId = useChatStore(s => s.activeConversationId)
  const setActiveConversationId = useChatStore(s => s.setActiveConversationId)
  const createConversation = useChatStore(s => s.createConversation)

  useEffect(()=>{
    // initialize CSS variable for sidebar current width
    const root = document.documentElement
    const computed = getComputedStyle(root)
    const expandedVal = computed.getPropertyValue('--sidebar-width') || '260px'
    root.style.setProperty('--sidebar-current-width', expandedVal.trim())
  },[])

  const toggleCollapse = () => {
    const root = document.documentElement
    const computed = getComputedStyle(root)
    const expandedVal = computed.getPropertyValue('--sidebar-width') || '260px'
    const collapsedVal = computed.getPropertyValue('--sidebar-collapsed-width') || '72px'
    setCollapsed(prev => {
      const next = !prev
      root.style.setProperty('--sidebar-current-width', next ? collapsedVal.trim() : expandedVal.trim())
      return next
    })
  }

  useEffect(()=>{
    if(searchOpen && searchRef.current){
      searchRef.current.focus()
      // initialize draft with applied value when opening
      setDraftQuery(appliedQuery)
    }
  },[searchOpen])

  const onNewChat = () => {
    createConversation('新聊天')
    setSearchOpen(false)
    setDraftQuery('')
    setAppliedQuery('')
  }

  const onSearchToggle = () => {
    setSearchOpen(v => !v)
    setMoreOpen(false)
    if(searchOpen){ setDraftQuery('') }
  }

  const onMoreToggle = () => {
    if(!moreOpen){
      const rect = moreBtnRef.current?.getBoundingClientRect() ?? null
      setMoreAnchor(rect)
      setMoreOpen(true)
    }else{
      setMoreOpen(false)
      setMoreAnchor(null)
    }
    setSearchOpen(false)
  }

  const searchFiltered = conversations.filter(r => r.title.includes(appliedQuery))

  function groupByTime(items: Array<{id:string,title:string,ts:number}>){
    const now = Date.now()
    const day = 24*60*60*1000
    const today: typeof items = []
    const last7: typeof items = []
    const last30: typeof items = []
    items.forEach(it=>{
      const d = now - it.ts
      if(d < day) today.push(it)
      else if(d < 7*day) last7.push(it)
      else if(d < 30*day) last30.push(it)
    })
    return { today, last7, last30 }
  }

  const groups = groupByTime(searchFiltered as any)

  const openConversation = (convId?: string) => {
    if(convId){
      setActiveConversationId(convId)
    }else{
      setActiveConversationId(null)
    }
    setSearchOpen(false)
    setMoreOpen(false)
  }

  return (
    <aside className={"sidebar" + (collapsed ? ' collapsed' : '')}>
      <div className="header">
        <div className="header-top">
          <div className="icon-row" aria-hidden>
            <div
              className="sidebar-icon"
              title={collapsed ? '展开侧边栏' : '会话'}
              role={collapsed ? 'button' : undefined}
              tabIndex={collapsed ? 0 : undefined}
              onClick={() => { if(collapsed) toggleCollapse() }}
              onKeyDown={(e) => { if(collapsed && (e.key === 'Enter' || e.key === ' ')){ e.preventDefault(); toggleCollapse() } }}
            >
              <span className="icon-default" aria-hidden>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </span>
              <span className="icon-expand" aria-hidden>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </span>
            </div>
          </div>
          {!collapsed && (
            <button className="collapse-btn" onClick={toggleCollapse} aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}>
              {/* chevron icon */}
              {collapsed ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
              )}
            </button>
          )}
        </div>

        <div className="sidebar-actions">
          <button className="action" onClick={onNewChat} title="新聊天">
            <span className="icon" aria-hidden>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </span>
            <span className="label">新聊天</span>
          </button>
          <button className="action" onClick={onSearchToggle} title="搜索聊天">
            <span className="icon" aria-hidden>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/><circle cx="11" cy="11" r="6" stroke="currentColor" strokeWidth="1.6"/></svg>
            </span>
            <span className="label">搜索聊天</span>
          </button>
          <button className="action" ref={moreBtnRef} onClick={onMoreToggle} title="更多">
            <span className="icon" aria-hidden>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 6v.01M12 12v.01M12 18v.01" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </span>
            <span className="label">更多</span>
          </button>
        </div>

        {searchOpen && (
          <Popover onClose={()=>setSearchOpen(false)} className="search">
            <div className="search-dialog">
              <input
                ref={searchRef}
                value={draftQuery}
                onChange={e=>setDraftQuery(e.target.value)}
                onBlur={() => setAppliedQuery(draftQuery)}
                onKeyDown={(e)=>{ if(e.key === 'Enter'){ setAppliedQuery(draftQuery); (e.target as HTMLInputElement).blur() } }}
                placeholder="搜索最近会话..."
              />
              <div className="divider" />
              <div className="history">
                      {groups.today && groups.today.length>0 && (
                        <div className="history-group">
                          <div className="group-title">今天</div>
                          {groups.today.map(g=> (
                            <div key={g.id} className="history-item" onClick={()=>{ openConversation(g.id) }}>{g.title}</div>
                          ))}
                        </div>
                      )}
                {groups.last7 && groups.last7.length>0 && (
                  <div className="history-group">
                    <div className="group-title">7天内</div>
                    {groups.last7.map(g=> (
                      <div key={g.id} className="history-item" onClick={()=>{ openConversation(g.id) }}>{g.title}</div>
                    ))}
                  </div>
                )}
                {groups.last30 && groups.last30.length>0 && (
                  <div className="history-group">
                    <div className="group-title">30天内</div>
                    {groups.last30.map(g=> (
                      <div key={g.id} className="history-item" onClick={()=>{ openConversation(g.id) }}>{g.title}</div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </Popover>
        )}

        {moreOpen && (
          <Popover onClose={()=>{ setMoreOpen(false); setMoreAnchor(null) }} className="more" contentStyle={moreAnchor ? { left: `${Math.min(window.innerWidth - 320 - 12, moreAnchor.right + 8)}px`, top: `${moreAnchor.top}px`, width: '320px' } : undefined}>
            <div className="more-dialog">
              <button className="menu-item" onClick={()=>{ alert('导出（mock）') }}>导出</button>
              <button className="menu-item" onClick={()=>{ alert('设置（mock）') }}>设置</button>
              <button className="menu-item" onClick={()=>{ alert('清空（mock）') }}>清空</button>
            </div>
          </Popover>
        )}
      </div>

      

      {!collapsed && (
        <div className="sessions">
          <div className="recent-label">最近</div>
          <div className="recent-list">
            {conversations.map(item => (
              <div key={item.id} className={"recent-item" + (item.id === activeConversationId ? ' selected' : '')} onClick={()=>{ openConversation(item.id) }} aria-selected={(item.id === activeConversationId) || undefined}>
                <div className="summary" title={item.title}>{item.title}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="sidebar-bottom">
        <div className="profile">
          <div className="avatar">{getInitials(username)}</div>
          {!collapsed && (
            <div className="profile-meta">
              <div className="username">{username}</div>
              <div className="tag">测试版</div>
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}
