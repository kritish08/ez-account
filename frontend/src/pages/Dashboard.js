import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useModules } from "../context/ModulesContext";
import { getDashboard, formatCurrency, formatDate, resetSystem } from "../lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import {
  Banknote,
  Building2,
  Users,
  CreditCard,
  TrendingUp,
  Calendar,
  FileText,
  ArrowRight,
  Plus,
  AlertTriangle,
  Receipt,
  Package,
  Trash2,
} from "lucide-react";

const StatCard = ({ icon: Icon, label, value, subValue, color }) => (
  <Card className="hover:shadow-md transition-shadow">
    <CardContent className="p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <p className={`text-2xl font-bold font-mono mt-1 ${color || "text-slate-900"}`}>
            {value}
          </p>
          {subValue && <p className="text-xs text-slate-400 mt-1">{subValue}</p>}
        </div>
        <div className={`p-3 rounded-lg ${color ? `bg-${color.split('-')[1]}-50` : "bg-slate-100"}`}>
          <Icon className={`h-5 w-5 ${color || "text-slate-600"}`} />
        </div>
      </div>
    </CardContent>
  </Card>
);

const Dashboard = () => {
  const { modules } = useModules();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    // Cancellation guard prevents setState-after-unmount.
    let cancelled = false;
    const fetchDashboard = async () => {
      try {
        setLoadError(null);
        const response = await getDashboard();
        if (!cancelled) setData(response.data);
      } catch (error) {
        if (!cancelled) {
          console.error("Failed to fetch dashboard:", error);
          setLoadError(error?.response?.data?.detail || "Failed to load dashboard");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchDashboard();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="space-y-8 animate-fade-in">
        {/* Quick Actions Skeleton */}
        <div className="flex flex-wrap gap-3">
          <Skeleton className="h-10 w-32" />
          <Skeleton className="h-10 w-36" />
          <Skeleton className="h-10 w-32" />
        </div>

        {/* Stats Grid Skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(9)].map((_, i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="flex items-start justify-between">
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-8 w-32" />
                    <Skeleton className="h-3 w-20" />
                  </div>
                  <Skeleton className="h-10 w-10 rounded-lg" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Recent Activity Skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Recent Invoices Skeleton */}
          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-32" />
            </CardHeader>
            <CardContent className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <Skeleton className="h-10 w-10 rounded" />
                    <div className="space-y-2">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                  </div>
                  <Skeleton className="h-4 w-20" />
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Recent Payments Skeleton */}
          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-32" />
            </CardHeader>
            <CardContent className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <Skeleton className="h-10 w-10 rounded" />
                    <div className="space-y-2">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                  </div>
                  <Skeleton className="h-4 w-20" />
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  if (loadError || !data) {
    return (
      <div className="space-y-4 animate-fade-in p-8 text-center" data-testid="dashboard-error">
        <AlertTriangle className="h-8 w-8 mx-auto text-red-500" />
        <h2 className="text-lg font-semibold text-slate-900">Dashboard couldn't load</h2>
        <p className="text-sm text-slate-500">{loadError || "Unable to fetch dashboard data. Please try again."}</p>
        <Button onClick={() => window.location.reload()}>Reload</Button>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in" data-testid="dashboard">
      {/* Quick Actions */}
      <div className="flex flex-wrap gap-3">
        <Link to="/invoices/new">
          <Button className="bg-brand-600 hover:bg-brand-700" data-testid="new-invoice-btn">
            <Plus className="h-4 w-4 mr-2" />
            New Invoice
          </Button>
        </Link>
        <Link to="/payments">
          <Button variant="outline" data-testid="record-payment-btn">
            <CreditCard className="h-4 w-4 mr-2" />
            Record Payment
          </Button>
        </Link>
        <Link to="/expenses">
          <Button variant="outline" data-testid="add-expense-btn">
            <Banknote className="h-4 w-4 mr-2" />
            Add Expense
          </Button>
        </Link>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <StatCard
          icon={TrendingUp}
          label="Today's Billed Revenue"
          value={formatCurrency(data?.today_sales)}
          color="text-emerald-600"
        />
        <StatCard
          icon={Calendar}
          label="Monthly Billed Revenue"
          value={formatCurrency(data?.monthly_sales)}
          subValue="This month"
          color="text-brand-600"
        />
        <StatCard
          icon={Receipt}
          label="Monthly Expenses"
          value={formatCurrency(data?.monthly_expenses)}
          subValue="This month"
          color="text-rose-600"
        />
        <StatCard
          icon={Banknote}
          label="Cash Balance"
          value={formatCurrency(data?.cash_balance)}
          color="text-emerald-600"
        />
        <StatCard
          icon={Building2}
          label="Bank Balance"
          value={formatCurrency(data?.bank_balance)}
          color="text-blue-600"
        />
        <StatCard
          icon={Users}
          label="Outstanding from Customers"
          value={formatCurrency(data?.total_outstanding)}
          subValue={`${data?.total_customers || 0} customers`}
          color="text-amber-600"
        />
        <StatCard
          icon={CreditCard}
          label="Supplier Payable"
          value={formatCurrency(data?.total_payable)}
          subValue={`${data?.total_suppliers || 0} suppliers`}
          color="text-orange-600"
        />
        <StatCard
          icon={AlertTriangle}
          label="Overdue Invoices"
          value={data?.overdue_count || 0}
          subValue={data?.overdue_count > 0 ? "Needs attention" : "All clear"}
          color={data?.overdue_count > 0 ? "text-rose-600" : "text-emerald-600"}
        />
        <StatCard
          icon={Package}
          label="Low Stock Products"
          value={data?.low_stock_count || 0}
          subValue={`of ${data?.total_products || 0} products`}
          color={data?.low_stock_count > 0 ? "text-amber-600" : "text-emerald-600"}
        />
      </div>

      {/* Manufacturing Floor Area */}
      {modules?.enable_production && (
        <div className="animate-fade-in mt-8 mb-6">
          <h2 className="text-xl font-bold font-heading text-slate-900 mb-4">Manufacturing Floor</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 border-l-4 border-brand-500 pl-4 py-2 bg-slate-50/50 rounded-r-xl">
            <StatCard
              icon={Building2}
              label="Active Operations"
              value={data?.active_work_orders || 0}
              subValue="Orders currently IN_PROGRESS"
              color="text-brand-600"
            />
            <StatCard
              icon={AlertTriangle}
              label="Pending QC"
              value={data?.completed_work_orders || 0}
              subValue="Completed this month"
              color="text-amber-600"
            />
            <StatCard
              icon={Calendar}
              label="Planned Queue"
              value={data?.planned_work_orders || 0}
              subValue="Waiting for raw materials/start"
              color="text-indigo-600"
            />
          </div>
        </div>
      )}

      {/* Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Invoices */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-lg font-semibold">Recent Invoices</CardTitle>
            <Link to="/invoices">
              <Button variant="ghost" size="sm">
                View all <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {data?.recent_invoices?.length > 0 ? (
              <div className="space-y-3">
                {data.recent_invoices.map((invoice) => (
                  <Link
                    key={invoice.id}
                    to={`/invoices/${invoice.id}`}
                    className="flex items-center justify-between p-3 rounded-lg hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-slate-100 rounded-lg">
                        <FileText className="h-4 w-4 text-slate-600" />
                      </div>
                      <div>
                        <p className="font-medium text-sm text-slate-900">{invoice.invoice_number}</p>
                        <p className="text-xs text-slate-500">{invoice.customer_name}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm font-medium">{formatCurrency(invoice.total)}</p>
                      <span className={`text-xs px-2 py-0.5 rounded-full badge-${invoice.status}`}>
                        {invoice.status.replace("_", " ")}
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">No invoices yet</p>
            )}
          </CardContent>
        </Card>

        {/* Recent Payments */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-lg font-semibold">Recent Payments</CardTitle>
            <Link to="/payments">
              <Button variant="ghost" size="sm">
                View all <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {data?.recent_payments?.length > 0 ? (
              <div className="space-y-3">
                {data.recent_payments.map((payment) => (
                  <div
                    key={payment.id}
                    className="flex items-center justify-between p-3 rounded-lg hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-emerald-50 rounded-lg">
                        <CreditCard className="h-4 w-4 text-emerald-600" />
                      </div>
                      <div>
                        <p className="font-medium text-sm text-slate-900">{payment.customer_name}</p>
                        <p className="text-xs text-slate-500">{formatDate(payment.date)}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm font-medium text-emerald-600">
                        +{formatCurrency(payment.amount)}
                      </p>
                      <span className="text-xs text-slate-500 capitalize">{payment.mode}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">No payments yet</p>
            )}
          </CardContent>
        </Card>
      </div>
      {/* Recent Activity Round 2: Purchases & Expenses */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        {/* Recent Purchases */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-lg font-semibold">Recent Purchases</CardTitle>
            <Link to="/purchases">
              <Button variant="ghost" size="sm">
                View all <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {data?.recent_purchases?.length > 0 ? (
              <div className="space-y-3">
                {data.recent_purchases.map((purchase) => (
                  <Link
                    key={purchase.id}
                    to={`/purchases?id=${purchase.id}`}
                    className="flex items-center justify-between p-3 rounded-lg hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-slate-100 rounded-lg">
                        <Package className="h-4 w-4 text-slate-600" />
                      </div>
                      <div>
                        <p className="font-medium text-sm text-slate-900">{purchase.supplier_name || 'Cash Purchase'}</p>
                        <p className="text-xs text-slate-500">{formatDate(purchase.date)}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm font-medium">{formatCurrency(purchase.total)}</p>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${purchase.payment_status === 'paid' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                        {purchase.payment_status}
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">No purchases yet</p>
            )}
          </CardContent>
        </Card>

        {/* Recent Expenses */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-lg font-semibold">Recent Expenses</CardTitle>
            <Link to="/expenses">
              <Button variant="ghost" size="sm">
                View all <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {data?.recent_expenses?.length > 0 ? (
              <div className="space-y-3">
                {data.recent_expenses.map((expense) => (
                  <div
                    key={expense.id}
                    className="flex items-center justify-between p-3 rounded-lg hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-rose-50 rounded-lg">
                        <Receipt className="h-4 w-4 text-rose-600" />
                      </div>
                      <div>
                        <p className="font-medium text-sm text-slate-900">{expense.description}</p>
                        <p className="text-xs text-slate-500">{formatDate(expense.date)} • {expense.category || 'Other'}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm font-medium text-rose-600">
                        -{formatCurrency(expense.amount)}
                      </p>
                      <span className="text-xs text-slate-500 capitalize">{expense.mode}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">No expenses yet</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* IMS Alerts (Optional) */}
      {modules?.enable_advanced_ims && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Card className="border-amber-200 shadow-sm">
            <CardHeader className="flex flex-row items-center justify-between pb-2 bg-amber-50/50 rounded-t-xl border-b border-amber-100">
              <CardTitle className="text-lg font-semibold text-amber-900 flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
                Low Stock Alerts
              </CardTitle>
              <Link to="/products">
                <Button variant="ghost" size="sm" className="text-amber-700 hover:text-amber-800 hover:bg-amber-100">
                  View inventory <ArrowRight className="h-4 w-4 ml-1" />
                </Button>
              </Link>
            </CardHeader>
            <CardContent className="pt-4">
              {data?.low_stock_products?.length > 0 ? (
                <div className="space-y-3">
                  {data.low_stock_products.map((product) => (
                    <Link
                      key={product.id}
                      to={`/products/${product.id}`}
                      className="flex items-center justify-between p-3 rounded-lg hover:bg-amber-50 transition-colors border border-transparent hover:border-amber-100"
                    >
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-amber-100 rounded-lg">
                          <Package className="h-4 w-4 text-amber-700" />
                        </div>
                        <div>
                          <p className="font-medium text-sm text-slate-900">{product.name}</p>
                          <p className="text-xs text-amber-600 font-medium">
                            Stock: {product.current_stock} (Min: {product.low_stock_threshold})
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <span className="text-xs font-bold px-2 py-1 rounded-full bg-rose-100 text-rose-700">
                          Reorder
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-center bg-slate-50/50 rounded-lg border border-slate-100 border-dashed">
                  <div className="h-10 w-10 bg-emerald-100 rounded-full flex items-center justify-center mb-3">
                    <Package className="h-5 w-5 text-emerald-600" />
                  </div>
                  <p className="text-sm font-medium text-slate-900">Inventory looks healthy</p>
                  <p className="text-xs text-slate-500 mt-1">No products are currently running low on stock.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
