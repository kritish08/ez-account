import { cn } from "@/lib/utils"

function Skeleton({
  className,
  ...props
}) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-brand-100/60", className)}
      {...props} />
  );
}

export { Skeleton }
