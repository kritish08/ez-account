import React, { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { getPayments, getCustomers, getCustomer, createPayment, deletePayment, getInvoice, getCreditNotes, formatCurrency, formatDate } from "../lib/api";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
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
import { Checkbox } from "../components/ui/checkbox";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog";
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";
import { Plus, CreditCard, Loader2, Banknote, Building2, MoreHorizontal, Trash2 } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { UIFilters } from "../components/UIFilters";

const Payments = () => {
  const [searchParams] = useSearchParams();
  const preselectedCustomer = searchParams.get("customer");
  const preselectedInvoice = searchParams.get("invoice");

  const [payments, setPayments] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(!!preselectedCustomer);
  const [saving, setSaving] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [paymentToDelete, setPaymentToDelete] = useState(null);
  const [search, setSearch] = useState("");
  const [modeFilter, setModeFilter] = useState("all");
  const [dateRange, setDateRange] = useState(undefined);
  const [customerCreditNotes, setCustomerCreditNotes] = useState([]); // CNs for selected customer
  const [applyCN, setApplyCN] = useState(false);  // whether to apply a CN
  const [selectedCNId, setSelectedCNId] = useState("");  // which CN to apply
  
  const [customerAdvancePayments, setCustomerAdvancePayments] = useState([]); // Advances for selected customer
  const [applyAdvance, setApplyAdvance] = useState(false);  // whether to apply an advance
  const [selectedAdvanceId, setSelectedAdvanceId] = useState("");  // which advance to apply

  const [formData, setFormData] = useState({
    customer_id: preselectedCustomer || "",
    invoice_id: preselectedInvoice || "",
    amount: "",
    mode: "cash",
    date: new Date().toISOString().split("T")[0],
    notes: "",
    use_credit: false,
  });

  useEffect(() => {
    fetchData();
  }, [dateRange]); // Added dateRange dep

  const fetchData = async () => {
    try {
      setLoading(true);
      const startDate = dateRange?.from ? dateRange.from.toISOString().split('T')[0] : null;
      const endDate = dateRange?.to ? dateRange.to.toISOString().split('T')[0] : null;

      const [paymentsRes, customersRes] = await Promise.all([
        getPayments(startDate, endDate),
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

  // Fetch credit notes and advance payments when customer changes
  useEffect(() => {
    if (formData.customer_id) {
      Promise.all([
        getCreditNotes(),
        getCustomer(formData.customer_id)
      ]).then(([cnRes, custRes]) => {
          const cns = (cnRes.data || []).filter(
            cn => cn.customer_id === formData.customer_id && cn.total > 0
          );
          setCustomerCreditNotes(cns);
          setApplyCN(false);
          setSelectedCNId("");
          
          const advs = custRes.data?.advance_payments || [];
          setCustomerAdvancePayments(advs);
          setApplyAdvance(false);
          setSelectedAdvanceId("");
      }).catch(err => {
          setCustomerCreditNotes([]);
          setCustomerAdvancePayments([]);
      });
    } else {
      setCustomerCreditNotes([]);
      setCustomerAdvancePayments([]);
    }
  }, [formData.customer_id]);

  useEffect(() => {
    if (preselectedInvoice) {
      const fetchInv = async () => {
        try {
          const res = await getInvoice(preselectedInvoice);
          const inv = res.data;
          const due = inv.total - (inv.paid_amount || 0);
          setFormData(prev => ({
            ...prev,
            amount: due > 0 ? due.toString() : "",
            notes: `Payment for Invoice ${inv.invoice_number}`
          }));
        } catch (e) {
          console.error("Failed to fetch invoice", e);
        }
      };
      fetchInv();
    }
  }, [preselectedInvoice]);

  const handleDeleteClick = (payment) => {
    setPaymentToDelete(payment);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    if (!paymentToDelete) return;
    try {
      await deletePayment(paymentToDelete.id);
      toast.success("Payment deleted (voided) successfully");
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete payment");
    } finally {
      setDeleteDialogOpen(false);
      setPaymentToDelete(null);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.customer_id) {
      toast.error("Please select a customer");
      return;
    }

    if ((!formData.amount || parseFloat(formData.amount) <= 0) && !applyCN && !applyAdvance) {
      toast.error("Please enter a valid amount or apply credit/advance");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        ...formData,
        amount: parseFloat(formData.amount) || 0,
        credit_note_id: (applyCN && selectedCNId) ? selectedCNId : null,
        advance_payment_id: (applyAdvance && selectedAdvanceId) ? selectedAdvanceId : null,
      };
      const response = await createPayment(payload);

      let message = "Payment recorded successfully!";
      if (response.data.credit_note_applied > 0) {
        message += ` Credit Note of ${formatCurrency(response.data.credit_note_applied)} applied.`;
      }
      if (response.data.advance_payment_applied > 0) {
        message += ` Advance Credit of ${formatCurrency(response.data.advance_payment_applied)} applied.`;
      }
      if (response.data.excess_as_credit > 0) {
        message += ` ${formatCurrency(response.data.excess_as_credit)} added as Credit Note.`;
      }
      if (response.data.excess_as_advance > 0) {
        message += ` ${formatCurrency(response.data.excess_as_advance)} added as Advance Credit.`;
      }
      toast.success(message);

      setDialogOpen(false);
      setFormData({
        customer_id: "",
        invoice_id: "",
        amount: "",
        mode: "cash",
        date: new Date().toISOString().split("T")[0],
        notes: "",
        use_credit: false,
      });
      setApplyCN(false);
      setSelectedCNId("");
      setCustomerCreditNotes([]);
      setApplyAdvance(false);
      setSelectedAdvanceId("");
      setCustomerAdvancePayments([]);
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
      <div className="space-y-6 animate-fade-in" data-testid="payments-page">
        <PageHeader
          title="Payments"
          description="Record and track customer payments"
          action={
            <Button onClick={() => setDialogOpen(true)} className="bg-brand-600 hover:bg-brand-700" data-testid="record-payment-btn">
              <Plus className="h-4 w-4 mr-2" />
              Record Payment
            </Button>
          }
        />

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
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

              {/* Credit Notes — apply existing CN to this payment */}
              {customerCreditNotes.length > 0 && formData.invoice_id && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 space-y-2">
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="apply_cn"
                      checked={applyCN}
                      onCheckedChange={(checked) => {
                        setApplyCN(checked);
                        if (!checked) setSelectedCNId("");
                        else if (customerCreditNotes.length === 1) setSelectedCNId(customerCreditNotes[0].id);
                      }}
                    />
                    <Label htmlFor="apply_cn" className="cursor-pointer font-medium text-emerald-700">
                      Apply Credit Note balance
                    </Label>
                  </div>
                  {applyCN && (
                    <Select value={selectedCNId} onValueChange={setSelectedCNId}>
                      <SelectTrigger className="bg-white">
                        <SelectValue placeholder="Select credit note" />
                      </SelectTrigger>
                      <SelectContent>
                        {customerCreditNotes.map(cn => (
                          <SelectItem key={cn.id} value={cn.id}>
                            CN #{cn.credit_note_number} — {formatCurrency(cn.total)} available
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              )}

              {/* Advance Payments — apply existing advance to this payment */}
              {customerAdvancePayments.length > 0 && formData.invoice_id && (
                <div className="rounded-lg border border-purple-200 bg-purple-50 p-3 space-y-2">
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="apply_advance"
                      checked={applyAdvance}
                      onCheckedChange={(checked) => {
                        setApplyAdvance(checked);
                        if (!checked) setSelectedAdvanceId("");
                        else if (customerAdvancePayments.length === 1) setSelectedAdvanceId(customerAdvancePayments[0].id);
                      }}
                    />
                    <Label htmlFor="apply_advance" className="cursor-pointer font-medium text-purple-700">
                      Apply Advance Balance
                    </Label>
                  </div>
                  {applyAdvance && (
                    <Select value={selectedAdvanceId} onValueChange={setSelectedAdvanceId}>
                      <SelectTrigger className="bg-white">
                        <SelectValue placeholder="Select advance credit" />
                      </SelectTrigger>
                      <SelectContent>
                        {customerAdvancePayments.map(adv => (
                          <SelectItem key={adv.id} value={adv.id}>
                            Advance from Payment ...{adv.payment_id.slice(-8)} — {formatCurrency(adv.remaining_amount)} available
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              )}

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
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${formData.mode === "cash"
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
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${formData.mode === "bank"
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

      {/* Delete Alert Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete (void) the payment of {paymentToDelete && formatCurrency(paymentToDelete.amount)} for {paymentToDelete?.customer_name}.
              This action cannot be undone and will reverse the ledger entries.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-red-600 hover:bg-red-700">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Search & Filter */}
      <UIFilters
        search={search}
        setSearch={setSearch}
        searchPlaceholder="Search payments..."
        statusFilter={modeFilter}
        setStatusFilter={setModeFilter}
        statusLabel="All Modes"
        statusOptions={[
          { value: "cash", label: "Cash" },
          { value: "bank", label: "Bank" }
        ]}
        dateRange={dateRange}
        setDateRange={setDateRange}
        onClear={() => {
          setSearch("");
          setModeFilter("all");
          setDateRange(undefined);
        }}
      />

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
      ) : (() => {
        const filtered = payments.filter((p) => {
          const q = search.toLowerCase();
          const matchSearch = !q || p.customer_name?.toLowerCase().includes(q) || p.notes?.toLowerCase().includes(q);
          const matchMode = modeFilter === "all" || p.mode === modeFilter;
          return matchSearch && matchMode;
        });
        return filtered.length > 0 ? (
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
                    <TableHead className="w-[80px]"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((payment) => (
                    <TableRow key={payment.id} data-testid={`payment-row-${payment.id}`}>
                      <TableCell className="font-medium">{payment.customer_name}</TableCell>
                      <TableCell className="text-slate-500">{formatDate(payment.date)}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="font-normal gap-1">
                          {payment.mode === "cash" ? (
                            <Banknote className="h-3 w-3 text-emerald-600" />
                          ) : (
                            <Building2 className="h-3 w-3 text-blue-600" />
                          )}
                          <span className="capitalize">{payment.mode}</span>
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono font-medium text-emerald-600">
                        +{formatCurrency(payment.amount)}
                      </TableCell>
                      <TableCell className="text-slate-500 text-sm">{payment.notes || "-"}</TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" className="h-8 w-8 p-0" data-testid={`payment-actions-${payment.id}`}>
                              <span className="sr-only">Open menu</span>
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => handleDeleteClick(payment)}
                              className="text-red-600 focus:text-red-600"
                              data-testid={`delete-payment-${payment.id}`}
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              Delete (Void)
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
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
              <h3 className="text-lg font-medium text-slate-900 mb-1">No payments found</h3>
              <p className="text-slate-500 text-sm mb-4">{search || modeFilter !== 'all' ? 'Try adjusting your search or filters' : 'Record your first payment to get started'}</p>
              <Button
                onClick={() => setDialogOpen(true)}
                className="bg-brand-600 hover:bg-brand-700"
              >
                <Plus className="h-4 w-4 mr-2" />
                Record Payment
              </Button>
            </CardContent>
          </Card>
        );
      })()}
    </div>
  );
};

export default Payments;
