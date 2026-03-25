import React, { useEffect, useState } from 'react';
import { Camera, Bell, Shield, LogOut, Search, Settings, AlertTriangle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { API_BASE, WS_URL } from './config';

// Dynamic cameras loaded from backend

export default function Dashboard({ userRole, onLogout }) {
  const [alerts, setAlerts] = useState([]);
  const [cameras, setCameras] = useState([]);

  useEffect(() => {
    // Fetch Dynamic Cameras
    fetch(`${API_BASE}/cameras`)
      .then(r => r.json())
      .then(d => setCameras(d.cameras || []))
      .catch(() => setCameras([{id: 'main', name: 'Main Camera'}]));

    const token = localStorage.getItem('token');
    if (token) {
      fetch(`${API_BASE}/alerts`, { headers: { Authorization: `Bearer ${token}` } })
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((d) => {
          const list = d.alerts || [];
          setAlerts([...list].reverse().slice(0, 50));
        })
        .catch(() => {});
    }
  }, []);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      setAlerts((prev) => [data, ...prev].slice(0, 50));
    };
    return () => ws.close();
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh', padding: 16, gap: 16 }}>
      {/* Sidebar Navigation */}
      <div className="glass-card" style={{ width: 80, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '24px 0' }}>
        <Shield size={32} color="#3b82f6" style={{ marginBottom: 40 }} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24, flex: 1 }}>
          <Camera size={24} color="#f3f4f6" cursor="pointer" />
          <Bell size={24} color="#9ca3af" cursor="pointer" />
          <Settings size={24} color="#9ca3af" cursor="pointer" />
        </div>
        <LogOut size={24} color="#ef4444" cursor="pointer" onClick={onLogout} />
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Header */}
        <div className="glass-card" style={{ padding: '0 24px', height: 80, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ fontSize: 20 }}>SecureVU Command Center</h1>
            <p style={{ fontSize: 13, color: '#9ca3af' }}>Role: <span style={{ color: '#3b82f6' }}>{userRole.toUpperCase()}</span></p>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="input-field" style={{ width: 300, display: 'flex', alignItems: 'center', padding: '0 12px' }}>
              <Search size={18} color="#4b5563" />
              <input type="text" placeholder="Search cameras..." style={{ background: 'transparent', border: 'none', color: 'white', marginLeft: 8, flex: 1, outline: 'none' }} />
            </div>
          </div>
        </div>

        {/* Camera Grid */}
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
          {cameras.map((cam, idx) => (
            <motion.div 
              key={idx} className="glass-card" 
              whileHover={{ scale: 1.01 }}
              style={{ position: 'relative', overflow: 'hidden', minHeight: 250 }}
            >
              <div style={{ position: 'absolute', top: 12, left: 12, padding: '4px 8px', borderRadius: 4, background: 'rgba(0,0,0,0.5)', zIndex: 10 }}>
                <p style={{ fontSize: 12, fontWeight: 600 }}>[CAM {idx+1}] {cam.name}</p>
              </div>
              <div style={{ height: '100%', width: '100%', background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                 <img 
                   src={`${API_BASE}/video/${cam.id}`} 
                   alt={cam.name}
                   style={{ width: '100%', height: '100%', objectFit: 'cover', position: 'absolute', top: 0, left: 0 }}
                   onError={(e) => { e.target.style.display = 'none'; }}
                 />
                 <Camera size={48} color="#1f2937" />
                 <p style={{ position: 'absolute', fontSize: 10, color: '#4b5563', bottom: 12 }}>Streaming encrypted feed...</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Alerts Sidebar */}
      <div className="glass-card" style={{ width: 350, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: 24, paddingBottom: 16, borderBottom: '1px solid #333' }}>
          <h3 style={{ fontSize: 16 }}>Live Intelligence Feed</h3>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
          <AnimatePresence>
            {alerts.length === 0 ? (
              <p style={{ textAlign: 'center', color: '#4b5563', marginTop: 40, fontSize: 13 }}>Waiting for events...</p>
            ) : (
              alerts.map((alert, i) => (
                <motion.div 
                  initial={{ x: 20, opacity: 0 }} animate={{ x: 0, opacity: 1 }}
                  key={i} className="glass-card" 
                  style={{ padding: 12, marginBottom: 12, background: 'rgba(239, 68, 68, 0.05)', borderColor: 'rgba(239, 68, 68, 0.2)' }}
                >
                  <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                    <div style={{ background: '#ef4444', padding: 8, borderRadius: 8 }}>
                       <AlertTriangle size={18} color="white" />
                    </div>
                    <div>
                      <p style={{ fontSize: 14, fontWeight: 700 }}>
                        {(alert.label || alert.type || 'Alert').toString().toUpperCase()}
                      </p>
                      <p style={{ fontSize: 12, color: '#9ca3af' }}>
                        Camera: {alert.cid ?? alert.cam ?? '—'}
                      </p>
                    </div>
                  </div>
                  <p style={{ fontSize: 10, color: '#4b5563', marginTop: 8 }}>
                    Time:{' '}
                    {alert.ts
                      ? new Date(alert.ts).toLocaleString()
                      : new Date().toLocaleTimeString()}
                  </p>
                </motion.div>
              ))
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
