import React, { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

type PopoverProps = {
  onClose?: () => void
  className?: string
  children?: React.ReactNode
  closeOnBackdrop?: boolean
  ariaLabel?: string
  contentStyle?: React.CSSProperties
}

export default function Popover({ onClose, className = '', children, closeOnBackdrop = true, ariaLabel = '对话框', contentStyle }: PopoverProps){
  const hostRef = useRef<HTMLDivElement | null>(null)
  if(!hostRef.current){
    hostRef.current = document.createElement('div')
  }

  const onCloseRef = useRef(onClose)
  useEffect(()=>{ onCloseRef.current = onClose }, [onClose])

  useEffect(()=>{
    const host = hostRef.current!
    document.body.appendChild(host)
    const onKey = (e: KeyboardEvent) => { if(e.key === 'Escape') onCloseRef.current?.() }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if(host.parentNode === document.body) document.body.removeChild(host)
    }
  },[])

  const handleBackdrop = () => { if(closeOnBackdrop) onCloseRef.current?.() }

  const content = (
    <div className={`popover-overlay`} role="dialog" aria-label={ariaLabel}>
      <div className="popover-backdrop" onClick={handleBackdrop} />
      <div className={`popover-content ${className}`} style={contentStyle} onClick={e=>e.stopPropagation()}>
        {children}
      </div>
    </div>
  )

  return createPortal(content, hostRef.current)
}
