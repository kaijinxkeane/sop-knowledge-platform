import * as React from "react";
import { cn } from "@/lib/utils";

type Props = Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: React.ReactNode;
  hint?: React.ReactNode;
};

/** A native checkbox with its label, so a click on the text toggles it. */
export function Checkbox({ label, hint, className, id, ...props }: Props) {
  const autoId = React.useId();
  const inputId = id ?? autoId;
  return (
    <div className={cn("flex items-start gap-2", className)}>
      <input
        id={inputId}
        type="checkbox"
        className="mt-0.5 size-4 accent-[var(--primary)] disabled:opacity-50"
        {...props}
      />
      <label htmlFor={inputId} className={cn("text-sm", props.disabled && "opacity-50")}>
        {label}
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </label>
    </div>
  );
}
