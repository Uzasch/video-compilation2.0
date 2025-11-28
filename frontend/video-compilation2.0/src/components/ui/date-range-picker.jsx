import * as React from "react"
import { CalendarIcon, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

function formatDate(date) {
  if (!date) return ""
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  })
}

function DateRangePicker({
  date,
  onDateChange,
  className,
  placeholder = "Select date range",
  align = "start",
}) {
  const [open, setOpen] = React.useState(false)

  const handleSelect = (range) => {
    onDateChange?.(range)
    if (range?.from && range?.to) {
      setOpen(false)
    }
  }

  const handleClear = (e) => {
    e.stopPropagation()
    onDateChange?.(undefined)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "justify-start text-left font-normal bg-background/50",
            !date && "text-muted-foreground",
            className
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4" />
          {date?.from ? (
            date.to ? (
              <>
                {formatDate(date.from)} - {formatDate(date.to)}
              </>
            ) : (
              formatDate(date.from)
            )
          ) : (
            <span>{placeholder}</span>
          )}
          {date?.from && (
            <X
              className="ml-auto h-4 w-4 opacity-50 hover:opacity-100"
              onClick={handleClear}
            />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align={align} side="bottom" sideOffset={4} avoidCollisions={false}>
        <Calendar
          mode="range"
          defaultMonth={date?.from}
          selected={date}
          onSelect={handleSelect}
          numberOfMonths={1}
          className="rounded-lg border-0 shadow-sm"
        />
      </PopoverContent>
    </Popover>
  )
}

export { DateRangePicker }
