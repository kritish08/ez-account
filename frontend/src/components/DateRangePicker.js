import React from "react";
import {
    endOfMonth,
    endOfWeek,
    format,
    startOfMonth,
    startOfWeek,
    subDays,
} from "date-fns";
import { Calendar as CalendarIcon, X } from "lucide-react";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";
import { Calendar } from "./ui/calendar";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "./ui/popover";

// Two months of react-day-picker is roughly 540px wide, which overflowed
// every phone. Track the viewport and drop to a single month below `sm`.
function useIsNarrow(query = "(max-width: 639px)") {
    const [narrow, setNarrow] = React.useState(
        () => typeof window !== "undefined" && window.matchMedia(query).matches
    );

    React.useEffect(() => {
        const mql = window.matchMedia(query);
        const onChange = (e) => setNarrow(e.matches);
        mql.addEventListener("change", onChange);
        setNarrow(mql.matches);
        return () => mql.removeEventListener("change", onChange);
    }, [query]);

    return narrow;
}

// Picking "this month" by tapping through a calendar grid is a lot of
// precision work on a phone, and it is what people actually want most of
// the time. These cover the common cases in one tap.
const PRESETS = [
    { label: "Today", range: () => ({ from: new Date(), to: new Date() }) },
    {
        label: "This week",
        range: () => ({
            from: startOfWeek(new Date(), { weekStartsOn: 1 }),
            to: endOfWeek(new Date(), { weekStartsOn: 1 }),
        }),
    },
    {
        label: "Last 30 days",
        range: () => ({ from: subDays(new Date(), 29), to: new Date() }),
    },
    {
        label: "This month",
        range: () => ({ from: startOfMonth(new Date()), to: endOfMonth(new Date()) }),
    },
];

export function DateRangePicker({ className, date, setDate }) {
    const isNarrow = useIsNarrow();
    const [open, setOpen] = React.useState(false);

    const applyPreset = (preset) => {
        setDate(preset.range());
        setOpen(false);
    };

    return (
        <div className={cn("grid gap-2", className)}>
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <Button
                        id="date"
                        variant={"outline"}
                        className={cn(
                            // Was a hard w-[260px], which forced the filter bar
                            // wider than a phone screen.
                            "w-full sm:w-[260px] justify-start text-left font-normal",
                            !date && "text-muted-foreground"
                        )}
                    >
                        <CalendarIcon className="mr-2 h-4 w-4 shrink-0" />
                        <span className="truncate">
                            {date?.from ? (
                                date.to ? (
                                    <>
                                        {format(date.from, "LLL dd, y")} -{" "}
                                        {format(date.to, "LLL dd, y")}
                                    </>
                                ) : (
                                    format(date.from, "LLL dd, y")
                                )
                            ) : (
                                "Pick a date range"
                            )}
                        </span>
                    </Button>
                </PopoverTrigger>
                <PopoverContent
                    // Never wider than the screen, whatever the calendar wants.
                    className="w-[calc(100vw-2rem)] sm:w-auto max-w-[calc(100vw-2rem)] p-0 overflow-x-auto"
                    align="start"
                >
                    <div className="flex flex-wrap gap-1.5 border-b p-2">
                        {PRESETS.map((preset) => (
                            <Button
                                key={preset.label}
                                variant="ghost"
                                size="sm"
                                className="h-8 px-2.5 text-xs"
                                onClick={() => applyPreset(preset)}
                            >
                                {preset.label}
                            </Button>
                        ))}
                        {date?.from && (
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-8 px-2.5 text-xs text-muted-foreground ml-auto"
                                onClick={() => {
                                    setDate(undefined);
                                    setOpen(false);
                                }}
                            >
                                <X className="mr-1 h-3 w-3" />
                                Clear
                            </Button>
                        )}
                    </div>
                    <Calendar
                        initialFocus
                        mode="range"
                        defaultMonth={date?.from}
                        selected={date}
                        onSelect={setDate}
                        numberOfMonths={isNarrow ? 1 : 2}
                    />
                </PopoverContent>
            </Popover>
        </div>
    );
}
