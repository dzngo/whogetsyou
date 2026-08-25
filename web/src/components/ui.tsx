import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

// ---- Page shell ----------------------------------------------------
export function PageShell({ children }: { children: ReactNode }) {
  return (
    <main className="flex-1 w-full max-w-md mx-auto px-5 py-8 flex flex-col">
      {children}
    </main>
  );
}

// ---- Brand / logo --------------------------------------------------
export function Brand({ small = false }: { small?: boolean }) {
  return (
    <Link href="/" className="inline-flex items-center gap-2 no-underline">
      <span className={small ? "text-xl" : "text-2xl"}>🎭</span>
      <span
        className="font-display font-semibold text-ink tracking-tight"
        style={{ fontSize: small ? "1.05rem" : "1.35rem" }}
      >
        Who Gets You?
      </span>
    </Link>
  );
}

// ---- Card ----------------------------------------------------------
export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-surface border border-border rounded-2xl p-5 shadow-[0_1px_2px_rgba(33,26,34,0.04),0_10px_30px_rgba(33,26,34,0.05)] ${className}`}
    >
      {children}
    </div>
  );
}

// ---- Button --------------------------------------------------------
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "md" | "lg";
  full?: boolean;
};

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-colors disabled:opacity-45 disabled:cursor-not-allowed cursor-pointer select-none";

const BUTTON_VARIANTS: Record<string, string> = {
  primary: "bg-accent text-white hover:brightness-110 active:brightness-95",
  secondary:
    "bg-surface-2 text-ink border border-border-strong hover:border-accent",
  ghost: "bg-transparent text-ink-soft hover:text-ink",
  danger:
    "bg-transparent text-[color:var(--accent-ink)] border border-border hover:border-accent",
};

export function Button({
  variant = "primary",
  size = "md",
  full = false,
  className = "",
  ...props
}: ButtonProps) {
  const sizes = size === "lg" ? "text-base px-5 py-3.5" : "text-sm px-4 py-2.5";
  return (
    <button
      className={`${BUTTON_BASE} ${BUTTON_VARIANTS[variant]} ${sizes} ${full ? "w-full" : ""} ${className}`}
      {...props}
    />
  );
}

// ---- Field ---------------------------------------------------------
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-semibold text-ink">{label}</span>
      {children}
      {hint ? <span className="text-xs text-ink-faint">{hint}</span> : null}
    </label>
  );
}

const INPUT_CLASS =
  "w-full bg-surface border border-border-strong rounded-xl px-3.5 py-3 text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent transition-colors";

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${INPUT_CLASS} ${props.className ?? ""}`} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={`${INPUT_CLASS} appearance-none ${props.className ?? ""}`} />
  );
}

// ---- Inline error / notice ----------------------------------------
export function Notice({
  tone = "error",
  children,
}: {
  tone?: "error" | "info";
  children: ReactNode;
}) {
  const styles =
    tone === "error"
      ? "text-[color:var(--accent-ink)] bg-accent-soft border-[color:var(--accent)]"
      : "text-[color:var(--cool)] bg-cool-soft border-[color:var(--cool)]";
  return (
    <div className={`text-sm rounded-xl border px-3.5 py-2.5 ${styles}`}>{children}</div>
  );
}

// ---- Live badge ----------------------------------------------------
export function LiveBadge({ live }: { live: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-mono text-ink-faint">
      <span
        className="w-2 h-2 rounded-full transition-colors"
        style={{
          background: live ? "var(--cool)" : "var(--ink-faint)",
          boxShadow: live ? "0 0 0 3px var(--cool-soft)" : "none",
        }}
      />
      {live ? "trực tiếp" : "đang kết nối…"}
    </span>
  );
}
