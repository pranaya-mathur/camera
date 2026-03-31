import React, { useState } from 'react';
import axios from 'axios';
import { API_BASE } from './config';

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      // OAuth2 password flow expects application/x-www-form-urlencoded (not multipart FormData).
      const body = new URLSearchParams();
      body.set('username', email);
      body.set('password', password);
      const resp = await axios.post(`${API_BASE}/auth/login`, body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      localStorage.setItem('token', resp.data.access_token);
      localStorage.setItem('role', resp.data.role);
      onLogin();
    } catch (err) {
      setError('Invalid email or password');
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center' }}>
      <div className="glass-card animate-fade" style={{ padding: 40, width: 400 }}>
        <h2 style={{ marginBottom: 24, textAlign: 'center' }}>SecureVU Login</h2>
        <form onSubmit={handleLogin}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 13, color: '#9ca3af', marginBottom: 6, display: 'block' }}>Email</label>
            <input 
              type="text" className="input-field" 
              value={email} onChange={e => setEmail(e.target.value)} required 
            />
          </div>
          <div style={{ marginBottom: 24 }}>
            <label style={{ fontSize: 13, color: '#9ca3af', marginBottom: 6, display: 'block' }}>Password</label>
            <input 
              type="password" className="input-field" 
              value={password} onChange={e => setPassword(e.target.value)} required 
            />
          </div>
          {error && <p style={{ color: '#ef4444', fontSize: 13, marginBottom: 16 }}>{error}</p>}
          <button type="submit" className="dark-button" style={{ width: '100%' }}>Enter Dashboard</button>
        </form>
      </div>
    </div>
  );
}
