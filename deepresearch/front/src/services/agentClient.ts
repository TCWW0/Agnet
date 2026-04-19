const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export function connectSSE(conversationId: string, onMessage: (chunk: string)=>void){
  // Deprecated: SSE GET kept for compatibility. Prefer `streamChat` (POST + ReadableStream).
  const url = `${API_BASE}/api/v1/chat/stream?conversationId=${encodeURIComponent(conversationId)}`
  const es = new EventSource(url)
  es.onmessage = e => onMessage(e.data)
  es.onerror = e => console.error(e)
  return es
}

export function connectWS(url: string, onMessage: (msg:any)=>void){
  const ws = new WebSocket(url)
  ws.onmessage = e => {
    try{ onMessage(JSON.parse(e.data)) } catch { onMessage(e.data) }
  }
  return ws
}

export async function pauseStream(streamId: string, conversationId?: string){
  if (!streamId) return
  try {
    await fetch(`${API_BASE}/api/v1/chat/stream/pause`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ streamId, conversationId })
    })
  } catch {
    // best-effort signal; local UI will still stop via AbortController
  }
}

// Stream chat via POST + ReadableStream. Returns a controller with `cancel()`.
export function streamChat(
  messages: any[],
  conversationId?: string,
  onChunk?: (chunk: string)=>void,
  onParagraph?: (paragraph: string)=>void,
  onDone?: (meta?: any)=>void,
  streamId?: string
){
  const controller = new AbortController()

  const url = `${API_BASE}/api/v1/chat/stream`
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversationId, messages, streamId }),
    signal: controller.signal
  }).then(async resp => {
    if (!resp.body) {
      // Fallback: read full text
      const text = await resp.text()
        try {
          const json = JSON.parse(text)
          onDone?.(json)
        } catch (e) {
          if (text) onChunk?.(text)
          onDone?.()
        }
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()

    // Buffer for incremental parsing (supports SSE framing)
    let buf = ''
    const flushEvent = (raw: string) => {
      const lines = raw.split(/\r?\n/)
      let eventType = ''
      const dataLines: string[] = []
      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventType = line.replace(/^event:\s*/, '').trim()
        } else if (line.startsWith('data:')) {
          dataLines.push(line.replace(/^data:\s*/, ''))
        }
      }
      const data = dataLines.join('\n')

      // Try to parse data as JSON frame
      let frame: any = null
      try { frame = JSON.parse(data) } catch {}

      if (frame && frame.type) {
        const t = frame.type
        if (t === 'chunk') {
          if (frame.text) onChunk?.(frame.text)
          else if (data) onChunk?.(data)
        } else if (t === 'paragraph') {
          if (frame.text) onParagraph?.(frame.text)
          else if (data) onParagraph?.(data)
        } else if (t === 'done') {
          onDone?.(frame.meta ?? frame)
        } else if (t === 'error') {
          // forward error meta
          onDone?.(frame.meta ?? { error: true })
        } else {
          // unknown typed frame, forward raw text
          if (frame.text) onChunk?.(frame.text)
        }
      } else {
        // No structured frame: fall back to eventType or raw
        if (eventType === 'chunk') {
          // try parse data as JSON then fallback to raw
          try { const d = JSON.parse(data); if (d && d.text) onChunk?.(d.text); else onChunk?.(data) } catch { onChunk?.(data) }
        } else if (eventType === 'paragraph') {
          try { const d = JSON.parse(data); if (d && d.text) onParagraph?.(d.text); else onParagraph?.(data) } catch { onParagraph?.(data) }
        } else if (eventType === 'done') {
          try { const d = JSON.parse(data); onDone?.(d.meta ?? d) } catch { onDone?.() }
        } else {
          // fallback: treat whole raw as chunk
          if (raw) onChunk?.(raw)
        }
      }
    }

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          // flush remaining buffer
          if (buf.trim()) {
            // if looks like SSE framed, split by double-newline; otherwise send as chunk
            if (buf.includes('\n\n') || buf.includes('\r\n\r\n')) {
              const parts = buf.split(/(?:\r?\n){2,}/)
              for (const p of parts) if (p.trim()) flushEvent(p.trim())
            } else {
              // try to parse remaining as JSON
                try {
                  const j = JSON.parse(buf)
                  if (j && j.type === 'paragraph') {
                    onParagraph?.(j.text)
                  } else if (j && j.type === 'chunk') {
                    onChunk?.(j.text || buf)
                  } else {
                    onChunk?.(buf)
                  }
                } catch (e) {
                  onChunk?.(buf)
                }
            }
          }
          onDone?.()
          break
        }
        const chunk = decoder.decode(value, { stream: true })
        if (!chunk) continue
        buf += chunk

        // process full SSE events separated by a blank line
        let sepIdx = -1
        while ((sepIdx = buf.search(/\r?\n\r?\n/)) !== -1) {
          const raw = buf.slice(0, sepIdx).trim()
          buf = buf.slice(sepIdx + (buf[sepIdx] === '\r' ? 4 : 2))
          if (raw) {
            flushEvent(raw)
          }
        }

        // If no SSE framing detected, and buffer grows large, flush as chunk
        if (!buf.includes('\n\n') && buf.length > 1024) {
          // attempt to parse a single JSON line (NDJSON) if present
          const nlIdx = buf.indexOf('\n')
          if (nlIdx !== -1) {
            const line = buf.slice(0, nlIdx).trim()
            buf = buf.slice(nlIdx + 1)
              try {
                const j = JSON.parse(line)
                if (j && j.type === 'paragraph') {
                  onParagraph?.(j.text)
                } else if (j && j.type === 'chunk') {
                  onChunk?.(j.text)
                } else {
                  onChunk?.(line)
                }
              } catch (e) {
                onChunk?.(line)
              }
          } else {
            onChunk?.(buf)
            buf = ''
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return
      console.error('streamChat error', err)
    }
  }).catch(err => {
    if ((err as any).name === 'AbortError') return
    console.error('streamChat fetch error', err)
  })

  return { cancel: () => controller.abort() }
}
