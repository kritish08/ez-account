import React, { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { getPayments, getCustomers, createPayment, formatCurrency, formatDate } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
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
import { Plus, CreditCard, Loader2, Banknote, Building2 } from "lucide-react";

const Payments = () => {
  const [searchParams] = useSearchParams();
  const preselectedCustomer = searchParams.get("customer");

  const [payments, setPayments] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(!!preselectedCustomer);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    customer_id: preselectedCustomer || "",
    amount: "",
    mode: "cash",
    date: new Date().toISOString().split("T")[0],
    notes: "",
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [paymentsRes, customersRes] = await Promise.all([
        getPayments(),
        getCustomers(),
      ]);
      setPayments(paymentsRes.data);
      setCustomers(customersRes.data);
    } catch (error) {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.customer_id) {
      toast.error("Please select a customer");
      return;
    }
    
    if (!formData.amount || parseFloat(formData.amount) <= 0) {
      toast.error("Please enter a valid amount");
      return;
    }

    setSaving(true);
    try {
      const response = await createPayment({
        ...formData,
        amount: parseFloat(formData.amount),
      });
      
      let message = "Payment recorded successfully!";
      if (response.data.excess_as_credit > 0) {
        message += ` ${formatCurrency(response.data.excess_as_credit)} added as customer credit.`;
      }
      toast.success(message);
      
      setDialogOpen(false);
      setFormData({
        customer_id: "",
        amount: "",
        mode: "cash",
        date: new Date().toISOString().split("T")[0],
        notes: "",
      });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to record payment");
    } finally {
      setSaving(false);
    }
  };

  const selectedCustomer = customers.find((c) => c.id === formData.customer_id);

  return (
    <div className="space-y-6 animate-fade-in" data-testid="payments-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">Payments</h1>
          <p className="text-slate-500 mt-1">Record and track customer payments</p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="bg-brand-600 hover:bg-brand-700" data-testid="record-payment-btn">
              <Plus className="h-4 w-4 mr-2" />
              Record Payment
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Record Payment</DialogTitle>
              <DialogDescription>Enter payment details below</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label>Customer *</Label>
                <Select
                  value={formData.customer_id}
                  onValueChange={(value) =>
                    setFormData((prev) => ({ ...prev, customer_id: value }))
                  }
                >
                  <SelectTrigger data-testid="payment-customer-select">
                    <SelectValue placeholder="Select customer" />
                  </SelectTrigger>
                  <SelectContent>
                    {customers.map((customer) => (
                      <SelectItem key={customer.id} value={customer.id}>
                        <div className="flex justify-between items-center w-full">
                          <span>{customer.name}</span>
                          {customer.outstanding > 0 && (
                            <span className="text-xs text-amber-600 ml-2">
                              Due: {formatCurrency(customer.outstanding)}
                            </span>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedCustomer?.outstanding > 0 && (
                  <p className="text-sm text-amber-600">
                    Outstanding: {formatCurrency(selectedCustomer.outstanding)}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="amount">Amount *</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono">₹</span>
                  <Input
                    id="amount"
                    type="number"
                    step="0.01"
                    min="0"
                    value={formData.amount}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, amount: e.target.value }))
                    }
                    className="pl-8 font-mono"
                    placeholder="0.00"
                    data-testid="payment-amount-input"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Payment Mode *</Label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setFormData((prev) => ({ ...prev, mode: "cash" }))}
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${
                      formData.mode === "cash"
                        ? "border-brand-600 bg-brand-50 text-brand-700"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                    data-testid="payment-mode-cash"
                  >
                    <Banknote className="h-4 w-4" />
                    <span className="font-medium">Cash</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormData((prev) => ({ ...prev, mode: "bank" }))}
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${
                      formData.mode === "bank"
                        ? "border-brand-600 bg-brand-50 text-brand-700"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                    data-testid="payment-mode-bank"
                  >
                    <Building2 className="h-4 w-4" />
                    <span className="font-medium">Bank</span>
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="date">Date</Label>
                <Input
                  id="date"
                  type="date"
                  value={formData.date}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, date: e.target.value }))
                  }
                  data-testid="payment-date-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="notes">Notes (Optional)</Label>
                <Input
                  id="notes"
                  value={formData.notes}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, notes: e.target.value }))
                  }
                  placeholder="Reference, cheque number, etc."
                  data-testid="payment-notes-input"
                />
              </div>

              <div className="flex justify-end gap-3 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setDialogOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  className="bg-brand-600 hover:bg-brand-700"
                  disabled={saving}
                  data-testid="save-payment-btn"
                >
                  {saving ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    "Record Payment"
                  )}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Payments Table */}
      {loading ? (
        <Card>
          <CardContent className="p-6">
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          </CardContent>
        </Card>
      ) : payments.length > 0 ? (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {payments.map((payment) => (
                  <TableRow key={payment.id} data-testid={`payment-row-${payment.id}`}>
                    <TableCell className="font-medium">{payment.customer_name}</TableCell>
                    <TableCell className="text-slate-500">{formatDate(payment.date)}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1 text-sm capitalize">
                        {payment.mode === "cash" ? (
                          <Banknote className="h-3 w-3 text-emerald-600" />
                        ) : (
                          <Building2 className="h-3 w-3 text-blue-600" />
                        )}
                        {payment.mode}
                      </span>
                    </TableCell>
                    <TableCell className="text-right font-mono font-medium text-emerald-600">
                      +{formatCurrency(payment.amount)}
                    </TableCell>
                    <TableCell className="text-slate-500 text-sm">{payment.notes || "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <CreditCard className="h-12 w-12 text-slate-300 mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-1">No payments yet</h3>
            <p className="text-slate-500 text-sm mb-4">Record your first payment to get started</p>
            <Button
              onClick={() => setDialogOpen(true)}
              className="bg-brand-600 hover:bg-brand-700"
            >
              <Plus className="h-4 w-4 mr-2" />
              Record Payment
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Payments;
