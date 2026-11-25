import { useSyncExternalStore } from "react";

/**
 * Installable web app: register the service worker (production builds only)
 * and keep the browser's install offer so the app can show its own
 * "Install app" button. The worker caches only the offline page, never content.
 */

type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

let offer: InstallPrompt | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function startPwa(): void {
  if (typeof window === "undefined") return;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // show our own button instead of the browser's mini bar
    offer = e as InstallPrompt;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    offer = null;
    emit();
  });
  if (import.meta.env.PROD && "serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => undefined);
    });
  }
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** The pending install offer, or null (already installed, or the browser doesn't offer one). */
export function useInstallOffer() {
  const current = useSyncExternalStore(subscribe, () => offer);
  return current
    ? async () => {
        await current.prompt();
        await current.userChoice;
        offer = null;
        emit();
      }
    : null;
}

/** Tests only: pretend the browser offered an install. */
export function _offerForTest(e: InstallPrompt | null) {
  offer = e;
  emit();
}
