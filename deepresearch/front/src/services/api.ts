const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export async function postChat(messages: any[], conversationId?: string){
  const url = `${API_BASE}/api/v1/chat`
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversationId, messages })
  })
  return resp.json()
}
