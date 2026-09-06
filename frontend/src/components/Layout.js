import React, { useState } from "react";
import { Outlet, NavLink, useLocation, useNavigate } from "react-router-dom";
import { getBusiness } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useModules } from "../context/ModulesContext";
import { Button } from "./ui/button";
import {
  LayoutDashboard,
  Users,
  FileText,
  CreditCard,
  Receipt,
  BarChart3,
  Settings,
  LogOut,
  Menu,
  X,
  Package,
  Layers,
  Truck,
  ShoppingCart,
  RotateCcw,
  Undo2,
  Factory,
} from "lucide-react";

// Grouped, and labelled in the words a shop owner already uses.
//
// The sidebar was a flat list of fifteen items with no sections, and several
// were named after the accounting artefact rather than the thing that
// happens: "Credit Notes" and "Debit Notes" are the two features people
// avoid out of not knowing what they are. Someone taking goods back from a
// customer is not looking for a credit note. The accounting term is kept as
// a sub-label so the vocabulary is still learnable and anyone who does know
// it can find it.
const navGroups = [
  {
    items: [{ to: "/", icon: LayoutDashboard, label: "Dashboard" }],
  },
  {
    title: "Sell",
    items: [
      { to: "/invoices", icon: FileText, label: "Invoices" },
      { to: "/customers", icon: Users, label: "Customers" },
      { to: "/payments", icon: CreditCard, label: "Payments received" },
      {
        to: "/credit-notes",
        icon: RotateCcw,
        label: "Returns from customers",
        sublabel: "Credit notes",
      },
    ],
  },
  {
    title: "Buy",
    items: [
      { to: "/purchases", icon: ShoppingCart, label: "Purchases" },
      { to: "/suppliers", icon: Truck, label: "Suppliers" },
      { to: "/expenses", icon: Receipt, label: "Expenses" },
      {
        to: "/debit-notes",
        icon: Undo2,
        label: "Returns to suppliers",
        sublabel: "Debit notes",
      },
    ],
  },
  {
    title: "Stock",
    items: [
      { to: "/finished-goods", icon: Package, label: "Finished Goods" },
      {
        to: "/raw-materials",
        icon: Layers,
        label: "Raw Materials",
        requireModule: "enable_production",
      },
      {
        to: "/production",
        icon: Factory,
        label: "Production",
        requireModule: "enable_production",
      },
    ],
  },
  {
    title: "Books",
    items: [{ to: "/reports", icon: BarChart3, label: "Reports" }],
  },
];


// The mobile top bar was 64px of white containing a hamburger and a spacer —
// on desktop, a blank stripe. Give it the one thing it should always have
// said: where you are.
const PAGE_TITLES = [
  ["/invoices/new", "New invoice"],
  ["/invoices", "Invoices"],
  ["/customers", "Customers"],
  ["/suppliers", "Suppliers"],
  ["/purchases", "Purchases"],
  ["/payments", "Payments received"],
  ["/expenses", "Expenses"],
  ["/credit-notes", "Returns from customers"],
  ["/debit-notes", "Returns to suppliers"],
  ["/finished-goods", "Finished Goods"],
  ["/raw-materials", "Raw Materials"],
  ["/production", "Production"],
  ["/products", "Product"],
  ["/reports", "Reports"],
  ["/settings", "Settings"],
  ["/setup", "Business Setup"],
];

const titleForPath = (pathname) => {
  if (pathname === "/") return "Dashboard";
  const hit = PAGE_TITLES.find(([prefix]) => pathname.startsWith(prefix));
  return hit ? hit[1] : "";
};

const Layout = () => {
  const { user, logout } = useAuth();
  const { modules } = useModules();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // First-run gate.
  //
  // A brand-new user landed on the Dashboard: nine cards reading Rs.0.00 and
  // no indication that anything needed setting up. Business Setup was the
  // fifteenth item in the sidebar and was never forced, so the business name
  // stayed blank on every invoice and — worse — the opening cash and bank
  // balances were never entered, which leaves the Cash Balance card wrong
  // permanently rather than visibly empty.
  //
  // GET /business already distinguishes "not configured yet" from a failure,
  // so redirect once, on that signal only. A failed request is left alone:
  // being offline should not bounce someone into setup.
  React.useEffect(() => {
    if (location.pathname === "/setup") return;
    let cancelled = false;
    getBusiness()
      .then((res) => {
        if (!cancelled && res.data?.configured === false) {
          navigate("/setup", { replace: true, state: { firstRun: true } });
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [location.pathname, navigate]);

  const isVisible = (item) => {
    if (item.to === "/credit-notes" && modules?.enable_credit_notes === false) return false;
    if (item.to === "/debit-notes" && modules?.enable_debit_notes === false) return false;
    if (item.requireModule && !modules?.[item.requireModule]) return false;
    return true;
  };

  // Drop any group left empty once module flags are applied, so a disabled
  // Production module doesn't leave a "Stock" heading over nothing.
  const visibleGroups = navGroups
    .map((group) => ({ ...group, items: group.items.filter(isVisible) }))
    .filter((group) => group.items.length > 0);

  // The mobile drawer is a hand-rolled fixed panel rather than a Radix
  // primitive, so it gets none of the usual scroll locking for free: opening
  // it left the page behind scrolling under your finger.
  React.useEffect(() => {
    if (!sidebarOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [sidebarOpen]);

  const handleLogout = async () => {
    // Await so the server-side revocation lands before we navigate away —
    // otherwise an unmount can cancel the request and leave the token live.
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen-dvh bg-slate-50">
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-slate-900/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 z-50 h-full w-64 bg-white border-r border-slate-200 transform transition-transform duration-200 ease-in-out lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center justify-between h-16 px-6 border-b border-slate-200">
            <h1 className="text-xl font-bold text-brand-600 font-heading">EZ Accounts by Kyrex</h1>
            <button
              className="lg:hidden p-1 text-slate-500 hover:text-slate-700"
              onClick={() => setSidebarOpen(false)}
              aria-label="Close menu"
            >
              <X size={20} />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-3 py-4 space-y-4 overflow-y-auto">
            {visibleGroups.map((group, groupIndex) => (
              <div key={group.title || `group-${groupIndex}`} className="space-y-1">
                {group.title && (
                  <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    {group.title}
                  </p>
                )}
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    onClick={() => setSidebarOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${isActive
                        ? "bg-brand-50 text-brand-700"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                      }`
                    }
                  >
                    <item.icon size={20} className="shrink-0" />
                    <span className="min-w-0">
                      <span className="block truncate">{item.label}</span>
                      {item.sublabel && (
                        <span className="block text-[11px] font-normal text-slate-400">
                          {item.sublabel}
                        </span>
                      )}
                    </span>
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>

          {/* Settings & User */}
          <div className="border-t border-slate-200 p-4">
            <NavLink
              to="/settings"
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all mb-1 ${isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`
              }
            >
              <Settings size={20} />
              Settings
            </NavLink>

            <NavLink
              to="/setup"
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all mb-3 ${isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`
              }
            >
              <LayoutDashboard size={20} />
              Business Setup
            </NavLink>

            <div className="flex items-center gap-3 px-3 py-2 mb-2">
              <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-semibold text-sm">
                {user?.name?.charAt(0)?.toUpperCase() || "U"}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-900 truncate">{user?.name || "User"}</p>
                <p className="text-xs text-slate-500 truncate">{user?.email}</p>
              </div>
            </div>

            <Button
              variant="ghost"
              className="w-full justify-start text-slate-600 hover:text-red-600 hover:bg-red-50"
              onClick={handleLogout}
              data-testid="logout-btn"
            >
              <LogOut size={18} className="mr-2" />
              Logout
            </Button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Top bar */}
        <header className="sticky top-0 z-30 h-16 bg-white border-b border-slate-200 flex items-center px-4 lg:px-8">
          <button
            className="lg:hidden p-2 -ml-2 text-slate-500 hover:text-slate-700"
            onClick={() => setSidebarOpen(true)}
            data-testid="mobile-menu-btn"
            aria-label="Open menu"
          >
            <Menu size={24} />
          </button>

          <h1 className="ml-1 truncate text-base font-semibold text-slate-900 lg:ml-0 lg:text-lg font-heading">
            {titleForPath(location.pathname)}
          </h1>

          <div className="flex-1" />
        </header>

        {/* Page content */}
        <main className="p-4 lg:p-8 pb-28 lg:pb-8 pb-safe">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default Layout;
