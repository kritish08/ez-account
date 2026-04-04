import React, { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getInvoice, deleteInvoice, downloadInvoicePDF, formatCurrency, formatDate } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
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
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import {
  ArrowLeft,
  Download,
  CreditCard,
  FileText,
  Loader2,
  Trash2,
} from "lucide-react";

const statusBadgeClass = {
  draft: "bg-slate-50 text-slate-700 ring-1 ring-inset ring-slate-500/20",
  unpaid: "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-600/20",
  partially_paid: "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20",
  paid: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20",
};

const InvoiceDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [invoice, setInvoice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  useEffect(() => {
    fetchInvoice();
  }, [id]);

  const fetchInvoice = async () => {
    try {
      const response = await getInvoice(id);
      setInvoice(response.data);
    } catch (error) {
      toast.error("Invoice not found");
      navigate("/invoices");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    setDownloading(true);
    try {
      const blob = await downloadInvoicePDF(id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `Invoice-${invoice.invoice_number}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("PDF downloaded!");
    } catch (error) {
      toast.error("Failed to download PDF");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (!invoice) {
    return null;
  }

  const balanceDue = invoice.total - (invoice.paid_amount || 0);

  return (
    <div className="max-w-3xl mx-auto animate-fade-in" data-testid="invoice-detail-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate("/invoices")}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold font-heading text-slate-900">
                {invoice.invoice_number}
              </h1>
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBadgeClass[invoice.status]
                  }`}
              >
                {invoice.status.replace("_", " ")}
              </span>
            </div>
            <p className="text-slate-500 mt-1">{invoice.customer_name}</p>
          </div>
        </div>

        <div className="flex gap-2">
          {invoice.status !== "paid" && (
            <Link to={`/payments?customer=${invoice.customer_id}`}>
              <Button variant="outline" data-testid="record-payment-for-invoice-btn">
                <CreditCard className="h-4 w-4 mr-2" />
                Record Payment
              </Button>
            </Link>
          )}
          <Link to={`/invoices/${id}/edit`}>
            <Button variant="outline" data-testid="edit-invoice-btn">
              <FileText className="h-4 w-4 mr-2" />
              Edit
            </Button>
          </Link>
          <Button
            onClick={handleDownloadPDF}
            className="bg-brand-600 hover:bg-brand-700"
            disabled={downloading}
            data-testid="download-pdf-btn"
          >
            {downloading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Download className="h-4 w-4 mr-2" />
            )}
            Download PDF
          </Button>
          <Button
            variant="outline"
            className="text-red-600 border-red-200 hover:bg-red-50"
            onClick={() => setDeleteDialogOpen(true)}
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      {/* Delete Alert Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Invoice?</AlertDialogTitle>
            <AlertDialogDescription>
              This will delete invoice {invoice.invoice_number} of {formatCurrency(invoice.total)} and reverse all stock movements, ledger entries, and payment allocations. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                try {
                  await deleteInvoice(id);
                  toast.success("Invoice deleted & effects reversed");
                  navigate("/invoices");
                } catch (error) {
                  toast.error(error.response?.data?.detail || "Failed to delete invoice");
                  setDeleteDialogOpen(false);
                }
              }}
              className="bg-red-600 hover:bg-red-700"
            >Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Invoice Card */}
      <Card>
        <CardContent className="p-8">
          {/* Header */}
          <div className="flex justify-between mb-8 pb-6 border-b border-slate-200">
            <div>
              <h2 className="text-xl font-bold text-slate-900 mb-1">INVOICE</h2>
              <p className="text-sm text-slate-500">#{invoice.invoice_number}</p>
            </div>
            <div className="text-right">
              <p className="text-sm text-slate-500">Date</p>
              <p className="font-medium">{formatDate(invoice.date)}</p>
            </div>
          </div>

          {/* Bill To */}
          <div className="mb-8">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Bill To</p>
            <p className="font-semibold text-slate-900">{invoice.customer_name}</p>
          </div>

          {/* Items Table */}
          <div className="mb-8">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">
                    Description
                  </th>
                  <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">
                    Qty
                  </th>
                  <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">
                    Rate
                  </th>
                  <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">
                    Amount
                  </th>
                </tr>
              </thead>
              <tbody>
                {invoice.items.map((item, index) => (
                  <tr key={index} className="border-b border-slate-100">
                    <td className="py-4 text-slate-900">{item.description}</td>
                    <td className="py-4 text-right font-mono text-slate-600">{item.quantity}</td>
                    <td className="py-4 text-right font-mono text-slate-600">
                      {formatCurrency(item.rate)}
                    </td>
                    <td className="py-4 text-right font-mono font-medium text-slate-900">
                      {formatCurrency(item.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Totals */}
          <div className="flex justify-end">
            <div className="w-64 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">Subtotal</span>
                <span className="font-mono">{formatCurrency(invoice.total)}</span>
              </div>

              {invoice.credit_applied > 0 && (
                <div className="flex justify-between text-sm text-emerald-600">
                  <span>Credit Applied</span>
                  <span className="font-mono">-{formatCurrency(invoice.credit_applied)}</span>
                </div>
              )}

              {invoice.paid_amount > 0 && (
                <div className="flex justify-between text-sm text-emerald-600">
                  <span>Paid</span>
                  <span className="font-mono">{formatCurrency(invoice.paid_amount)}</span>
                </div>
              )}

              <div className="flex justify-between pt-2 border-t border-slate-200">
                <span className="font-semibold">Balance Due</span>
                <span
                  className={`text-lg font-bold font-mono ${balanceDue > 0 ? "text-amber-600" : "text-emerald-600"
                    }`}
                >
                  {formatCurrency(balanceDue)}
                </span>
              </div>
            </div>
          </div>

          {/* Notes */}
          {invoice.notes && (
            <div className="mt-8 pt-6 border-t border-slate-200">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Notes</p>
              <p className="text-sm text-slate-600">{invoice.notes}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default InvoiceDetail;
