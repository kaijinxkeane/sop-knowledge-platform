import { BookOpenCheck } from "lucide-react";

// Product name and logo. Swap these for company branding (frontend spec §10).
export const brand = {
  name: "SOP Assistant",
};

export function Logo({ className }: { className?: string }) {
  return <BookOpenCheck aria-hidden="true" className={className} />;
}
