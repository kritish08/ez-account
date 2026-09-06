import React, { useState, useEffect, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getInvoices, deleteInvoice, formatCurrency, formatDate } from "../lib/api";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { ResponsiveList, ListCard } from "../components/ResponsiveList";
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
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { Plus, FileText, Eye, MoreHorizontal, Trash2 } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { UIFilters } from "../components/UIFilters";
import { Badge } from "../components/ui/badge";

const statusBadgeVariant = {
  draft: "secondary",
  unpaid: "destructive",
  partially_paid: "warning",
  paid: "success",
};
// specific styling if variants aren't standard in default shadcn
const statusBadgeClass = {
  draft: "bg-slate-100 text-slate-700 hover:bg-slate-100",
  unpaid: "bg-rose-100 text-rose-700 hover:bg-rose-100",
  partially_paid: "bg-amber-100 text-amber-700 hover:bg-amber-100",
  paid: "bg-emerald-100 text-emerald-700 hover:bg-emerald-100",
};

const Invoices = () => {
  const navigate = useNavigate();
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [dateRange, setDateRange] = useState(undefined);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [invoiceToDelete, setInvoiceToDelete] = useState(null);

  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = () => setRefreshKey((k) => k + 1);

  // The search filter used to run twice on every render — once to decide
  // whether to show the table at all, once to map the rows — over the whole
  // invoice list, on every keystroke of an undebounced input. Computed once
  // here and reused by both the table and the mobile card list.
  const visibleInvoices = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return invoices;
    return invoices.filter(
      (inv) =>
        inv.invoice_number?.toLowerCase().includes(q) ||
        inv.customer_name?.toLowerCase().includes(q)
    );
  }, [invoices, search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const status = statusFilter === "all" ? null : statusFilter;
    const startDate = dateRange?.from ? dateRange.from.toISOString().split('T')[0] : null;
    const endDate = dateRange?.to ? dateRange.to.toISOString().split('T')[0] : null;
    getInvoices(status, startDate, endDate)
      .then((res) => { if (!cancelled) setInvoices(res.data); })
      .catch(() => toast.error("Failed to load invoices"))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshKey, statusFilter, dateRange]);

  return (
    <div className="space-y-6 animate-fade-in" data-testid="invoices-page">
      <PageHeader
        title="Invoices"
        description="Create and manage your sales invoices"
        action={
          <Link to="/invoices/new">
            <Button className="bg-brand-600 hover:bg-brand-700 shadow-sm">
              <Plus className="h-4 w-4 mr-2" />
              Create Invoice
            </Button>
          </Link>
        }
      />

      {/* Delete Alert Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Invoice?</AlertDialogTitle>
            <AlertDialogDescription>
              This will delete invoice {invoiceToDelete?.invoice_number} of {invoiceToDelete && formatCurrency(invoiceToDelete.total)} and reverse all stock movements, ledger entries, and payment allocations. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                // Optimistic delete
                setInvoices((prev) => prev.filter((inv) => inv.id !== invoiceToDelete.id));
                setDeleteDialogOpen(false);
                const deleted = invoiceToDelete;
                setInvoiceToDelete(null);
                try {
                  await deleteInvoice(deleted.id);
                  toast.success("Invoice deleted & effects reversed");
                  refresh();
                } catch (error) {
                  toast.error(error.response?.data?.detail || "Failed to delete invoice");
                  refresh();
                }
              }}
              className="bg-red-600 hover:bg-red-700"
            >Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Search & Filter */}
      <UIFilters
        search={search}
        setSearch={setSearch}
        searchPlaceholder="Search invoices..."
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
        statusOptions={[
          { value: "draft", label: "Draft" },
          { value: "unpaid", label: "Unpaid" },
          { value: "partially_paid", label: "Partially Paid" },
          { value: "paid", label: "Paid" },
        ]}
        dateRange={dateRange}
        setDateRange={setDateRange}
        onClear={() => {
          setSearch("");
          setStatusFilter("all");
          setDateRange(undefined);
        }}
      />

      {/* Invoices Table */}
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
      ) : visibleInvoices.length > 0 ? (
        <Card>
          <CardContent className="p-0 max-md:px-4">
            <ResponsiveList
              items={visibleInvoices}
              renderCard={(invoice) => (
                <ListCard
                  primary={invoice.invoice_number}
                  secondary={invoice.customer_name}
                  amount={formatCurrency(invoice.total)}
                  status={
                    <Badge
                      variant={statusBadgeVariant[invoice.status]}
                      className={statusBadgeClass[invoice.status]}
                    >
                      {invoice.status.replace("_", " ")}
                    </Badge>
                  }
                  meta={
                    <>
                      {formatDate(invoice.date)}
                      {invoice.paid_amount > 0 &&
                        ` · ${formatCurrency(invoice.paid_amount)} paid`}
                    </>
                  }
                  onClick={() => navigate(`/invoices/${invoice.id}`)}
                />
              )}
            >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invoice #</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="text-right">Paid</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleInvoices.map((invoice) => (
                  <TableRow
                    key={invoice.id}
                    data-testid={`invoice-row-${invoice.id}`}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={(e) => {
                      // Prevent navigation if clicking on actions menu
                      if (e.target.closest('[role="menuitem"]') || e.target.closest('button')) return;
                      navigate(`/invoices/${invoice.id}`);
                    }}
                  >
                    <TableCell>
                      <span className="font-medium text-brand-600">{invoice.invoice_number}</span>
                    </TableCell>
                    <TableCell>{invoice.customer_name}</TableCell>
                    <TableCell className="text-slate-500">{formatDate(invoice.date)}</TableCell>
                    <TableCell className="text-right font-mono font-medium">
                      {formatCurrency(invoice.total)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-emerald-600">
                      {invoice.paid_amount > 0 ? formatCurrency(invoice.paid_amount) : "-"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusBadgeVariant[invoice.status]} className={statusBadgeClass[invoice.status]}>
                        {invoice.status.replace("_", " ")}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" className="h-8 w-8 p-0" aria-label="Row actions">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuLabel>Actions</DropdownMenuLabel>
                          <DropdownMenuItem onSelect={() => navigate(`/invoices/${invoice.id}`)}>
                            <Eye className="mr-2 h-4 w-4" /> View
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onSelect={() => { setInvoiceToDelete(invoice); setDeleteDialogOpen(true); }}
                            className="text-red-600 focus:text-red-600"
                          >
                            <Trash2 className="mr-2 h-4 w-4" /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </ResponsiveList>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <FileText className="h-12 w-12 text-slate-300 mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-1">No invoices yet</h3>
            <p className="text-slate-500 text-sm mb-4">Create your first invoice to get started</p>
            <Link to="/invoices/new">
              <Button className="bg-brand-600 hover:bg-brand-700">
                <Plus className="h-4 w-4 mr-2" />
                Create Invoice
              </Button>
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Invoices;
