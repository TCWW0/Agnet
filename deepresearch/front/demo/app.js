const chat = document.getElementById('chat')
const input = document.getElementById('input')
const send = document.getElementById('send')
const newBtn = document.getElementById('new')

function appendMessage(role, text){
  const div = document.createElement('div')
  div.className = 'msg ' + (role === 'user' ? 'user' : 'assistant')
  div.textContent = text
  chat.appendChild(div)
  chat.scrollTop = chat.scrollHeight
  return div
}

send.addEventListener('click', ()=>{ doSend() })
input.addEventListener('keydown', (e)=>{
  if(e.key === 'Enter' && !e.shiftKey){
    e.preventDefault()
    doSend()
  }
})

function doSend(){
  const text = input.value.trim()
  if(!text) return
  appendMessage('user', text)
  input.value = ''

  // simulate streaming assistant response
  const assistantDiv = appendMessage('assistant', '')
  const full = '这是演示的逐步回复： ' + text
  let i = 0
  const chunkSize = 5
  const id = setInterval(()=>{
    if(i >= full.length){ clearInterval(id); return }
    assistantDiv.textContent += full.slice(i, i+chunkSize)
    i += chunkSize
    chat.scrollTop = chat.scrollHeight
  }, 150)
}

newBtn.addEventListener('click', ()=>{
  chat.innerHTML = ''
})

// seed
appendMessage('assistant', '欢迎！这是一个无需构建的静态演示页面，模拟流式回复。')
