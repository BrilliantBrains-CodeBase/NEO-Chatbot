import "./auth.css";

// The sign-in area: one centred card, as in the approved design.
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="auth">
      <div className="card">{children}</div>
    </main>
  );
}
