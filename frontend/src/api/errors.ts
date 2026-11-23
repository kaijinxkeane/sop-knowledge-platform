import { t } from "@/i18n";

/**
 * A failed call whose `detail` is a fixed message from the server, such as
 * "another administrator must add roles to your account". Only used for
 * endpoints whose errors never quote content (admin, sign-in setup).
 */
export class ServerError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string | null,
  ) {
    super(detail ?? `request failed with status ${status}`);
  }

  /** Text to show: the server's sentence if it sent one, else a generic line. */
  get userMessage(): string {
    if (this.detail) return this.detail.charAt(0).toUpperCase() + this.detail.slice(1) + ".";
    if (this.status === 422) return t("error.checkFields");
    return t("error.generic");
  }
}

export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request;
  if (response.ok) return data as T;
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  // Validation errors (422) come as a list; only a plain short sentence is shown.
  throw new ServerError(
    response.status,
    typeof detail === "string" && detail.length <= 200 ? detail : null,
  );
}

export function messageOf(err: unknown): string {
  return err instanceof ServerError ? err.userMessage : t("error.generic");
}
