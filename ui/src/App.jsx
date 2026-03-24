
import React, {useEffect, useState} from 'react'
export default function App(){
  const [alerts,setAlerts]=useState([])
  useEffect(()=>{
    const ws=new WebSocket('ws://localhost:8000/ws')
    ws.onmessage=(e)=> setAlerts(a=>[JSON.parse(e.data), ...a])
    return ()=>ws.close()
  },[])
  return (
    <div style={{padding:16}}>
      <h2>SecureVU</h2>
      <ul>{alerts.map((a,i)=>(<li key={i}>{JSON.stringify(a)}</li>))}</ul>
    </div>
  )
}
