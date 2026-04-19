import React from 'react'
import Sidebar from './components/Sidebar'
import ChatPage from './pages/ChatPage'

export default function App(){
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-area">
        <ChatPage />
      </div>
    </div>
  )
}
