import { FormEvent, ReactNode, useEffect, useState } from 'react';

const API = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');
type User = { id: string; name: string; email: string };
type Profile = {
  monthly_income: number | null;
  credit_score: number | null;
  annual_fee_max: number;
  reward_preference: string;
  spending: Record<string, number>;
};
const blankProfile = (): Profile => ({
  monthly_income: null, credit_score: null, annual_fee_max: 1500, reward_preference: 'cashback',
  spending: { shopping: 0, dining: 0, fuel: 0, travel: 0, grocery: 0, utilities: 0 },
});
const categories = ['shopping', 'dining', 'fuel', 'travel', 'grocery', 'utilities'];
const messageOf = (data: any, fallback: string) => typeof data?.detail === 'string' ? data.detail : data?.detail?.message || fallback;

export default function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [screen, setScreen] = useState<'loading'|'login'|'signup'|'onboarding'|'ready'|'error'>('loading');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [profile, setProfile] = useState<Profile>(blankProfile());

  async function loadProfile() {
    const response = await fetch(API + '/api/profile');
    if (!response.ok) throw new Error('Could not load your profile. Please try again.');
    const data = await response.json();
    if (data.complete && data.profile) {
      setProfile({ ...blankProfile(), ...data.profile, spending: { ...blankProfile().spending, ...data.profile.spending } });
      setScreen('ready');
    } else {
      setProfile(blankProfile());
      setScreen('onboarding');
    }
  }

  useEffect(() => {
    let active = true;
    fetch(API + '/api/auth/me').then(async response => {
      if (!active) return;
      if (response.status === 401) { setScreen('login'); return; }
      const data = await response.json();
      if (!response.ok) throw new Error(messageOf(data, 'CardLens is temporarily unavailable.'));
      setUser(data.user);
      await loadProfile();
    }).catch(err => { if (active) { setError(err.message); setScreen('error'); } });
    return () => { active = false; };
  }, []);

  async function authenticate(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const endpoint = screen === 'signup' ? 'signup' : 'login';
      const response = await fetch(API + '/api/auth/' + endpoint, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(screen === 'signup' ? { name, email, password } : { email, password }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(messageOf(data, 'Unable to sign in. Please check your details.'));
      setUser(data.user);
      if (endpoint === 'signup') { setProfile(blankProfile()); setScreen('onboarding'); }
      else await loadProfile();
    } catch (err: any) { setError(err.message || 'Unable to sign in. Please try again.'); }
    finally { setBusy(false); }
  }

  async function finishOnboarding(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch(API + '/api/profile', {
        method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(profile),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(messageOf(data, 'Your profile could not be saved.'));
      setScreen('ready');
    } catch (err: any) { setError(err.message || 'Your profile could not be saved.'); }
    finally { setBusy(false); }
  }

  async function logout() {
    if (!window.confirm('Sign out of CardLens AI?')) return;
    setBusy(true);
    try {
      await fetch(API + '/api/auth/logout', { method: 'POST' });
      setUser(null); setProfile(blankProfile()); setScreen('login');
    } catch { setError('Could not sign out. Please retry.'); }
    finally { setBusy(false); }
  }

  if (screen === 'loading') return <div className="auth-loading" role="status">Opening your CardLens workspace…</div>;
  if (screen === 'ready' && user) return <div className="account-shell"><header className="account-bar"><a className="account-brand" href="#">cardlens <span>AI</span></a><div><span className="account-greeting">Welcome, {user.name}</span><button onClick={logout} disabled={busy} className="account-logout">Sign out</button></div></header>{children}</div>;
  if (screen === 'error') return <main className="auth-screen"><section className="auth-card"><a className="account-brand" href="#">cardlens <span>AI</span></a><h1>Your workspace is unavailable</h1><p>{error}</p><button className="auth-submit" onClick={()=>{setError('');setScreen('login')}}>Try again</button></section></main>;

  if (screen === 'onboarding') return <main className="auth-screen"><section className="auth-card onboarding-card">
    <a className="account-brand" href="#">cardlens <span>AI</span></a>
    <div className="auth-eyebrow">YOUR PROFILE · STEP 1 OF 1</div><h1>Start with your spending.</h1>
    <p>Share only what helps us rank cards. Never enter card numbers, CVV, or bank passwords. Your profile is saved to your account and can be edited later.</p>
    <form onSubmit={finishOnboarding}>
      <div className="onboarding-fields">
        <label>Monthly income (₹)<input type="number" min="0" value={profile.monthly_income ?? ''} onChange={e=>setProfile({...profile,monthly_income:e.target.value===''?null:+e.target.value})} placeholder="Optional"/></label>
        <label>Credit score<input type="number" min="300" max="900" value={profile.credit_score ?? ''} onChange={e=>setProfile({...profile,credit_score:e.target.value===''?null:+e.target.value})} placeholder="Optional"/></label>
        <label>Annual fee limit (₹)<input type="number" min="0" value={profile.annual_fee_max} onChange={e=>setProfile({...profile,annual_fee_max:+e.target.value})}/></label>
        <label>Reward preference<select value={profile.reward_preference} onChange={e=>setProfile({...profile,reward_preference:e.target.value})}><option value="cashback">Cashback</option><option value="travel">Travel</option><option value="fuel">Fuel</option><option value="rewards">Flexible rewards</option></select></label>
      </div>
      <h2>Typical monthly spend</h2><div className="onboarding-fields spend-onboarding">{categories.map(key=><label key={key}>{key[0].toUpperCase()+key.slice(1)} (₹)<input type="number" min="0" value={profile.spending[key] ?? 0} onChange={e=>setProfile({...profile,spending:{...profile.spending,[key]:Math.max(0,+e.target.value)}})}/></label>)}</div>
      {error&&<p className="auth-error" role="alert">{error}</p>}
      <button className="auth-submit" disabled={busy}>{busy?'Saving your profile…':'Save profile and continue'}</button>
      <button type="button" className="auth-back" disabled={busy} onClick={logout}>Sign out</button>
    </form>
  </section></main>;

  const signup = screen === 'signup';
  return <main className="auth-screen"><section className="auth-card">
    <div className="auth-brand-row"><a className="account-brand" href="#">cardlens <span>AI</span></a><span className="auth-security">Private by design</span></div>
    <div className="auth-eyebrow">PERSONAL CREDIT CARD INSIGHTS</div>
    <h1>{signup?'A smarter match starts here.':'Welcome back.'}</h1>
    <p>{signup?'Create an account to keep your profile and recommendations with you.':'Sign in to continue to your personalized workspace.'}</p>
    <form onSubmit={authenticate}>
      {signup&&<label>Your name<input required autoComplete="name" maxLength={120} value={name} onChange={e=>setName(e.target.value)} placeholder="Name"/></label>}
      <label>Email address<input required type="email" autoComplete="email" maxLength={320} value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com"/></label>
      <label>Password<input required type="password" autoComplete={signup?'new-password':'current-password'} minLength={signup?10:1} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)} placeholder={signup?'At least 10 characters, with letters and numbers':'Your password'}/></label>
      {signup&&<small className="auth-hint">Use 10+ characters with at least one letter and one number.</small>}
      {error&&<p className="auth-error" role="alert">{error}</p>}
      <button className="auth-submit" disabled={busy}>{busy?(signup?'Creating account…':'Signing in…'):(signup?'Create account':'Sign in')}</button>
    </form>
    <p className="auth-switch">{signup?'Already have an account?':'New to CardLens?'} <button onClick={()=>{setError('');setScreen(signup?'login':'signup')}}>{signup?'Sign in':'Create an account'}</button></p>
    <p className="auth-disclaimer">Recommendations are estimates. CardLens never guarantees issuer approval. Catalog terms may be illustrative; confirm current terms with the issuer.</p>
  </section><aside className="auth-aside"><div className="auth-orbit">C</div><span>CLARITY FOR EVERYDAY CHOICES</span><h2>Your spending,<br/>understood.</h2><p>Compare transparent estimates, explore what-if scenarios, and ask questions in your preferred way.</p></aside></main>;
}
