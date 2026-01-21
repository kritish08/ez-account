import React, { useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
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
  Truck,
  ShoppingCart,
} from "lucide-react";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/customers", icon: Users, label: "Customers" },
  { to: "/products", icon: Package, label: "Products" },
  { to: "/suppliers", icon: Truck, label: "Suppliers" },
  { to: "/purchases", icon: ShoppingCart, label: "Purchases" },
  { to: "/invoices", icon: FileText, label: "Invoices" },
  { to: "/payments", icon: CreditCard, label: "Payments" },
  { to: "/expenses", icon: Receipt, label: "Expenses" },
  { to: "/reports", icon: BarChart3, label: "Reports" },
];

const Layout = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-slate-900/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 z-50 h-full w-64 bg-white border-r border-slate-200 transform transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center justify-between h-16 px-6 border-b border-slate-200">
            <h1 className="text-xl font-bold text-brand-600 font-heading">EZ Accounts</h1>
            <button
              className="lg:hidden p-1 text-slate-500 hover:text-slate-700"
              onClick={() => setSidebarOpen(false)}
            >
              <X size={20} />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
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
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all mb-1 ${
                  isActive
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
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all mb-3 ${
                  isActive
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
        <main className="p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default Layout;
