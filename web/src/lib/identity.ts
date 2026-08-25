"use client";

// Lightweight identity: which player this browser is, per room code.
// No accounts — just a uuid kept in localStorage.

const KEY = "wgy.identity.v1";

type IdentityMap = Record<string, { playerId: string; name: string }>;

function read(): IdentityMap {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(KEY) ?? "{}") as IdentityMap;
  } catch {
    return {};
  }
}

function write(map: IdentityMap) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(map));
}

export function rememberIdentity(code: string, playerId: string, name: string) {
  const map = read();
  map[code.toUpperCase()] = { playerId, name };
  write(map);
}

export function getIdentity(code: string): { playerId: string; name: string } | null {
  return read()[code.toUpperCase()] ?? null;
}

export function forgetIdentity(code: string) {
  const map = read();
  delete map[code.toUpperCase()];
  write(map);
}
