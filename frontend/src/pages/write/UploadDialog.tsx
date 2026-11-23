import { useState, type FormEvent } from "react";
import { messageOf } from "@/api/errors";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";

const ACCEPT = ".pptx,.pdf,.docx,.png,.jpg,.jpeg,.webp,.gif";
const MAX = 50 * 1024 * 1024;

export function UploadDialog({
  onUpload,
  onClose,
}: {
  onUpload: (file: File, tool: string, link: string) => Promise<void>;
  onClose: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [tool, setTool] = useState("");
  const [link, setLink] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    if (file.size > MAX) return setError(t("upload.tooBig"));
    if (link && !link.startsWith("https://")) return setError(t("upload.linkHttps"));
    setBusy(true);
    setError(null);
    try {
      await onUpload(file, tool, link);
      onClose();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent>
        <DialogTitle>{t("upload.title")}</DialogTitle>
        <DialogDescription>{t("upload.help")}</DialogDescription>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="upload-file">{t("upload.file")}</Label>
            <Input
              id="upload-file"
              type="file"
              accept={ACCEPT}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="upload-tool">{t("upload.tool")}</Label>
            <Input
              id="upload-tool"
              maxLength={40}
              placeholder="Google Slides, Canva…"
              value={tool}
              onChange={(e) => setTool(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="upload-link">{t("upload.link")}</Label>
            <Input
              id="upload-link"
              type="url"
              maxLength={1000}
              placeholder="https://"
              value={link}
              onChange={(e) => setLink(e.target.value)}
            />
          </div>
          {error && <Alert>{error}</Alert>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!file || busy}>
              {busy ? t("upload.uploading") : t("upload.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
