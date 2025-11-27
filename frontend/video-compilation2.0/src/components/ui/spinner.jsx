import { Loader2Icon } from "lucide-react"

import { cn } from "@/lib/utils"

const sizeClasses = {
  sm: "size-4",
  md: "size-6",
  lg: "size-8",
  xl: "size-12"
}

function Spinner({
  className,
  size = "sm",
  ...props
}) {
  return (
    <Loader2Icon
      role="status"
      aria-label="Loading"
      className={cn(sizeClasses[size] || "size-4", "animate-spin", className)}
      {...props} />
  );
}

export { Spinner }
