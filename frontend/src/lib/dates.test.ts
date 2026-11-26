import { afterEach, describe, expect, it, vi } from "vitest";
import { startOfDay, TIME_ZONE, todayIso } from "./dates";

describe("company dates (Singapore)", () => {
  afterEach(() => vi.useRealTimers());

  it("uses Singapore's date even where it is already tomorrow there", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-26T17:30:00Z")); // 01:30 on the 27th in Singapore
    expect(todayIso()).toBe("2026-11-27");
    expect(todayIso(1)).toBe("2026-11-28");
  });

  it("starts a day at Singapore midnight", () => {
    expect(startOfDay("2026-11-27")).toBe("2026-11-26T16:00:00.000Z");
  });

  it("shows times in Singapore", () => {
    const shown = new Date("2026-11-26T17:30:00Z").toLocaleTimeString("en-GB", { timeZone: TIME_ZONE, hour: "2-digit", minute: "2-digit" });
    expect(shown).toBe("01:30");
  });
});
