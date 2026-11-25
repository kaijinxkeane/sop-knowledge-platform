import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { session } from "@/auth/session";

afterEach(() => {
  cleanup();
  session.reset();
  localStorage.clear();
  sessionStorage.clear();
});

// jsdom has no scrolling; the app restores scroll positions (ScrollRestoration).
window.scrollTo = () => {};
