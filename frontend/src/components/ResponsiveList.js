import React from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "../lib/utils";

/**
 * Table on a wide screen, tappable cards on a phone.
 *
 * Nineteen pages render a 6-8 column desktop table, and the only mobile
 * strategy anywhere in the app was `overflow-auto` on the table wrapper — so
 * every list screen became a horizontal scroll on a phone, with the columns
 * that matter pushed off the right edge.
 *
 * This deliberately does NOT take a `columns` config. Rewriting each page's
 * table into a schema would touch every cell and risk regressions across the
 * whole app; here the existing <Table> is passed straight through as
 * `children` and only the mobile branch is new. The two views can also then
 * differ honestly — a card shows the three things that matter, not eight
 * columns squeezed into 375px.
 */
export const ResponsiveList = ({ items, renderCard, children, className }) => (
  <>
    <div className={cn("hidden md:block", className)}>{children}</div>
    <div className="md:hidden divide-y divide-slate-100">
      {items.map((item, index) => (
        <React.Fragment key={item.id ?? index}>{renderCard(item)}</React.Fragment>
      ))}
    </div>
  </>
);

/**
 * One row of a mobile list.
 *
 * Layout is fixed on purpose so every list in the app reads the same way:
 *
 *   primary ................. amount
 *   secondary ............... status
 *
 * `amount` is right-aligned and tabular so figures line up down the column,
 * which is most of what an accounting list is for.
 */
export const ListCard = ({
  primary,
  secondary,
  amount,
  amountClassName,
  status,
  meta,
  onClick,
  actions,
}) => {
  const interactive = typeof onClick === "function";

  return (
    <div
      className={cn(
        "flex items-start gap-3 px-1 py-3.5",
        interactive && "active:bg-slate-50 cursor-pointer"
      )}
      onClick={
        interactive
          ? (e) => {
              // The actions menu lives inside the card; don't navigate when
              // someone is reaching for it.
              if (e.target.closest("button, [role='menuitem'], [role='menu']")) return;
              onClick();
            }
          : undefined
      }
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <span className="truncate font-medium text-slate-900">{primary}</span>
          {amount != null && (
            <span
              className={cn(
                "shrink-0 font-mono font-medium tabular-nums",
                amountClassName || "text-slate-900"
              )}
            >
              {amount}
            </span>
          )}
        </div>
        <div className="mt-1 flex items-center justify-between gap-3">
          <span className="truncate text-sm text-slate-500">{secondary}</span>
          {status}
        </div>
        {meta && <div className="mt-1.5 text-xs text-slate-400">{meta}</div>}
      </div>

      {actions ? (
        <div className="shrink-0 pt-0.5">{actions}</div>
      ) : interactive ? (
        <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />
      ) : null}
    </div>
  );
};
