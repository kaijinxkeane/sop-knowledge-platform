import { useState, type FormEvent } from "react";
import { api } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t, type MessageKey } from "@/i18n";

type Props = {
  token: string;
  onSignedIn: (accessToken: string) => void;
  onStartOver: () => void;
};

type Setup = { secret: string; qr: string };

/** Draw the QR code here, in the browser: the secret must never go to an outside service. */
async function qrDataUrl(uri: string): Promise<string> {
  const QRCode = await import("qrcode");
  const svg = await QRCode.toString(uri, { type: "svg", margin: 1, errorCorrectionLevel: "M" });
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/** "ABCD EFGH IJKL ..." is easier to type into an app than one long string. */
const grouped = (secret: string) => secret.replace(/(.{4})(?=.)/g, "$1 ");

export function EnrollTotp({ token, onSignedIn, onStartOver }: Props) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  function fail(status: number) {
    if (status === 409) setError("signin.errorAlreadyEnrolled");
    else if (status === 429) setError("signin.errorLocked");
    else if (status === 401) setError("signin.errorCredentials");
    else setError("signin.errorNetwork");
  }

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const { data, response } = await api.POST("/api/v1/auth/totp/enroll", { body: { token } });
      if (!data) return fail(response.status);
      setSetup({ secret: data.secret, qr: await qrDataUrl(data.otpauth_uri) });
    } catch {
      setError("signin.errorNetwork");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { data, response } = await api.POST("/api/v1/auth/totp/enroll/confirm", {
        body: { token, code: code.replace(/\s/g, "") },
      });
      if (!data) return fail(response.status);
      onSignedIn(data.access_token);
    } catch {
      setError("signin.errorNetwork");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <CardHeader>
        <CardTitle>{t("signin.enrollTitle")}</CardTitle>
        <CardDescription>{setup ? t("signin.enrollScan") : t("signin.enrollBody")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!setup ? (
          <Button type="button" className="w-full" onClick={() => void start()} disabled={busy}>
            {t("signin.enrollStart")}
          </Button>
        ) : (
          <form className="space-y-4" onSubmit={confirm} noValidate>
            <img
              src={setup.qr}
              alt={t("signin.enrollQrAlt")}
              className="mx-auto size-48 rounded border bg-white p-2"
            />
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">{t("signin.enrollManual")}</p>
              <code className="block select-all break-all rounded bg-muted px-2 py-1 text-sm">
                {grouped(setup.secret)}
              </code>
            </div>
            <div className="space-y-2">
              <Label htmlFor="enroll-code">{t("signin.code")}</Label>
              <Input
                id="enroll-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={12}
                autoFocus
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </div>
            {error && <Alert>{t(error)}</Alert>}
            <Button type="submit" className="w-full" disabled={busy || code.trim().length < 6}>
              {t("signin.enrollConfirm")}
            </Button>
          </form>
        )}
        {!setup && error && <Alert>{t(error)}</Alert>}
        <Button type="button" variant="link" className="w-full" onClick={onStartOver}>
          {t("signin.startOver")}
        </Button>
      </CardContent>
    </>
  );
}
