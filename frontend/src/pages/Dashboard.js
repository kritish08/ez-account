import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { getDashboard, formatCurrency, formatDate } from "../lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
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
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboard();
  }, []);

  const fetchDashboard = async () => {
    try {
      const response = await getDashboard();
      setData(response.data);
    } catch (error) {
      console.error("Failed to fetch dashboard:", error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-8 animate-fade-in">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[...Array(6)].map((_, i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-8 w-32" />
              </CardContent>
            </Card>
          ))}
        </div>
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
          label="Today's Sales"
          value={formatCurrency(data?.today_sales)}
          color="text-emerald-600"
        />
        <StatCard
          icon={Calendar}
          label="Monthly Sales"
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
    </div>
  );
};

export default Dashboard;
