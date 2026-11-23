import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api } from "@/api/client";
import { brand, Logo } from "@/app/theme/brand";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";

const MIN_LENGTH = 12; // backend: app/security/passwords.py MIN_PASSWORD_LENGTH

/**
 * The token sits in the URL fragment (/invite#TOKEN): browsers never send the
 * fragment to a server or in a Referer header. It is read once and then
 * removed from the address bar and history.
 */
function takeTokenFromHash(): string {
  const token = window.location.hash.replace(/^#/, "");
  if (token) {
    window.history.replaceState(window.history.state, "", window.location.pathname);
  }
  return token;
}

export function AcceptInvite() {
  const [token] = useState(takeTokenFromHash);
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password.length < MIN_LENGTH) return setError(t("invite.tooShort"));
    if (password !== again) return setError(t("invite.mismatch"));
    setBusy(true);
    setError(null);
    try {
      const { response, error: body } = await api.POST("/api/v1/auth/invite/accept", {
        body: { token, password },
      });
      if (response.ok) {
        setDone(true);
        setPassword("");
        setAgain("");
      } else if (response.status === 422) {
        // The password policy's own sentence (never content).
        const detail = (body as { detail?: unknown } | undefined)?.detail;
        setError(typeof detail === "string" ? detail : t("error.checkFields"));
      } else if (response.status === 429) {
        setError(t("signin.errorLocked"));
      } else {
        setError(t("invite.invalid"));
      }
    } catch {
      setError(t("signin.errorNetwork"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-full items-center justify-center bg-muted p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center justify-center gap-2 text-lg font-semibold">
          <Logo className="size-6" />
          {brand.name}
        </div>
        <Card>
          <CardHeader>
            <CardTitle>{t("invite.title")}</CardTitle>
            {!done && token && <CardDescription>{t("invite.subtitle")}</CardDescription>}
          </CardHeader>
          <CardContent className="space-y-4">
            {!token ? (
              <Alert>{t("invite.missing")}</Alert>
            ) : done ? (
              <>
                <p className="text-sm" role="status">
                  {t("invite.done")}
                </p>
                <Button asChild className="w-full">
                  <Link to="/sign-in">{t("invite.toSignIn")}</Link>
                </Button>
              </>
            ) : (
              <form className="space-y-4" onSubmit={submit} noValidate>
                <div className="space-y-2">
                  <Label htmlFor="new-password">{t("invite.password")}</Label>
                  <Input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    autoFocus
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-password-again">{t("invite.confirm")}</Label>
                  <Input
                    id="new-password-again"
                    type="password"
                    autoComplete="new-password"
                    value={again}
                    onChange={(e) => setAgain(e.target.value)}
                  />
                </div>
                {error && <Alert>{error}</Alert>}
                <Button type="submit" className="w-full" disabled={busy || !password || !again}>
                  {t("invite.submit")}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
