import * as React from "react";
import { cn } from "@/lib/utils";

/** A styled native select: accessible and keyboard-friendly without extra code. */
export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
