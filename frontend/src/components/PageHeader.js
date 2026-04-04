import React from "react";
import { cn } from "../lib/utils";

export const PageHeader = ({ title, description, action, className }) => {
    return (
        <div className={cn("flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6", className)}>
            <div>
                <h1 className="text-2xl font-bold font-heading text-slate-900">{title}</h1>
                {description && <p className="text-slate-500 mt-1">{description}</p>}
            </div>
            {action && <div>{action}</div>}
        </div>
    );
};
