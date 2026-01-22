import React, { useState, useEffect } from "react";
import {
  getOutstandingReport,
  getCreditReport,
  getSalesReport,
  getExpensesReport,
  getCashBankReport,
  getInventoryReport,
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
} from "lucide-react";

const Reports = () => {
  const [activeTab, setActiveTab] = useState("outstanding");
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

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3 sm:grid-cols-6 lg:w-auto lg:inline-grid h-auto">
          <TabsTrigger value="outstanding" data-testid="tab-outstanding">
            <Users className="h-4 w-4 mr-2 hidden sm:inline" />
            Outstanding
          </TabsTrigger>
          <TabsTrigger value="credit" data-testid="tab-credit">
            <CreditCard className="h-4 w-4 mr-2 hidden sm:inline" />
            Credit
          </TabsTrigger>
          <TabsTrigger value="sales" data-testid="tab-sales">
            <TrendingUp className="h-4 w-4 mr-2 hidden sm:inline" />
            Sales
          </TabsTrigger>
          <TabsTrigger value="expenses" data-testid="tab-expenses">
            <Receipt className="h-4 w-4 mr-2 hidden sm:inline" />
            Expenses
          </TabsTrigger>
          <TabsTrigger value="cash-bank" data-testid="tab-cash-bank">
            <Banknote className="h-4 w-4 mr-2 hidden sm:inline" />
            Cash/Bank
          </TabsTrigger>
          <TabsTrigger value="inventory" data-testid="tab-inventory">
            <Package className="h-4 w-4 mr-2 hidden sm:inline" />
            Inventory
          </TabsTrigger>
        </TabsList>

        {/* Date Filter for Sales and Expenses */}
        {(activeTab === "sales" || activeTab === "expenses") && (
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
                        <TableRow key={row.customer_id}>
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
                        <TableRow key={row.customer_id}>
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
                          <TableRow key={inv.id}>
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
                          <TableRow key={exp.id}>
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
                        <TableRow key={item.product_id}>
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
