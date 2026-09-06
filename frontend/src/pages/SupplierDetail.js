import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getSupplierLedger, formatCurrency, formatDate } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import {
  ArrowLeft,
  Phone,
  MapPin,
  TrendingDown,
  TrendingUp,
  FileText,
  Plus,
  Banknote,
  Receipt
} from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import { UIFilters } from "../components/UIFilters";
import { Badge } from "../components/ui/badge";
import { MinusCircle, CreditCard } from "lucide-react";

const SupplierDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState(undefined);

  useEffect(() => {
    fetchData();
  }, [id, dateRange]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const start = dateRange?.from ? dateRange.from.toISOString().split("T")[0] : null;
      const end = dateRange?.to ? dateRange.to.toISOString().split("T")[0] : null;
      const res = await getSupplierLedger(id, start, end);
      setData(res.data);
    } catch (error) {
      toast.error("Failed to load supplier ledger");
      navigate("/suppliers");
    } finally {
      setLoading(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  const { supplier, summary, ledger, advance_payments = [] } = data;

  return (
    <div className="space-y-6 animate-fade-in" data-testid="supplier-ledger-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" aria-label="Back to suppliers" onClick={() => navigate("/suppliers")}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold font-heading text-slate-900">{supplier.name}</h1>
            <div className="flex items-center gap-4 mt-1 text-sm text-slate-500">
              {supplier.phone && (
                <span className="flex items-center gap-1">
                  <Phone className="h-3 w-3" />
                  {supplier.phone}
                </span>
              )}
              {supplier.address && (
                <span className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  {supplier.address}
                </span>
              )}
              {supplier.gstin && (
                <span className="flex items-center gap-1">
                  <FileText className="h-3 w-3" />
                  GSTIN: {supplier.gstin}
               </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button className="bg-brand-600 hover:bg-brand-700" onClick={() => navigate(`/purchases/new?supplier=${id}`)}>
            <Plus className="h-4 w-4 mr-2" />
            New Purchase
          </Button>
        </div>
      </div>

      {/* Date Filters */}
      <div className="bg-white p-4 rounded-xl border shadow-sm">
        <UIFilters
          dateRange={dateRange}
          setDateRange={setDateRange}
          onClear={() => setDateRange(undefined)}
          search={undefined}
          statusFilter={undefined}
        />
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-blue-50 rounded-lg">
                 <Receipt className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500">Total Purchase Value</p>
                <p className="text-xl font-bold font-mono text-slate-900">
                  {formatCurrency(summary.total_purchased)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
             <div className="flex items-center gap-4">
              <div className="p-3 bg-emerald-50 rounded-lg">
                <TrendingDown className="h-5 w-5 text-emerald-600" />
              </div>
               <div>
                 <p className="text-sm text-slate-500">Total Payments Made</p>
                 <p className="text-xl font-bold font-mono text-emerald-600">
                   {formatCurrency(summary.total_paid)}
                 </p>
               </div>
             </div>
          </CardContent>
        </Card>

        <Card className="border-amber-200 bg-amber-50/30">
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-amber-100 rounded-lg">
                <TrendingUp className="h-5 w-5 text-amber-700" />
              </div>
              <div>
                <p className="text-sm font-medium text-amber-800">Current Payable Balance</p>
                <p className="text-2xl font-bold font-mono text-amber-700">
                  {formatCurrency(summary.outstanding)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-indigo-200 bg-indigo-50/30">
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-indigo-100 rounded-lg">
                <Banknote className="h-5 w-5 text-indigo-700" />
              </div>
              <div>
                <p className="text-sm font-medium text-indigo-800">Advance Balance</p>
                <p className="text-2xl font-bold font-mono text-indigo-700">
                  {formatCurrency(summary.adv_balance || 0)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {/* Ledger Table Section */}
          <Card className="h-full">
            <CardHeader className="pb-3 border-b flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-lg">Ledger Transactions</CardTitle>
                <CardDescription>
                   {dateRange?.from ? `Showing transactions for selected period` : 'All time transaction history'}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="relative overflow-x-auto min-h-[400px]">
                 {loading ? (
                  <div className="absolute inset-0 bg-white/50 flex items-center justify-center z-10">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
                  </div>
                ) : null}

                 {ledger.length > 0 ? (
                   <Table>
                     <TableHeader>
                       <TableRow className="bg-slate-50/50">
                         <TableHead>Date</TableHead>
                         <TableHead>Details</TableHead>
                         <TableHead className="text-right text-slate-600">Debit (₹)</TableHead>
                         <TableHead className="text-right text-slate-600">Credit (₹)</TableHead>
                         <TableHead className="text-right border-l font-semibold">Balance (₹)</TableHead>
                       </TableRow>
                     </TableHeader>
                     <TableBody>
                       {ledger.map((entry, index) => (
                          <TableRow
                             key={index}
                             className="hover:bg-slate-50 transition-colors"
                          >
                             <TableCell className="whitespace-nowrap text-slate-500">
                               {formatDate(entry.date)}
                             </TableCell>
                             <TableCell>
                               <div className="flex flex-col">
                                  <span className="font-medium text-slate-900 line-clamp-1">
                                    {entry.narration}
                                  </span>
                                  <span className="text-xs text-slate-500 capitalize">{entry.type}</span>
                               </div>
                             </TableCell>
                             <TableCell className="text-right font-mono text-emerald-600 font-medium">
                               {entry.debit > 0 ? formatCurrency(entry.debit) : "-"}
                             </TableCell>
                             <TableCell className="text-right font-mono text-amber-600 font-medium">
                               {entry.credit > 0 ? formatCurrency(entry.credit) : "-"}
                             </TableCell>
                             <TableCell className="text-right font-mono font-semibold border-l bg-slate-50/30">
                               {formatCurrency(entry.balance)}
                             </TableCell>
                          </TableRow>
                       ))}
                      </TableBody>
                   </Table>
                 ) : (
                   <div className="flex flex-col items-center justify-center py-16 text-slate-500 text-center px-4">
                     <FileText className="h-12 w-12 text-slate-200 mb-3" />
                     <p className="font-medium text-slate-900">No transactions found</p>
                     <p className="text-sm mt-1">Record purchases or payments to see ledger entries.</p>
                   </div>
                 )}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3 border-b border-indigo-100 bg-indigo-50/50">
              <CardTitle className="text-base text-indigo-900 flex items-center">
                <Banknote className="w-4 h-4 mr-2" />
                Active Advance Credits
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-indigo-50">
                {advance_payments.length > 0 ? (
                  advance_payments.map((adv, i) => (
                    <div key={i} className="p-4 hover:bg-slate-50 transition-colors">
                      <div className="flex justify-between items-start mb-1">
                        <span className="font-medium text-sm text-slate-900">
                          Advance
                        </span>
                        <Badge variant="outline" className="bg-indigo-50 text-indigo-700 border-indigo-200">
                          {formatCurrency(adv.remaining_amount)} avail
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-500 line-clamp-2">
                        {"From Payment #..." + adv.payment_id?.slice(-8) || "N/A"}
                      </p>
                      <div className="flex justify-between items-center mt-3 text-xs text-slate-400">
                        <span>Issued: {formatDate(adv.date)}</span>
                        {adv.remaining_amount < adv.amount && (
                          <span>Orig: {formatCurrency(adv.amount)}</span>
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-6 flex flex-col items-center justify-center text-center text-slate-500 bg-white">
                    <MinusCircle className="h-8 w-8 text-slate-200 mb-2" />
                    <span className="text-sm">No active advances</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default SupplierDetail;
