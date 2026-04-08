import React, { useEffect, useMemo, useState } from 'react';
import { Camera, Bell, Shield, LogOut, Search, Settings, AlertTriangle, Film, ExternalLink, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, EyeOff } from 'lucide-react';
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
  const [privacyMode, setPrivacyMode] = useState(false);
  const [clipPlayError, setClipPlayError] = useState({});
  /** When false, customer-style roles do not get MJPEG (basic_suite default: internal mode). */
  const [liveFeedForUser, setLiveFeedForUser] = useState(true);
  /** Operators see MP4 clip links; viewers get snapshots only. */
  const [clipMediaForUser, setClipMediaForUser] = useState(false);
  const accessToken = localStorage.getItem('token') || '';

  useEffect(() => {
    let cancelled = false;
    const token = localStorage.getItem('token');
    if (!token) {
      onLogout();
      return;
    }
    const auth = { Authorization: `Bearer ${token}` };

    (async () => {
      try {
        const rc = await fetch(`${API_BASE}/cameras`, { headers: auth });
        if (rc.status === 401) {
          onLogout();
          return;
        }
        if (rc.ok) {
          const d = await rc.json();
          const list = d.cameras || [];
          // Always show at least one tile so MJPEG + layout work if API returns [].
          if (!cancelled) {
            setCameras(
              list.length > 0 ? list : [{ id: 'main', name: 'Main Camera' }],
            );
          }
        } else if (!cancelled) {
          setCameras([{ id: 'main', name: 'Main Camera' }]);
        }

        const rs = await fetch(`${API_BASE}/control-plane/status`, { headers: auth });
        if (rs.status === 401) {
          onLogout();
          return;
        }
        if (rs.ok) {
          const sd = await rs.json();
          if (!cancelled) setPrivacyMode(!!sd.privacy_mode);
        }

        const ren = await fetch(`${API_BASE}/entitlements`, { headers: auth });
        if (ren.ok) {
          const en = await ren.json();
          if (!cancelled && typeof en.live_feed_for_user === 'boolean') {
            setLiveFeedForUser(en.live_feed_for_user);
          }
          if (!cancelled && typeof en.clip_media_for_user === 'boolean') {
            setClipMediaForUser(en.clip_media_for_user);
          }
        }

        const ra = await fetch(`${API_BASE}/alerts`, { headers: auth });
        if (ra.status === 401) {
          onLogout();
          return;
        }
        if (ra.ok) {
          const ad = await ra.json();
          const list = ad.alerts || [];
          if (!cancelled) setAlerts([...list].reverse().slice(0, 50));
        }
      } catch {
        if (!cancelled && localStorage.getItem('token')) {
          setCameras([{ id: 'main', name: 'Main Camera' }]);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [onLogout]);

  const handlePTZ = async (camId, action) => {
    try {
      await fetch(`${API_BASE}/cameras/${camId}/ptz?action=${action}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
    } catch (e) {
      console.error("PTZ error", e);
    }
  };

  useEffect(() => {
    const tok = localStorage.getItem('token');
    const wsUrl = tok ? `${WS_URL}?token=${encodeURIComponent(tok)}` : WS_URL;
    const ws = new WebSocket(wsUrl);
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
            <p style={{ fontSize: 13, color: '#9ca3af', display: 'flex', alignItems: 'center', gap: 8 }}>
              Role: <span style={{ color: '#3b82f6' }}>{userRole.toUpperCase()}</span>
              {privacyMode && (
                <span style={{ color: '#ef4444', display: 'flex', alignItems: 'center', gap: 4, marginLeft: 12, fontSize: 11, background: 'rgba(239, 68, 68, 0.1)', padding: '2px 8px', borderRadius: 12 }}>
                  <EyeOff size={14} /> Privacy Active
                </span>
              )}
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
                  [CAM] {cam.name}
                </p>
              </div>

              {cam.has_ptz && (
                <div style={{ position: 'absolute', bottom: 12, right: 12, zIndex: 20, display: 'flex', flexDirection: 'column', gap: 4, background: 'rgba(0,0,0,0.4)', padding: 8, borderRadius: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'center' }}>
                    <ChevronUp size={20} cursor="pointer" onClick={() => handlePTZ(cam.id, 'UP')} />
                  </div>
                  <div style={{ display: 'flex', gap: 12 }}>
                    <ChevronLeft size={20} cursor="pointer" onClick={() => handlePTZ(cam.id, 'LEFT')} />
                    <ChevronRight size={20} cursor="pointer" onClick={() => handlePTZ(cam.id, 'RIGHT')} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'center' }}>
                    <ChevronDown size={20} cursor="pointer" onClick={() => handlePTZ(cam.id, 'DOWN')} />
                  </div>
                  <div style={{ display: 'flex', gap: 12, marginTop: 4, borderTop: '1px solid #555', paddingTop: 4 }}>
                    <ZoomIn size={18} cursor="pointer" onClick={() => handlePTZ(cam.id, 'ZOOM_IN')} />
                    <ZoomOut size={18} cursor="pointer" onClick={() => handlePTZ(cam.id, 'ZOOM_OUT')} />
                  </div>
                </div>
              )}

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
                {liveFeedForUser && accessToken && cam.id ? (
                  <img
                    src={`${API_BASE}/video/${encodeURIComponent(cam.id)}?token=${encodeURIComponent(accessToken)}`}
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
                ) : (
                  <p
                    style={{
                      position: 'absolute',
                      zIndex: 2,
                      padding: '12px 16px',
                      fontSize: 12,
                      color: '#9ca3af',
                      textAlign: 'center',
                      maxWidth: '90%',
                    }}
                  >
                    Live video is not available for your role (alerts only). Operators use admin /
                    manager / operator accounts for preview when enabled.
                  </p>
                )}
                <Camera size={48} color="#1f2937" />
                {privacyMode && (
                  <div style={{ position: 'absolute', zIndex: 5, padding: '8px 16px', background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(8px)', borderRadius: 8, fontSize: 10, color: '#9ca3af' }}>
                    Privacy Filter Engaged
                  </div>
                )}
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
            {filteredAlerts.length} shown · hazard · zones · vehicles · snapshots / clips
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
                        {alert.image && accessToken ? (
                          <>
                            <img
                              src={`${API_BASE}${alert.image}?token=${encodeURIComponent(accessToken)}`}
                              alt="Alert snapshot"
                              style={{
                                width: '100%',
                                maxHeight: 240,
                                marginTop: 10,
                                borderRadius: 8,
                                objectFit: 'contain',
                                background: '#111',
                              }}
                            />
                            <a
                              href={`${API_BASE}${alert.image}?token=${encodeURIComponent(accessToken)}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              download
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
                              Download snapshot
                            </a>
                          </>
                        ) : null}
                        {alert.clip && clipMediaForUser && accessToken ? (
                          <>
                            <video
                              controls
                              playsInline
                              preload="metadata"
                              src={`${API_BASE}${alert.clip}?token=${encodeURIComponent(accessToken)}`}
                              onError={() =>
                                setClipPlayError((p) => ({
                                  ...p,
                                  [`${alert.ts}-${i}`]: true,
                                }))
                              }
                              style={{
                                width: '100%',
                                maxHeight: 220,
                                marginTop: 10,
                                borderRadius: 8,
                                background: '#000',
                              }}
                            />
                            {clipPlayError[`${alert.ts}-${i}`] ? (
                              <p style={{ fontSize: 11, color: '#fbbf24', marginTop: 6 }}>
                                Browser could not decode this clip (common on Safari with OpenCV mp4v).
                                Install <code style={{ color: '#e5e7eb' }}>ffmpeg</code> and restart the
                                suite so clips are saved as H.264, or try Chrome — or use download below.
                              </p>
                            ) : null}
                            <a
                              href={`${API_BASE}${alert.clip}?token=${encodeURIComponent(accessToken)}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              download
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
                              Open / download recording
                            </a>
                          </>
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
