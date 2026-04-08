import React, { useState } from 'react';
import axios from 'axios';
import { API_BASE } from './config';

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [mode, setMode] = useState('login'); // 'login' | 'register'

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    const em = email.trim();
    try {
      // OAuth2 password flow expects application/x-www-form-urlencoded (not multipart FormData).
      const body = new URLSearchParams();
      body.set('username', em);
      body.set('password', password);
      const resp = await axios.post(`${API_BASE}/auth/login`, body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      localStorage.setItem('token', resp.data.access_token);
      localStorage.setItem('role', resp.data.role);
      onLogin();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : 'Invalid email or password. Create an account first if you have not registered.',
      );
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError('');
    const em = email.trim();
    if (!em || !password) {
      setError('Enter email and password');
      return;
    }
    try {
      const q = new URLSearchParams({
        email: em,
        password,
        role: 'admin',
      });
      await axios.post(`${API_BASE}/auth/register?${q.toString()}`);
      setError('');
      setMode('login');
      // Auto-login after register
      const body = new URLSearchParams();
      body.set('username', em);
      body.set('password', password);
      const resp = await axios.post(`${API_BASE}/auth/login`, body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      localStorage.setItem('token', resp.data.access_token);
      localStorage.setItem('role', resp.data.role);
      onLogin();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Registration failed');
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center' }}>
      <div className="glass-card animate-fade" style={{ padding: 40, width: 400 }}>
        <h2 style={{ marginBottom: 24, textAlign: 'center' }}>
          {mode === 'login' ? 'SecureVU Login' : 'Create account'}
        </h2>
        <form onSubmit={mode === 'login' ? handleLogin : handleRegister}>
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
          <button type="submit" className="dark-button" style={{ width: '100%' }}>
            {mode === 'login' ? 'Enter Dashboard' : 'Register and sign in'}
          </button>
        </form>
        <p style={{ marginTop: 20, textAlign: 'center', fontSize: 13, color: '#9ca3af' }}>
          {mode === 'login' ? (
            <>
              First time?{' '}
              <button
                type="button"
                className="link-button"
                style={{ background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer' }}
                onClick={() => { setMode('register'); setError(''); }}
              >
                Create account
              </button>
            </>
          ) : (
            <>
              Already have an account?{' '}
              <button
                type="button"
                className="link-button"
                style={{ background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer' }}
                onClick={() => { setMode('login'); setError(''); }}
              >
                Back to login
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
