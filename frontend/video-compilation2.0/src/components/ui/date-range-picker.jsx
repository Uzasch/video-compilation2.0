import * as React from "react"
import { format } from "date-fns"
import { CalendarIcon, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

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
    // Close popover when both dates are selected
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
                {format(date.from, "MMM d, yyyy")} -{" "}
                {format(date.to, "MMM d, yyyy")}
              </>
            ) : (
              format(date.from, "MMM d, yyyy")
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
      <PopoverContent className="w-auto p-0" align={align}>
        <Calendar
          mode="range"
          defaultMonth={date?.from}
          selected={date}
          onSelect={handleSelect}
          numberOfMonths={2}
        />
        <div className="flex items-center justify-between gap-2 border-t border-border p-3">
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const today = new Date()
                const weekAgo = new Date()
                weekAgo.setDate(today.getDate() - 7)
                handleSelect({ from: weekAgo, to: today })
              }}
            >
              Last 7 days
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const today = new Date()
                const monthAgo = new Date()
                monthAgo.setDate(today.getDate() - 30)
                handleSelect({ from: monthAgo, to: today })
              }}
            >
              Last 30 days
            </Button>
          </div>
          {date?.from && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClear}
            >
              Clear
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

export { DateRangePicker }
