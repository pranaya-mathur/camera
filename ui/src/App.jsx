import React, { useState, useEffect } from 'react';
import Login from './Login';
import Dashboard from './Dashboard';
import './index.css';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(!!localStorage.getItem('token'));
  const [userRole, setUserRole] = useState(localStorage.getItem('role') || 'guest');

  const handleLogin = () => {
    setIsLoggedIn(true);
    setUserRole(localStorage.getItem('role') || 'home');
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    setIsLoggedIn(false);
  };

  return (
    <div className="App">
      {!isLoggedIn ? (
        <Login onLogin={handleLogin} />
      ) : (
        <Dashboard userRole={userRole} onLogout={handleLogout} />
      )}
    </div>
  );
}

export default App;
