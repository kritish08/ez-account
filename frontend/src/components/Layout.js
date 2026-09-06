import React, { useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
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

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/customers", icon: Users, label: "Customers" },
  { to: "/finished-goods", icon: Package, label: "Finished Goods" },
  { to: "/suppliers", icon: Truck, label: "Suppliers" },
  { to: "/raw-materials", icon: Layers, label: "Raw Materials", requireModule: "enable_production" },
  { to: "/purchases", icon: ShoppingCart, label: "Purchases" },
  { to: "/production", icon: Factory, label: "Production", requireModule: "enable_production" },
  { to: "/invoices", icon: FileText, label: "Invoices" },
  { to: "/payments", icon: CreditCard, label: "Payments" },
  { to: "/expenses", icon: Receipt, label: "Expenses" },
  { to: "/credit-notes", icon: RotateCcw, label: "Credit Notes" },
  { to: "/debit-notes", icon: Undo2, label: "Debit Notes" },
  { to: "/reports", icon: BarChart3, label: "Reports" },
];

const Layout = () => {
  const { user, logout } = useAuth();
  const { modules } = useModules();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const filteredNavItems = navItems.filter((item) => {
    if (item.to === "/credit-notes" && modules?.enable_credit_notes === false) return false;
    if (item.to === "/debit-notes" && modules?.enable_debit_notes === false) return false;
    if (item.requireModule && !modules?.[item.requireModule]) return false;
    return true;
  });

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
            >
              <X size={20} />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
            {filteredNavItems.map((item) => (
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
                <item.icon size={20} />
                {item.label}
              </NavLink>
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
          >
            <Menu size={24} />
          </button>

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
