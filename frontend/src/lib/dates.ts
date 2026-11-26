/**
 * Dates and times are shown in the company's time zone, whoever is looking and
 * wherever they are. Keep it the same as the backend's SOP_TIMEZONE
 * (backend/app/config.py, used by app/clock.py).
 */
export const TIME_ZONE = "Asia/Singapore";
/** Singapore has no daylight saving: its offset never changes. */
const OFFSET = "+08:00";

/** Today's date in the company's time zone, as YYYY-MM-DD. */
export function todayIso(addDays = 0): string {
  const d = new Date(Date.now() + addDays * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

/** The instant a company day (YYYY-MM-DD) starts, as an ISO timestamp. */
export const startOfDay = (day: string) => new Date(`${day}T00:00:00${OFFSET}`).toISOString();
