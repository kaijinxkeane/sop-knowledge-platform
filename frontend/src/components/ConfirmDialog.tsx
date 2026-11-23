import { useState, type ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { Button, type ButtonProps } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { messageOf } from "@/api/errors";
import { t } from "@/i18n";

type Props = {
  label: ReactNode;
  title: string;
  body: string;
  confirmLabel?: string;
  onConfirm: () => Promise<unknown>;
  variant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
  "aria-label"?: string;
};

/** A button that asks before doing something hard to undo, and shows the server's refusal. */
export function ConfirmDialog({ label, title, body, confirmLabel, onConfirm, ...button }: Props) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      setOpen(false);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setError(null);
      }}
    >
      <DialogTrigger asChild>
        <Button
          variant={button.variant ?? "outline"}
          size={button.size ?? "sm"}
          aria-label={button["aria-label"]}
        >
          {label}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{body}</DialogDescription>
        {error && <Alert>{error}</Alert>}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => void confirm()} disabled={busy}>
            {confirmLabel ?? title}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
