import React from "react";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { Search, Filter, X } from "lucide-react";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "./ui/select";
import { DateRangePicker } from "./DateRangePicker";

export const UIFilters = ({
    search,
    setSearch,
    searchPlaceholder = "Search...",
    statusFilter,
    setStatusFilter,
    statusOptions = [], // [{value: 'draft', label: 'Draft'}]
    dateRange,
    setDateRange,
    statusLabel = "All Statuses",
    children,
    onClear,
}) => {
    return (
        <div className="flex flex-col xl:flex-row items-start xl:items-center gap-3 mb-6">
            {/* Search — only render the input when a setter was provided.
                Some callers (e.g. CustomerDetail) don't have a search box but
                still want the rest of the filter row; the previous version
                would crash with "setSearch is not a function" on keystroke. */}
            {typeof setSearch === "function" && (
                <div className="relative flex-1 w-full xl:max-w-sm">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <Input
                        placeholder={searchPlaceholder}
                        value={search ?? ""}
                        onChange={(e) => setSearch(e.target.value)}
                        className="pl-9"
                    />
                </div>
            )}

            <div className="flex flex-wrap items-center gap-2 w-full xl:w-auto">
                {/* Status Filter */}
                {statusFilter !== undefined && (
                    <Select value={statusFilter} onValueChange={setStatusFilter}>
                        <SelectTrigger className="w-[160px]">
                            <Filter className="h-4 w-4 mr-2 text-slate-400" />
                            <SelectValue placeholder="Filter by status" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">{statusLabel}</SelectItem>
                            {statusOptions.map((opt) => (
                                <SelectItem key={opt.value} value={opt.value}>
                                    {opt.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                )}

                {/* Additional Filters */}
                {children}

                {/* Date Range */}
                {setDateRange && (
                    <DateRangePicker date={dateRange} setDate={setDateRange} />
                )}

                {/* Clear Button */}
                <Button variant="ghost" size="icon" onClick={onClear} title="Clear Filters">
                    <X className="h-4 w-4 text-slate-500" />
                </Button>
            </div>
        </div>
    );
};
