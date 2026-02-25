import { cn } from "../../lib/cn";

export function Card({ className, children }) {
  return <section className={cn("glass p-4 basketball-texture", className)}>{children}</section>;
}

export function CardHeader({ className, title, subtitle, right }) {
  return (
    <div className={cn("mb-3 flex items-start justify-between gap-3", className)}>
      <div>
        <h3 className="section-title">{title}</h3>
        {subtitle ? <p className="section-subtitle mt-1">{subtitle}</p> : null}
      </div>
      {right}
    </div>
  );
}
