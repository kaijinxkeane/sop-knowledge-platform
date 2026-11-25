import { X } from "lucide-react";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import { usePeople, type Colleague } from "@/pages/handovers/api";

type Props = {
  id: string;
  label: string;
  value: Colleague[];
  onChange: (people: Colleague[]) => void;
  hint?: string;
  single?: boolean;
};

/** Pick colleagues by name (names only: the backend sends no emails or roles). */
export function PeoplePicker({ id, label, value, onChange, hint, single }: Props) {
  const [q, setQ] = useState("");
  const people = usePeople(q.trim());
  const chosen = new Set(value.map((p) => p.id));
  const options = (people.data ?? []).filter((p) => !chosen.has(p.id)).slice(0, 8);
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {value.map((p) => (
            <li key={p.id} className="flex items-center gap-1 rounded-full border bg-muted/40 py-0.5 pl-3 pr-1 text-sm">
              {p.name}
              <button
                type="button"
                className="rounded-full p-0.5 hover:bg-accent"
                aria-label={t("handover.remove", { name: p.name })}
                onClick={() => onChange(value.filter((x) => x.id !== p.id))}
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {(!single || value.length === 0) && (
        <>
          <Input
            id={id}
            value={q}
            placeholder={t("handover.searchPeople")}
            autoComplete="off"
            maxLength={100}
            onChange={(e) => setQ(e.target.value)}
          />
          {q.trim() && options.length > 0 && (
            <ul className="rounded-md border" aria-label={t("handover.addReceiver")}>
              {options.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className="w-full px-3 py-1.5 text-left text-sm hover:bg-accent"
                    onClick={() => {
                      onChange(single ? [p] : [...value, p]);
                      setQ("");
                    }}
                  >
                    {p.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
