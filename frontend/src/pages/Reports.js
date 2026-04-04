import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  getOutstandingReport,
  getCreditReport,
  getSalesReport,
  getExpensesReport,
  getCashBankReport,
  getInventoryReport,
  getProfitLossReport,
  getTrialBalanceReport,
  getBalanceSheetReport,
  exportReport,
  formatCurrency,
  formatDate,
} from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import {
  Users,
  CreditCard,
  TrendingUp,
  Receipt,
  Banknote,
  Building2,
  Download,
  RefreshCw,
  Package,
  FileText,
  BarChart3,
} from "lucide-react";

const Reports = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("sales");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [dateRange, setDateRange] = useState({
    start: new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split("T")[0],
    end: new Date().toISOString().split("T")[0],
  });

  useEffect(() => {
    fetchReport(activeTab);
  }, [activeTab]);

  const fetchReport = async (type) => {
    setLoading(true);
    try {
      let response;
      switch (type) {
        case "outstanding":
          response = await getOutstandingReport();
          break;
        case "credit":
          response = await getCreditReport();
          break;
        case "sales":
          response = await getSalesReport(dateRange.start, dateRange.end);
          break;
        case "expenses":
          response = await getExpensesReport(dateRange.start, dateRange.end);
          break;
        case "cash-bank":
          response = await getCashBankReport();
          break;
        case "inventory":
          response = await getInventoryReport();
          break;
        case "profit-loss":
          response = await getProfitLossReport(dateRange.start, dateRange.end);
          break;
        case "trial-balance":
          response = await getTrialBalanceReport();
          break;
        case "balance-sheet":
          response = await getBalanceSheetReport();
          break;
        default:
          return;
      }
      setData(response.data);
    } catch (error) {
      toast.error("Failed to load report");
    } finally {
      setLoading(false);
    }
  };

  const handleDateFilter = () => {
    fetchReport(activeTab);
  };

  const handleExport = (format) => {
    try {
      const params = {};
      if (activeTab === "sales" || activeTab === "expenses") {
        params.start_date = dateRange.start;
        params.end_date = dateRange.end;
      }

      const url = exportReport(activeTab, format, params);
      window.location.href = url;
      toast.success(`Exporting ${activeTab} report as ${format.toUpperCase()}...`);
    } catch (error) {
      toast.error("Failed to export report");
    }
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="reports-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">Reports</h1>
          <p className="text-slate-500 mt-1">Business insights and summaries</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => handleExport("csv")} data-testid="export-csv-btn">
            <Download className="h-4 w-4 mr-2" />
            Export CSV
          </Button>
          <Button variant="outline" onClick={() => handleExport("excel")} data-testid="export-excel-btn">
            <FileText className="h-4 w-4 mr-2" />
            Export Excel
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        {/* Mobile: Select Dropdown */}
        <div className="md:hidden">
          <Select value={activeTab} onValueChange={setActiveTab}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select Report" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sales">Sales & Revenue</SelectItem>
              <SelectItem value="expenses">Operating Expenses</SelectItem>
              <SelectItem value="profit-loss">Profit & Loss</SelectItem>
              <SelectItem value="outstanding">Outstanding (Receivables)</SelectItem>
              <SelectItem value="credit">Customer Credit</SelectItem>
              <SelectItem value="cash-bank">Cash & Bank</SelectItem>
              <SelectItem value="inventory">Inventory Valuation</SelectItem>
              <SelectItem value="balance-sheet">Balance Sheet</SelectItem>
              <SelectItem value="trial-balance">Trial Balance</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Desktop: Tabs List */}
        <div className="hidden md:block overflow-x-auto pb-2">
          <TabsList className="w-full justify-start h-auto flex-wrap gap-1 bg-transparent p-0">
            <TabsTrigger value="sales" data-testid="tab-sales" className="data-[state=active]:bg-brand-600 data-[state=active]:text-white">
              <TrendingUp className="h-4 w-4 mr-2" />
              Sales
            </TabsTrigger>
            <TabsTrigger value="expenses" data-testid="tab-expenses" className="data-[state=active]:bg-brand-600 data-[state=active]:text-white">
              <Receipt className="h-4 w-4 mr-2" />
              Expenses
            </TabsTrigger>
            <TabsTrigger value="profit-loss" data-testid="tab-profit-loss" className="data-[state=active]:bg-brand-600 data-[state=active]:text-white">
              <BarChart3 className="h-4 w-4 mr-2" />
              P&L
            </TabsTrigger>
            <TabsTrigger value="outstanding" data-testid="tab-outstanding" className="data-[state=active]:bg-brand-600 data-[state=active]:text-white">
              <Users className="h-4 w-4 mr-2" />
              Outstanding
            </TabsTrigger>
            <TabsTrigger value="credit" data-testid="tab-credit" className="data-[state=active]:bg-brand-600 data-[state=active]:text-white">
              <CreditCard className="h-4 w-4 mr-2" />
              Credit
            </TabsTrigger>
            <TabsTrigger value="cash-bank" data-testid="tab-cash-bank" className="data-[state=active]:bg-brand-600 data-[state=active]:text-white">
              <Banknote className="h-4 w-4 mr-2" />
              Cash/Bank
            </TabsTrigger>
            <TabsTrigger value="inventory" data-testid="tab-inventory" className="data-[state=active]:bg-brand-600 data-[state=active]:text-white">
              <Package className="h-4 w-4 mr-2" />
              Inventory
            </TabsTrigger>
            <TabsTrigger value="balance-sheet" data-testid="tab-balance-sheet" className="data-[state=active]:bg-brand-600 data-[state=active]:text-white">
              <FileText className="h-4 w-4 mr-2" />
              Bal Sheet
            </TabsTrigger>
            <TabsTrigger value="trial-balance" data-testid="tab-trial-balance" className="data-[state=active]:bg-brand-600 data-[state=active]:text-white">
              <Building2 className="h-4 w-4 mr-2" />
              Trial Bal
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Date Filter for Sales and Expenses */}
        {(activeTab === "sales" || activeTab === "expenses" || activeTab === "profit-loss") && (
          <Card className="mt-4">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-end gap-4">
                <div className="space-y-2">
                  <Label>From Date</Label>
                  <Input
                    type="date"
                    value={dateRange.start}
                    onChange={(e) =>
                      setDateRange((prev) => ({ ...prev, start: e.target.value }))
                    }
                    data-testid="report-start-date"
                  />
                </div>
                <div className="space-y-2">
                  <Label>To Date</Label>
                  <Input
                    type="date"
                    value={dateRange.end}
                    onChange={(e) =>
                      setDateRange((prev) => ({ ...prev, end: e.target.value }))
                    }
                    data-testid="report-end-date"
                  />
                </div>
                <Button onClick={handleDateFilter} variant="outline" data-testid="apply-filter-btn">
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Apply Filter
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Outstanding Report */}
        <TabsContent value="outstanding" className="mt-4">
          {loading ? (
            <ReportSkeleton />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>Customer Outstanding</span>
                  <span className="text-xl font-mono text-amber-600">
                    {formatCurrency(data?.total || 0)}
                  </span>
                </CardTitle>
                <CardDescription>Amount pending from customers</CardDescription>
              </CardHeader>
              <CardContent>
                {data?.report?.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Customer</TableHead>
                        <TableHead>Phone</TableHead>
                        <TableHead className="text-right">Outstanding</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.report.map((row) => (
                        <TableRow
                          key={row.customer_id}
                          className="cursor-pointer hover:bg-slate-50"
                          onClick={() => navigate(`/customers/${row.customer_id}`)}
                        >
                          <TableCell className="font-medium">{row.customer_name}</TableCell>
                          <TableCell className="text-slate-500">{row.phone || "-"}</TableCell>
                          <TableCell className="text-right font-mono font-medium text-amber-600">
                            {formatCurrency(row.outstanding)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <EmptyState message="No outstanding amounts" />
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Credit Report */}
        <TabsContent value="credit" className="mt-4">
          {loading ? (
            <ReportSkeleton />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>Customer Credit</span>
                  <span className="text-xl font-mono text-emerald-600">
                    {formatCurrency(data?.total || 0)}
                  </span>
                </CardTitle>
                <CardDescription>Advance payments and overpayments</CardDescription>
              </CardHeader>
              <CardContent>
                {data?.report?.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Customer</TableHead>
                        <TableHead>Phone</TableHead>
                        <TableHead className="text-right">Credit Balance</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.report.map((row) => (
                        <TableRow
                          key={row.customer_id}
                          className="cursor-pointer hover:bg-slate-50"
                          onClick={() => navigate(`/customers/${row.customer_id}`)}
                        >
                          <TableCell className="font-medium">{row.customer_name}</TableCell>
                          <TableCell className="text-slate-500">{row.phone || "-"}</TableCell>
                          <TableCell className="text-right font-mono font-medium text-emerald-600">
                            {formatCurrency(row.credit)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <EmptyState message="No customer credits" />
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Sales Report */}
        <TabsContent value="sales" className="mt-4">
          {loading ? (
            <ReportSkeleton />
          ) : (
            <div className="space-y-4">
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                  <CardContent className="p-4">
                    <p className="text-sm text-slate-500">Total Sales</p>
                    <p className="text-2xl font-bold font-mono text-slate-900">
                      {formatCurrency(data?.total_sales || 0)}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <p className="text-sm text-slate-500">Collected</p>
                    <p className="text-2xl font-bold font-mono text-emerald-600">
                      {formatCurrency(data?.total_collected || 0)}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <p className="text-sm text-slate-500">Pending</p>
                    <p className="text-2xl font-bold font-mono text-amber-600">
                      {formatCurrency(data?.pending || 0)}
                    </p>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle>Invoice Details</CardTitle>
                </CardHeader>
                <CardContent>
                  {data?.invoices?.length > 0 ? (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Invoice #</TableHead>
                          <TableHead>Customer</TableHead>
                          <TableHead>Date</TableHead>
                          <TableHead className="text-right">Total</TableHead>
                          <TableHead className="text-right">Paid</TableHead>
                          <TableHead>Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.invoices.map((inv) => (
                          <TableRow
                            key={inv.id}
                            className="cursor-pointer hover:bg-slate-50"
                            onClick={() => navigate(`/invoices/${inv.id}`)}
                          >
                            <TableCell className="font-medium text-brand-600">
                              {inv.invoice_number}
                            </TableCell>
                            <TableCell>{inv.customer_name}</TableCell>
                            <TableCell className="text-slate-500">{formatDate(inv.date)}</TableCell>
                            <TableCell className="text-right font-mono">
                              {formatCurrency(inv.total)}
                            </TableCell>
                            <TableCell className="text-right font-mono text-emerald-600">
                              {formatCurrency(inv.paid_amount || 0)}
                            </TableCell>
                            <TableCell>
                              <span
                                className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium badge-${inv.status}`}
                              >
                                {inv.status.replace("_", " ")}
                              </span>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <EmptyState message="No sales in this period" />
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* Expenses Report */}
        <TabsContent value="expenses" className="mt-4">
          {loading ? (
            <ReportSkeleton />
          ) : (
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span>Total Expenses</span>
                    <span className="text-xl font-mono text-rose-600">
                      {formatCurrency(data?.total || 0)}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {data?.by_category && Object.keys(data.by_category).length > 0 && (
                    <div className="mb-6">
                      <h4 className="text-sm font-medium text-slate-500 mb-3">By Category</h4>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {Object.entries(data.by_category).map(([cat, amount]) => (
                          <div key={cat} className="p-3 bg-slate-50 rounded-lg">
                            <p className="text-xs text-slate-500">{cat}</p>
                            <p className="font-mono font-medium">{formatCurrency(amount)}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {data?.expenses?.length > 0 ? (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Description</TableHead>
                          <TableHead>Category</TableHead>
                          <TableHead>Date</TableHead>
                          <TableHead>Mode</TableHead>
                          <TableHead className="text-right">Amount</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.expenses.map((exp) => (
                          <TableRow
                            key={exp.id}
                            className="cursor-pointer hover:bg-slate-50"
                            onClick={() => navigate("/expenses")}
                          >
                            <TableCell className="font-medium">{exp.description}</TableCell>
                            <TableCell className="text-slate-500">{exp.category || "Other"}</TableCell>
                            <TableCell className="text-slate-500">{formatDate(exp.date)}</TableCell>
                            <TableCell className="capitalize">{exp.mode}</TableCell>
                            <TableCell className="text-right font-mono text-rose-600">
                              -{formatCurrency(exp.amount)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <EmptyState message="No expenses in this period" />
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* Cash/Bank Report */}
        <TabsContent value="cash-bank" className="mt-4">
          {loading ? (
            <ReportSkeleton />
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                  <CardContent className="p-6">
                    <div className="flex items-center gap-4">
                      <div className="p-3 bg-emerald-50 rounded-lg">
                        <Banknote className="h-5 w-5 text-emerald-600" />
                      </div>
                      <div>
                        <p className="text-sm text-slate-500">Cash Balance</p>
                        <p className="text-2xl font-bold font-mono text-emerald-600">
                          {formatCurrency(data?.cash_balance || 0)}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-6">
                    <div className="flex items-center gap-4">
                      <div className="p-3 bg-blue-50 rounded-lg">
                        <Building2 className="h-5 w-5 text-blue-600" />
                      </div>
                      <div>
                        <p className="text-sm text-slate-500">Bank Balance</p>
                        <p className="text-2xl font-bold font-mono text-blue-600">
                          {formatCurrency(data?.bank_balance || 0)}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-6">
                    <div className="flex items-center gap-4">
                      <div className="p-3 bg-brand-50 rounded-lg">
                        <TrendingUp className="h-5 w-5 text-brand-600" />
                      </div>
                      <div>
                        <p className="text-sm text-slate-500">Total Balance</p>
                        <p className="text-2xl font-bold font-mono text-brand-600">
                          {formatCurrency(data?.total_balance || 0)}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Cash Transactions */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Recent Cash Transactions</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {data?.cash_transactions?.length > 0 ? (
                      <div className="space-y-2">
                        {data.cash_transactions.slice(0, 10).map((t, i) => (
                          <div
                            key={i}
                            className="flex justify-between items-center p-2 rounded hover:bg-slate-50"
                          >
                            <div>
                              <p className="text-sm font-medium">{t.narration}</p>
                              <p className="text-xs text-slate-500">{formatDate(t.date)}</p>
                            </div>
                            <p
                              className={`font-mono text-sm ${t.debit > 0 ? "text-emerald-600" : "text-rose-600"
                                }`}
                            >
                              {t.debit > 0 ? "+" : "-"}
                              {formatCurrency(t.debit > 0 ? t.debit : t.credit)}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState message="No cash transactions" />
                    )}
                  </CardContent>
                </Card>

                {/* Bank Transactions */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Recent Bank Transactions</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {data?.bank_transactions?.length > 0 ? (
                      <div className="space-y-2">
                        {data.bank_transactions.slice(0, 10).map((t, i) => (
                          <div
                            key={i}
                            className="flex justify-between items-center p-2 rounded hover:bg-slate-50"
                          >
                            <div>
                              <p className="text-sm font-medium">{t.narration}</p>
                              <p className="text-xs text-slate-500">{formatDate(t.date)}</p>
                            </div>
                            <p
                              className={`font-mono text-sm ${t.debit > 0 ? "text-emerald-600" : "text-rose-600"
                                }`}
                            >
                              {t.debit > 0 ? "+" : "-"}
                              {formatCurrency(t.debit > 0 ? t.debit : t.credit)}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState message="No bank transactions" />
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          )}
        </TabsContent>

        {/* Inventory Report */}
        <TabsContent value="inventory" className="mt-4">
          {loading ? (
            <ReportSkeleton />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>Inventory Value</span>
                  <span className="text-xl font-mono text-brand-600">
                    {formatCurrency(data?.total_value || 0)}
                  </span>
                </CardTitle>
                <CardDescription>Current stock valuation (Cost Price)</CardDescription>
              </CardHeader>
              <CardContent>
                {data?.report?.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Product</TableHead>
                        <TableHead>SKU</TableHead>
                        <TableHead className="text-right">Stock</TableHead>
                        <TableHead className="text-right">Cost Price</TableHead>
                        <TableHead className="text-right">Value</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.report.map((item) => (
                        <TableRow
                          key={item.product_id}
                          className="cursor-pointer hover:bg-slate-50"
                          onClick={() => navigate("/products")}
                        >
                          <TableCell className="font-medium">
                            <div className="flex flex-col">
                              <span>{item.product_name}</span>
                              {item.is_low_stock && (
                                <span className="text-xs text-rose-600">Low Stock</span>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-slate-500 text-xs">{item.sku || "-"}</TableCell>
                          <TableCell className="text-right font-mono">
                            <span className={item.is_low_stock ? "text-rose-600 font-bold" : ""}>
                              {item.current_stock}
                            </span>
                          </TableCell>
                          <TableCell className="text-right font-mono text-slate-500">
                            {formatCurrency(item.cost_price)}
                          </TableCell>
                          <TableCell className="text-right font-mono font-medium text-brand-600">
                            {formatCurrency(item.value)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <EmptyState message="No inventory items found" />
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Profit & Loss */}
        <TabsContent value="profit-loss">
          {loading ? (
            <ReportSkeleton />
          ) : data ? (
            <Card>
              <CardContent className="p-6">
                <h2 className="text-lg font-bold text-slate-900 mb-6">Profit & Loss Statement</h2>
                <div className="space-y-6">
                  {/* Income */}
                  <div>
                    <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Income</h3>
                    <div className="space-y-2">
                      <div className="flex justify-between py-2 px-3 bg-slate-50 rounded">
                        <span className="text-slate-700">Sales ({data.income?.invoice_count || 0} invoices)</span>
                        <span className="font-mono font-medium text-slate-900">{formatCurrency(data.income?.total_sales || 0)}</span>
                      </div>
                      {(data.income?.credit_notes || 0) > 0 && (
                        <div className="flex justify-between py-2 px-3">
                          <span className="text-slate-500">Less: Credit Notes (Sales Returns)</span>
                          <span className="font-mono text-orange-600">-{formatCurrency(data.income?.credit_notes || 0)}</span>
                        </div>
                      )}
                      <div className="flex justify-between py-2 px-3 border-t border-slate-200 font-medium">
                        <span className="text-slate-900">Net Sales</span>
                        <span className="font-mono text-brand-700">{formatCurrency(data.income?.net_sales || 0)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Cost of Goods */}
                  <div>
                    <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Cost of Goods Sold</h3>
                    <div className="space-y-2">
                      <div className="flex justify-between py-2 px-3 bg-slate-50 rounded">
                        <span className="text-slate-700">Purchase Cost</span>
                        <span className="font-mono font-medium text-slate-900">{formatCurrency(data.cost_of_goods?.total_cost || 0)}</span>
                      </div>
                      {(data.cost_of_goods?.debit_notes || 0) > 0 && (
                        <div className="flex justify-between py-2 px-3">
                          <span className="text-slate-500">Less: Debit Notes (Purchase Returns)</span>
                          <span className="font-mono text-orange-600">-{formatCurrency(data.cost_of_goods?.debit_notes || 0)}</span>
                        </div>
                      )}
                      <div className="flex justify-between py-2 px-3 border-t border-slate-200 font-medium">
                        <span className="text-slate-900">Net COGS</span>
                        <span className="font-mono text-slate-700">{formatCurrency(data.cost_of_goods?.net_cost || 0)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Gross Profit */}
                  <div className="flex justify-between py-3 px-4 bg-brand-50 rounded-lg border border-brand-200">
                    <span className="font-bold text-brand-800">Gross Profit</span>
                    <span className="font-mono font-bold text-brand-700">{formatCurrency(data.gross_profit || 0)}</span>
                  </div>

                  {/* Expenses */}
                  <div>
                    <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Operating Expenses</h3>
                    <div className="space-y-2">
                      {data.expenses?.categories && Object.entries(data.expenses.categories).map(([cat, amount]) => (
                        <div key={cat} className="flex justify-between py-2 px-3 bg-slate-50 rounded">
                          <span className="text-slate-700">{cat}</span>
                          <span className="font-mono text-rose-600">-{formatCurrency(amount)}</span>
                        </div>
                      ))}
                      <div className="flex justify-between py-2 px-3 border-t border-slate-200 font-medium">
                        <span className="text-slate-900">Total Expenses</span>
                        <span className="font-mono text-rose-600">-{formatCurrency(data.expenses?.total || 0)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Net Profit */}
                  <div className={`flex justify-between py-3 px-4 rounded-lg border ${(data.net_profit || 0) >= 0 ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'}`}>
                    <span className={`font-bold ${(data.net_profit || 0) >= 0 ? 'text-emerald-800' : 'text-rose-800'}`}>Net Profit</span>
                    <span className={`font-mono font-bold ${(data.net_profit || 0) >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                      {formatCurrency(data.net_profit || 0)}
                    </span>
                  </div>

                  {/* Margin */}
                  <div className="text-center text-sm text-slate-500">
                    Gross Margin: <span className="font-medium text-slate-700">{(data.margin_percent || 0).toFixed(1)}%</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </TabsContent>

        {/* Trial Balance */}
        <TabsContent value="trial-balance">
          {loading ? (
            <ReportSkeleton />
          ) : data ? (
            <Card>
              <CardHeader>
                <CardTitle>Trial Balance</CardTitle>
                <CardDescription>As of {formatDate(new Date())}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex justify-between mb-6 p-4 bg-slate-50 rounded-lg border border-slate-200">
                  <div className="text-center">
                    <p className="text-sm text-slate-500 uppercase font-semibold">Total Debit</p>
                    <p className="text-lg font-mono font-bold text-slate-900">{formatCurrency(data.total_debit)}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-slate-500 uppercase font-semibold">Total Credit</p>
                    <p className="text-lg font-mono font-bold text-slate-900">{formatCurrency(data.total_credit)}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-slate-500 uppercase font-semibold">Status</p>
                    <p className={`text-lg font-bold ${data.is_balanced ? "text-emerald-600" : "text-rose-600"}`}>
                      {data.is_balanced ? "Balanced" : "Unbalanced"}
                    </p>
                  </div>
                </div>
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Account</TableHead>
                        <TableHead className="text-right">Debit</TableHead>
                        <TableHead className="text-right">Credit</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.entries && data.entries.map((entry, idx) => (
                        <TableRow key={idx}>
                          <TableCell className="font-medium capitalize">{entry.account.replace(/[:_]/g, ' ')}</TableCell>
                          <TableCell className="text-right font-mono text-slate-600">{entry.debit > 0 ? formatCurrency(entry.debit) : "-"}</TableCell>
                          <TableCell className="text-right font-mono text-slate-600">{entry.credit > 0 ? formatCurrency(entry.credit) : "-"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </TabsContent>

        {/* Balance Sheet */}
        <TabsContent value="balance-sheet">
          {loading ? (
            <ReportSkeleton />
          ) : data ? (
            <div className="space-y-6">
              <div className={`p-4 rounded-lg border flex justify-between items-center ${data.is_balanced ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`}>
                <span className={`font-bold ${data.is_balanced ? "text-emerald-800" : "text-rose-800"}`}>
                  {data.is_balanced ? "Balance Sheet is Balanced" : "Balance Sheet is Unbalanced"}
                </span>
                {!data.is_balanced && <span className="text-xs text-rose-600">Assets != Liab + Equity</span>}
              </div>

              <div className="grid md:grid-cols-2 gap-6">
                {/* Assets */}
                <Card className="h-full">
                  <CardHeader className="bg-slate-50 border-b pb-3">
                    <CardTitle className="text-lg">Assets</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <Table>
                      <TableBody>
                        <TableRow>
                          <TableCell>Cash</TableCell>
                          <TableCell className="text-right font-mono">{formatCurrency(data.assets?.cash)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Bank</TableCell>
                          <TableCell className="text-right font-mono">{formatCurrency(data.assets?.bank)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Accounts Receivable</TableCell>
                          <TableCell className="text-right font-mono">{formatCurrency(data.assets?.accounts_receivable)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Inventory</TableCell>
                          <TableCell className="text-right font-mono">{formatCurrency(data.assets?.inventory)}</TableCell>
                        </TableRow>
                        <TableRow className="bg-slate-50 font-bold border-t-2">
                          <TableCell>Total Assets</TableCell>
                          <TableCell className="text-right font-mono text-brand-700">{formatCurrency(data.assets?.total)}</TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                {/* Liabilities & Equity */}
                <div className="space-y-6">
                  <Card>
                    <CardHeader className="bg-slate-50 border-b pb-3">
                      <CardTitle className="text-lg">Liabilities</CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <Table>
                        <TableBody>
                          <TableRow>
                            <TableCell>Accounts Payable</TableCell>
                            <TableCell className="text-right font-mono">{formatCurrency(data.liabilities?.accounts_payable)}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell>Customer Credits</TableCell>
                            <TableCell className="text-right font-mono">{formatCurrency(data.liabilities?.customer_credits)}</TableCell>
                          </TableRow>
                          <TableRow className="bg-slate-50 font-bold border-t-2">
                            <TableCell>Total Liabilities</TableCell>
                            <TableCell className="text-right font-mono">{formatCurrency(data.liabilities?.total)}</TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="bg-slate-50 border-b pb-3">
                      <CardTitle className="text-lg">Equity</CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <Table>
                        <TableBody>
                          <TableRow>
                            <TableCell>Net Profit</TableCell>
                            <TableCell className="text-right font-mono">{formatCurrency(data.equity?.net_profit)}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell>Capital / Retained Earnings</TableCell>
                            <TableCell className="text-right font-mono">{formatCurrency(data.equity?.total - data.equity?.net_profit)}</TableCell>
                          </TableRow>
                          <TableRow className="bg-slate-50 font-bold border-t-2">
                            <TableCell>Total Equity</TableCell>
                            <TableCell className="text-right font-mono">{formatCurrency(data.equity?.total)}</TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                  <Card className="bg-slate-900 text-white">
                    <CardContent className="p-4 flex justify-between items-center">
                      <span className="font-semibold">Total Liabilities + Equity</span>
                      <span className="font-mono font-bold text-lg">{formatCurrency((data.liabilities?.total || 0) + (data.equity?.total || 0))}</span>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          ) : null}
        </TabsContent>
      </Tabs>
    </div>
  );
};

const ReportSkeleton = () => (
  <Card>
    <CardContent className="p-6">
      <div className="space-y-4">
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    </CardContent>
  </Card>
);

const EmptyState = ({ message }) => (
  <div className="text-center py-8 text-slate-500">
    <p>{message}</p>
  </div>
);

export default Reports;
