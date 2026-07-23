"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Verify" },
  { href: "/history", label: "History" },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/history") {
    return pathname.startsWith("/history") || pathname.startsWith("/runs");
  }
  return pathname.startsWith(href);
}

export default function Nav() {
  const pathname = usePathname();

  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mx-auto flex w-full max-w-4xl items-center gap-8 px-4 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight">
          <span className="text-emerald-600 dark:text-emerald-500">Sent</span>
          inel
        </Link>
        <nav className="flex gap-5 text-sm">
          {LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={
                isActive(pathname, href)
                  ? "font-semibold text-emerald-700 dark:text-emerald-400"
                  : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
              }
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
