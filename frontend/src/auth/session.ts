/**
 * The signed-in session.
 *
 * The access token lives in memory only: never localStorage or sessionStorage,
 * so a script on the page can't lift it from storage and it is gone when the
 * tab closes. The refresh token is an httpOnly cookie scoped to /api/v1/auth
 * that this code can't read; a reload restores the session by calling
 * /auth/refresh (plan §11).
 */

export type SessionStatus = "unknown" | "signed-in" | "signed-out";

type State = { status: SessionStatus; accessToken: string | null };

let state: State = { status: "unknown", accessToken: null };
const listeners = new Set<() => void>();

function set(next: State) {
  state = next;
  listeners.forEach((l) => l());
}

export const session = {
  get: () => state,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  signIn(accessToken: string) {
    set({ status: "signed-in", accessToken });
  },
  signOut() {
    set({ status: "signed-out", accessToken: null });
  },
  /** Tests only. */
  reset() {
    set({ status: "unknown", accessToken: null });
  },
};

let inFlight: Promise<boolean> | null = null;

/**
 * Swap the refresh cookie for a new access token. Concurrent callers share
 * one request: the backend rotates the cookie and treats a reused one as
 * theft, so two parallel refreshes would end the session.
 */
export function refreshSession(): Promise<boolean> {
  inFlight ??= (async () => {
    try {
      const res = await globalThis.fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!res.ok) {
        session.signOut();
        return false;
      }
      const body = (await res.json()) as { access_token: string };
      session.signIn(body.access_token);
      return true;
    } catch {
      session.signOut();
      return false;
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}
