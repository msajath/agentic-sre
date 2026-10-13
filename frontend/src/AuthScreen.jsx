import { useEffect, useState } from 'react';
import './AuthScreen.css';

const initialRegistration = {
  full_name: '', username: '', email: '', password: '', confirmPassword: '',
};

function errorMessage(detail, fallback) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => item.msg).join(' ');
  return fallback;
}

export default function AuthScreen({ apiBase, onAuthenticated }) {
  const [view, setView] = useState(window.location.pathname === '/signup' ? 'signup' : 'login');
  const [login, setLogin] = useState({ username: '', password: '' });
  const [registration, setRegistration] = useState(initialRegistration);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const syncView = () => {
      const path = window.location.pathname;
      setView(path === '/signup' ? 'signup' : 'login');
      if (path !== '/login' && path !== '/signup') window.history.replaceState(null, '', '/login');
    };
    syncView();
    window.addEventListener('popstate', syncView);
    return () => window.removeEventListener('popstate', syncView);
  }, []);

  const selectView = (nextView) => {
    if (busy) return;
    setError('');
    setView(nextView);
    window.history.pushState(null, '', nextView === 'signup' ? '/signup' : '/login');
  };

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    if (view === 'signup' && registration.password !== registration.confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    const path = view === 'login' ? 'login' : 'register';
    const body = view === 'login'
      ? login
      : {
          full_name: registration.full_name.trim(),
          username: registration.username.trim(),
          email: registration.email.trim(),
          password: registration.password,
        };

    setBusy(true);
    try {
      const response = await fetch(`${apiBase}/api/v1/auth/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(errorMessage(data.detail, view === 'login' ? 'Sign in failed.' : 'Sign up failed.'));
      setLogin({ username: '', password: '' });
      setRegistration(initialRegistration);
      onAuthenticated(data);
    } catch (requestError) {
      setError(requestError.message || 'Unable to connect. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const updateLogin = (field) => (event) => setLogin(current => ({ ...current, [field]: event.target.value }));
  const updateRegistration = (field) => (event) => setRegistration(current => ({ ...current, [field]: event.target.value }));

  return (
    <main className="auth-page">
      <div className="auth-shell">
        <section className="auth-intro" aria-label="About Agentic SRE">
          <div className="auth-brand">
            <span className="auth-brand-mark" aria-hidden="true">S</span>
            <span>Agentic SRE <small>Sentinel Platform</small></span>
          </div>
          <div className="auth-intro-body">
            <span className="auth-eyebrow"><span className="auth-live-dot" /> Your operations workspace</span>
            <h1>See incidents clearly.<br /><em>Act with confidence.</em></h1>
            <p>Follow live service signals, investigate causes, and guide recovery through a human approval step.</p>
            <div className="auth-flow" aria-label="Platform workflow">
              <div><span>01</span><strong>Observe</strong><small>Spot service changes early</small></div>
              <div><span>02</span><strong>Investigate</strong><small>Follow the evidence</small></div>
              <div><span>03</span><strong>Recover</strong><small>Approve the next step</small></div>
            </div>
          </div>
          <p className="auth-intro-footer">A guided workspace for safer incident response.</p>
        </section>

        <section className="auth-panel" aria-labelledby="auth-title">
          <div className="auth-panel-inner">
            <div className="auth-mobile-brand">Agentic SRE <span>Sentinel Platform</span></div>
            <div className="auth-tabs" role="tablist" aria-label="Account access">
              <button type="button" role="tab" aria-selected={view === 'login'} className={view === 'login' ? 'active' : ''} onClick={() => selectView('login')}>Login</button>
              <button type="button" role="tab" aria-selected={view === 'signup'} className={view === 'signup' ? 'active' : ''} onClick={() => selectView('signup')}>Sign Up</button>
            </div>

            <div className="auth-heading">
              <span>{view === 'login' ? 'WELCOME BACK' : 'JOIN THE WORKSPACE'}</span>
              <h2 id="auth-title">{view === 'login' ? 'Log in to your account' : 'Create your account'}</h2>
              <p>{view === 'login' ? 'Enter your credentials to open the operations dashboard.' : 'Start with read-only access to incidents and service health.'}</p>
            </div>

            <form className="auth-form" onSubmit={submit}>
              {view === 'signup' && (
                <>
                  <label htmlFor="signup-name">Full name</label>
                  <input id="signup-name" type="text" autoComplete="name" maxLength="128" value={registration.full_name} onChange={updateRegistration('full_name')} placeholder="Your name" required />
                </>
              )}

              <label htmlFor="auth-username">Username</label>
              <input id="auth-username" type="text" autoComplete="username" minLength="3" maxLength="32" pattern="[A-Za-z0-9_-]+" value={view === 'login' ? login.username : registration.username} onChange={view === 'login' ? updateLogin('username') : updateRegistration('username')} placeholder="Enter your username" required />

              {view === 'signup' && (
                <>
                  <label htmlFor="signup-email">Email address</label>
                  <input id="signup-email" type="email" autoComplete="email" maxLength="128" value={registration.email} onChange={updateRegistration('email')} placeholder="you@example.com" required />
                </>
              )}

              <label htmlFor="auth-password">Password</label>
              <input id="auth-password" type="password" autoComplete={view === 'login' ? 'current-password' : 'new-password'} minLength={view === 'signup' ? 12 : 6} maxLength="128" value={view === 'login' ? login.password : registration.password} onChange={view === 'login' ? updateLogin('password') : updateRegistration('password')} placeholder={view === 'signup' ? 'At least 12 characters' : 'Enter your password'} required />

              {view === 'signup' && (
                <>
                  <label htmlFor="signup-confirm">Confirm password</label>
                  <input id="signup-confirm" type="password" autoComplete="new-password" minLength="12" maxLength="128" value={registration.confirmPassword} onChange={updateRegistration('confirmPassword')} placeholder="Enter password again" required />
                  <p className="auth-access-note">New accounts receive Viewer access. An administrator can grant higher permissions.</p>
                </>
              )}

              {error && <p className="auth-error" role="alert">{error}</p>}
              <button className="auth-submit" type="submit" disabled={busy}>
                {busy ? (view === 'login' ? 'Logging in…' : 'Creating account…') : (view === 'login' ? 'Log in' : 'Create account')}
                {!busy && <span aria-hidden="true">→</span>}
              </button>
            </form>

            <p className="auth-switch">
              {view === 'login' ? 'New to Agentic SRE?' : 'Already have an account?'}{' '}
              <button type="button" onClick={() => selectView(view === 'login' ? 'signup' : 'login')}>
                {view === 'login' ? 'Create an account' : 'Log in'}
              </button>
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
