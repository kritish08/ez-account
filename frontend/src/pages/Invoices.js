import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { getInvoices, formatCurrency, formatDate } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
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
import { Plus, FileText, ChevronRight, Filter } from "lucide-react";

const statusBadgeClass = {
  unpaid: "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-600/20",
  partially_paid: "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20",
  paid: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20",
};

const Invoices = () => {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    fetchInvoices();
  }, [statusFilter]);

  const fetchInvoices = async () => {
    try {
      const status = statusFilter === "all" ? null : statusFilter;
      const response = await getInvoices(status);
      setInvoices(response.data);
    } catch (error) {
      toast.error("Failed to load invoices");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="invoices-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">Invoices</h1>
          <p className="text-slate-500 mt-1">Create and manage your sales invoices</p>
        </div>

        <Link to="/invoices/new">
          <Button className="bg-brand-600 hover:bg-brand-700" data-testid="create-invoice-btn">
            <Plus className="h-4 w-4 mr-2" />
            Create Invoice
          </Button>
        </Link>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-slate-400" />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px]" data-testid="invoice-status-filter">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Invoices</SelectItem>
            <SelectItem value="unpaid">Unpaid</SelectItem>
            <SelectItem value="partially_paid">Partially Paid</SelectItem>
            <SelectItem value="paid">Paid</SelectItem>
          </SelectContent>
        </Select>
      </div>

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
      ) : invoices.length > 0 ? (
        <Card>
          <CardContent className="p-0">
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
                {invoices.map((invoice) => (
                  <TableRow key={invoice.id} data-testid={`invoice-row-${invoice.id}`}>
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
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          statusBadgeClass[invoice.status]
                        }`}
                      >
                        {invoice.status.replace("_", " ")}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Link to={`/invoices/${invoice.id}`}>
                        <Button variant="ghost" size="sm">
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </Link>
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
