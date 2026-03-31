import React, { useEffect, useMemo, useState } from 'react';
import { Camera, Bell, Shield, LogOut, Search, Settings, AlertTriangle, Film, ExternalLink } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { API_BASE, WS_URL } from './config';

const SEVERITY_STYLE = {
  critical: { bg: 'rgba(239, 68, 68, 0.15)', border: 'rgba(239, 68, 68, 0.35)', icon: '#ef4444' },
  warning: { bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.35)', icon: '#f59e0b' },
  info: { bg: 'rgba(59, 130, 246, 0.1)', border: 'rgba(59, 130, 246, 0.25)', icon: '#3b82f6' },
};

function alertStyle(sev) {
  return SEVERITY_STYLE[sev] || SEVERITY_STYLE.info;
}

export default function Dashboard({ userRole, onLogout }) {
  const [alerts, setAlerts] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [typeFilter, setTypeFilter] = useState('all');
  const [searchCam, setSearchCam] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/cameras`)
      .then((r) => r.json())
      .then((d) => setCameras(d.cameras || []))
      .catch(() => setCameras([{ id: 'main', name: 'Main Camera' }]));

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
      try {
        const data = JSON.parse(e.data);
        setAlerts((prev) => [data, ...prev].slice(0, 50));
      } catch {
        /* ignore non-JSON */
      }
    };
    ws.onerror = () => {
      console.warn('[SecureVU] WebSocket error — is the backend running on :8000?');
    };
    return () => {
      try {
        ws.close();
      } catch {
        /* noop */
      }
    };
  }, []);

  const typeOptions = useMemo(() => {
    const s = new Set();
    alerts.forEach((a) => {
      if (a.type) s.add(a.type);
    });
    return ['all', ...Array.from(s).sort()];
  }, [alerts]);

  const filteredAlerts = useMemo(() => {
    const q = searchCam.trim().toLowerCase();
    return alerts.filter((a) => {
      if (typeFilter !== 'all' && (a.type || '') !== typeFilter) return false;
      if (!q) return true;
      const cam = String(a.cid ?? a.cam ?? '').toLowerCase();
      return cam.includes(q);
    });
  }, [alerts, typeFilter, searchCam]);

  const filteredCameras = useMemo(() => {
    const q = searchCam.trim().toLowerCase();
    if (!q) return cameras;
    return cameras.filter(
      (c) =>
        String(c.id || '').toLowerCase().includes(q) ||
        String(c.name || '').toLowerCase().includes(q)
    );
  }, [cameras, searchCam]);

  return (
    <div style={{ display: 'flex', height: '100vh', padding: 16, gap: 16 }}>
      <div
        className="glass-card"
        style={{
          width: 80,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '24px 0',
        }}
      >
        <Shield size={32} color="#3b82f6" style={{ marginBottom: 40 }} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24, flex: 1 }}>
          <Camera size={24} color="#f3f4f6" cursor="pointer" />
          <Bell size={24} color="#9ca3af" cursor="pointer" />
          <Settings size={24} color="#9ca3af" cursor="pointer" />
        </div>
        <LogOut size={24} color="#ef4444" cursor="pointer" onClick={onLogout} />
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div
          className="glass-card"
          style={{
            padding: '0 24px',
            height: 80,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <div>
            <h1 style={{ fontSize: 20 }}>SecureVU Command Center</h1>
            <p style={{ fontSize: 13, color: '#9ca3af' }}>
              Role: <span style={{ color: '#3b82f6' }}>{userRole.toUpperCase()}</span>
            </p>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <div
              className="input-field"
              style={{
                width: 220,
                display: 'flex',
                alignItems: 'center',
                padding: '0 12px',
              }}
            >
              <Search size={18} color="#4b5563" />
              <input
                type="text"
                placeholder="Filter cameras / alerts…"
                value={searchCam}
                onChange={(e) => setSearchCam(e.target.value)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'white',
                  marginLeft: 8,
                  flex: 1,
                  outline: 'none',
                }}
              />
            </div>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="input-field"
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid #374151',
                background: 'rgba(0,0,0,0.3)',
                color: '#e5e7eb',
                fontSize: 13,
                minWidth: 180,
              }}
            >
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  {t === 'all' ? 'All alert types' : t}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
          {filteredCameras.map((cam, idx) => (
            <motion.div
              key={cam.id || idx}
              className="glass-card"
              whileHover={{ scale: 1.01 }}
              style={{ position: 'relative', overflow: 'hidden', minHeight: 250 }}
            >
              <div
                style={{
                  position: 'absolute',
                  top: 12,
                  left: 12,
                  padding: '4px 8px',
                  borderRadius: 4,
                  background: 'rgba(0,0,0,0.5)',
                  zIndex: 10,
                }}
              >
                <p style={{ fontSize: 12, fontWeight: 600 }}>
                  [CAM {idx + 1}] {cam.name}
                </p>
              </div>
              <div
                style={{
                  height: '100%',
                  width: '100%',
                  background: '#000',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <img
                  src={`${API_BASE}/video/${cam.id}`}
                  alt={cam.name}
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    position: 'absolute',
                    top: 0,
                    left: 0,
                  }}
                  onError={() => {}}
                />
                <Camera size={48} color="#1f2937" />
                <p style={{ position: 'absolute', fontSize: 10, color: '#4b5563', bottom: 12 }}>
                  Live feed
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      <div
        className="glass-card"
        style={{
          width: 380,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: 24, paddingBottom: 16, borderBottom: '1px solid #333' }}>
          <h3 style={{ fontSize: 16 }}>Live Intelligence Feed</h3>
          <p style={{ fontSize: 11, color: '#6b7280', marginTop: 6 }}>
            {filteredAlerts.length} shown · hazard · zones · vehicles · open-vocab · clips
          </p>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
          <AnimatePresence>
            {filteredAlerts.length === 0 ? (
              <p style={{ textAlign: 'center', color: '#4b5563', marginTop: 40, fontSize: 13 }}>
                No events match filters…
              </p>
            ) : (
              filteredAlerts.map((alert, i) => {
                const st = alertStyle(alert.severity);
                const title =
                  (alert.label || alert.type || 'Alert').toString();
                const typeLine = alert.type ? String(alert.type) : '';
                return (
                  <motion.div
                    initial={{ x: 20, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    key={`${alert.ts}-${i}-${typeLine}`}
                    className="glass-card"
                    style={{
                      padding: 12,
                      marginBottom: 12,
                      background: st.bg,
                      borderColor: st.border,
                      borderWidth: 1,
                      borderStyle: 'solid',
                    }}
                  >
                    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                      <div
                        style={{
                          background: st.icon,
                          padding: 8,
                          borderRadius: 8,
                          flexShrink: 0,
                        }}
                      >
                        {alert.type === 'clip_ready' ? (
                          <Film size={18} color="white" />
                        ) : (
                          <AlertTriangle size={18} color="white" />
                        )}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontSize: 13, fontWeight: 700, lineHeight: 1.35 }}>{title}</p>
                        {typeLine ? (
                          <p style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>{typeLine}</p>
                        ) : null}
                        <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
                          Camera: {alert.cid ?? alert.cam ?? '—'}
                        </p>
                        {alert.zone_name ? (
                          <p style={{ fontSize: 11, color: '#a78bfa', marginTop: 2 }}>
                            Zone: {alert.zone_name}
                          </p>
                        ) : null}
                        {alert.clip ? (
                          <a
                            href={`${API_BASE}${alert.clip}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 6,
                              fontSize: 12,
                              color: '#60a5fa',
                              marginTop: 8,
                            }}
                          >
                            <ExternalLink size={14} />
                            Open recording
                          </a>
                        ) : null}
                      </div>
                    </div>
                    <p style={{ fontSize: 10, color: '#4b5563', marginTop: 8 }}>
                      {alert.ts
                        ? new Date(alert.ts).toLocaleString()
                        : new Date().toLocaleTimeString()}
                    </p>
                  </motion.div>
                );
              })
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
