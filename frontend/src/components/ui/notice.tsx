import { CircleAlert } from "lucide-react";
import type { ReactNode } from "react";

export function Notice({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  return <div className={`notice ${compact ? "compact" : ""}`}><CircleAlert size={17}/><div>{children}</div></div>;
}
