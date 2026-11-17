import { Cloud, LockKeyhole, Mail } from "lucide-react";
import { useState } from "react";

export default function Login({ busy, error, onLogin, onRegister, allowRegistration = true }) {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  function submit(event) {
    event.preventDefault();
    if (registering) {
      if (password !== confirmPassword) return;
      onRegister(email, password);
    } else {
      onLogin(email, password);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center px-5 py-10">
      <section className="w-full max-w-sm rounded-3xl border border-slate-100 bg-white p-7 shadow-card sm:p-9">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-brand-600 text-white shadow-lg shadow-blue-200">
          <Cloud size={24} strokeWidth={2.5} />
        </div>
        <h1 className="mt-5 text-center font-display text-2xl font-extrabold text-ink">
          {registering ? "Create your CloudVault account" : "Sign in to CloudVault"}
        </h1>
        <p className="mt-2 text-center text-sm leading-6 text-slate-500">
          {registering ? "Register to start managing your files." : "Enter your access password to manage your files."}
        </p>
        <form className="mt-7" onSubmit={submit}>
          <label className="block text-xs font-bold text-slate-600" htmlFor="access-email">
            Email address
          </label>
          <div className="mt-2 flex items-center gap-2 rounded-xl border border-slate-200 px-3 focus-within:border-brand-500">
            <Mail className="shrink-0 text-slate-400" size={17} />
            <input
              autoComplete="username"
              className="min-w-0 flex-1 py-3 text-sm text-ink outline-none"
              disabled={busy}
              id="access-email"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              required
              type="email"
              value={email}
            />
          </div>
          <label className="mt-4 block text-xs font-bold text-slate-600" htmlFor="access-password">
            Access password
          </label>
          <div className="mt-2 flex items-center gap-2 rounded-xl border border-slate-200 px-3 focus-within:border-brand-500">
            <LockKeyhole className="shrink-0 text-slate-400" size={17} />
            <input
              autoComplete={registering ? "new-password" : "current-password"}
              className="min-w-0 flex-1 py-3 text-sm text-ink outline-none"
              disabled={busy}
              id="access-password"
              onChange={(event) => setPassword(event.target.value)}
              minLength={registering ? 12 : undefined}
              type="password"
              value={password}
              required
            />
          </div>
          {registering && (
            <p className="mt-2 text-xs text-slate-400">Use at least 12 characters.</p>
          )}
          {registering && (
            <>
              <label className="mt-4 block text-xs font-bold text-slate-600" htmlFor="confirm-password">
                Confirm password
              </label>
              <div className="mt-2 flex items-center gap-2 rounded-xl border border-slate-200 px-3 focus-within:border-brand-500">
                <LockKeyhole className="shrink-0 text-slate-400" size={17} />
                <input
                  autoComplete="new-password"
                  className="min-w-0 flex-1 py-3 text-sm text-ink outline-none"
                  disabled={busy}
                  id="confirm-password"
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  type="password"
                  value={confirmPassword}
                  required
                />
              </div>
            </>
          )}
          {error && (
            <p className="mt-3 text-sm text-rose-700" role="alert">
              {error}
            </p>
          )}
          <button
            className="mt-5 w-full rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={busy || !email || !password || (registering && (!confirmPassword || password !== confirmPassword))}
            type="submit"
          >
            {busy ? (registering ? "Creating account..." : "Signing in...") : (registering ? "Create account" : "Sign in")}
          </button>
          {allowRegistration && <button
            className="mt-3 w-full text-sm font-semibold text-brand-700 hover:underline"
            disabled={busy}
            onClick={() => { setRegistering((current) => !current); setPassword(""); setConfirmPassword(""); }}
            type="button"
          >
            {registering ? "Already have an account? Sign in" : "New user? Register first"}
          </button>}
        </form>
      </section>
    </main>
  );
}
