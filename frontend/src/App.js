import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Authenticator } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';
import Dashboard from './pages/Dashboard';
import SessionDetail from './pages/SessionDetail';
import ProgressPage from './pages/ProgressPage';
import './App.css';

function App() {
  return (
    <Authenticator
      loginMechanisms={['email']}
      signUpAttributes={['given_name']}
    >
      {({ signOut, user }) => (
        <Router>
          <div className="app">
            <header className="app-header">
              <div className="header-brand">
                <span className="brand-logo">◎</span>
                <span className="brand-name">Qleam</span>
              </div>
              <div className="header-user">
                <span className="user-name">
                  {user?.signInDetails?.loginId || user?.username}
                </span>
                <button className="sign-out-btn" onClick={signOut}>
                  Sign Out
                </button>
              </div>
            </header>
            <main className="app-main">
              <Routes>
                <Route path="/" element={<Dashboard user={user} />} />
                <Route path="/session/:sessionId" element={<SessionDetail />} />
                <Route path="/progress/:childId" element={<ProgressPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
        </Router>
      )}
    </Authenticator>
  );
}

export default App;
