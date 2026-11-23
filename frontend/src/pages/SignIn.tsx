import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { api } from "@/api/client";
import { brand, Logo } from "@/app/theme/brand";
import { useSession } from "@/auth/hooks";
import { session } from "@/auth/session";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t, type MessageKey } from "@/i18n";
import { EnrollTotp } from "./EnrollTotp";

type Step =
  | { kind: "password" }
  | { kind: "totp"; token: string }
  | { kind: "enroll"; token: string };

function errorFor(status: number | "network"): MessageKey {
  if (status === "network") return "signin.errorNetwork";
  if (status === 429) return "signin.errorLocked";
  // A wrong code and an expired 10-minute step token both come back as 401.
  if (status === 401 || status === 422) return "signin.errorCredentials";
  return "signin.errorNetwork";
}

/** Only same-app paths; never an absolute or protocol-relative URL. */
function safeNext(from: unknown): string {
  return typeof from === "string" && from.startsWith("/") && !from.startsWith("//") ? from : "/";
}

export function SignIn() {
  const { status } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const next = safeNext((location.state as { from?: string } | null)?.from);

  const [step, setStep] = useState<Step>({ kind: "password" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "signed-in") return <Navigate to={next} replace />;

  async function run(call: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await call();
    } catch (e) {
      setError(errorFor(e instanceof Response ? e.status : "network"));
    } finally {
      setBusy(false);
    }
  }

  function submitPassword(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      const { data, response } = await api.POST("/api/v1/auth/login", {
        body: { email: email.trim(), password },
      });
      if (!data) throw response;
      setPassword("");
      setStep(
        data.status === "totp_required"
          ? { kind: "totp", token: data.token }
          : { kind: "enroll", token: data.token },
      );
    });
  }

  function submitCode(e: FormEvent) {
    e.preventDefault();
    if (step.kind !== "totp") return;
    void run(async () => {
      const { data, response } = await api.POST("/api/v1/auth/totp/verify", {
        body: { token: step.token, code: code.replace(/\s/g, "") },
      });
      if (!data) throw response;
      session.signIn(data.access_token);
      navigate(next, { replace: true });
    });
  }

  function startOver() {
    setStep({ kind: "password" });
    setCode("");
    setPassword("");
    setError(null);
  }

  return (
    <main className="flex min-h-full items-center justify-center bg-muted p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center justify-center gap-2 text-lg font-semibold">
          <Logo className="size-6" />
          {brand.name}
        </div>
        <Card>
          {step.kind === "password" && (
            <>
              <CardHeader>
                <CardTitle>{t("signin.title")}</CardTitle>
                <CardDescription>{t("signin.subtitle")}</CardDescription>
              </CardHeader>
              <CardContent>
                <form className="space-y-4" onSubmit={submitPassword} noValidate>
                  <div className="space-y-2">
                    <Label htmlFor="email">{t("signin.email")}</Label>
                    <Input
                      id="email"
                      type="email"
                      autoComplete="username"
                      required
                      autoFocus
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">{t("signin.password")}</Label>
                    <Input
                      id="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </div>
                  {error && <Alert>{t(error)}</Alert>}
                  <Button type="submit" className="w-full" disabled={busy || !email || !password}>
                    {t("signin.submit")}
                  </Button>
                </form>
              </CardContent>
            </>
          )}

          {step.kind === "totp" && (
            <>
              <CardHeader>
                <CardTitle>{t("signin.totpTitle")}</CardTitle>
                <CardDescription>{t("signin.totpSubtitle")}</CardDescription>
              </CardHeader>
              <CardContent>
                <form className="space-y-4" onSubmit={submitCode} noValidate>
                  <div className="space-y-2">
                    <Label htmlFor="code">{t("signin.code")}</Label>
                    <Input
                      id="code"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={12}
                      required
                      autoFocus
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                    />
                  </div>
                  {error && <Alert>{t(error)}</Alert>}
                  <Button type="submit" className="w-full" disabled={busy || code.trim().length < 6}>
                    {t("signin.verify")}
                  </Button>
                  <Button type="button" variant="link" className="w-full" onClick={startOver}>
                    {t("signin.startOver")}
                  </Button>
                </form>
              </CardContent>
            </>
          )}

          {step.kind === "enroll" && (
            <EnrollTotp
              token={step.token}
              onSignedIn={(accessToken) => {
                session.signIn(accessToken);
                navigate(next, { replace: true });
              }}
              onStartOver={startOver}
            />
          )}
        </Card>
      </div>
    </main>
  );
}
