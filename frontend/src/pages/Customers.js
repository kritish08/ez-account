import React, { useState, useEffect, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getCustomers, createCustomer, updateCustomer, deleteCustomer, formatCurrency } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent } from "../components/ui/card";
import { ResponsiveList, ListCard } from "../components/ResponsiveList";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
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
import { Plus, Search, Users, Phone, Loader2, ChevronRight, MoreHorizontal, Pencil, Trash2 } from "lucide-react";

const EMPTY_FORM = {
  name: "",
  phone: "",
  address: "",
  gstin: "",
  opening_balance: 0,
  balance_type: "debit",
};

const Customers = () => {
  const navigate = useNavigate();
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [customerToDelete, setCustomerToDelete] = useState(null);
  const [formData, setFormData] = useState(EMPTY_FORM);

  // ─── Refresh Key ─────────────────────────────────────────────────────────────
  // Incrementing this triggers the useEffect below, which re-fetches fresh data.
  // React guarantees the effect re-runs whenever this value changes.
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = () => setRefreshKey((k) => k + 1);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getCustomers()
      .then((res) => {
        if (!cancelled) setCustomers(res.data);
      })
      .catch(() => toast.error("Failed to load customers"))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [refreshKey]);
  // ─────────────────────────────────────────────────────────────────────────────

  const handleChange = (e) => {
    const { name, value, type } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "number" ? parseFloat(value) || 0 : value,
    }));
  };

  const resetForm = () => {
    setFormData(EMPTY_FORM);
    setEditingCustomer(null);
  };

  const openAddDialog = () => {
    resetForm();
    setDialogOpen(true);
  };

  const handleEdit = (customer) => {
    setEditingCustomer(customer);
    setFormData({
      name: customer.name,
      phone: customer.phone || "",
      address: customer.address || "",
      gstin: customer.gstin || "",
      opening_balance: 0,
      balance_type: "debit",
    });
    setDialogOpen(true);
  };

  const handleDeleteClick = (customer) => {
    setCustomerToDelete(customer);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    if (!customerToDelete) return;
    // Optimistic: immediately remove from UI
    setCustomers((prev) => prev.filter((c) => c.id !== customerToDelete.id));
    setDeleteDialogOpen(false);
    const deleted = customerToDelete;
    setCustomerToDelete(null);
    try {
      await deleteCustomer(deleted.id);
      toast.success("Customer deleted successfully");
      refresh(); // Trigger re-fetch to sync with server
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete customer");
      refresh(); // Re-fetch to restore if failed
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name) {
      toast.error("Customer name is required");
      return;
    }

    setSaving(true);
    // Close dialog immediately for snappy UX
    setDialogOpen(false);
    const isEditing = !!editingCustomer;
    const editTarget = editingCustomer;
    resetForm();

    try {
      if (isEditing) {
        // Optimistic update
        setCustomers((prev) =>
          prev.map((c) => c.id === editTarget.id ? { ...c, ...formData } : c)
        );
        await updateCustomer(editTarget.id, formData);
        toast.success("Customer updated successfully");
      } else {
        await createCustomer(formData);
        toast.success("Customer added successfully");
      }
      refresh(); // Always re-fetch to get server-accurate data
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save customer");
      refresh(); // Re-fetch to restore consistent state
    } finally {
      setSaving(false);
    }
  };

  const filteredCustomers = customers
    .filter(
      (c) =>
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.phone?.includes(search)
    )
    .sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className="space-y-6 animate-fade-in" data-testid="customers-page">
      {/* --- Edit / Add Dialog --- */}
      <Dialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) resetForm();
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingCustomer ? "Edit Customer" : "Add New Customer"}</DialogTitle>
            <DialogDescription>
              {editingCustomer ? "Update customer details below" : "Enter customer details below"}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 mt-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                name="name"
                value={formData.name}
                onChange={handleChange}
                placeholder="Customer name"
                data-testid="customer-name-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="phone">Phone</Label>
              <Input
                id="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                name="phone"
                value={formData.phone}
                onChange={handleChange}
                placeholder="+91 98765 43210"
                data-testid="customer-phone-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="address">Address</Label>
              <Input
                id="address"
                name="address"
                value={formData.address}
                onChange={handleChange}
                placeholder="Customer address"
                data-testid="customer-address-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="gstin">GSTIN (Optional)</Label>
              <Input
                id="gstin"
                autoCapitalize="characters"
                autoCorrect="off"
                spellCheck={false}
                name="gstin"
                value={formData.gstin}
                onChange={handleChange}
                placeholder="Tax ID"
                data-testid="customer-gstin-input"
              />
            </div>

            {!editingCustomer && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="opening_balance">Opening Balance</Label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono">₹</span>
                    <Input
                      id="opening_balance"
                      name="opening_balance"
                      type="number" inputMode="decimal"
                      step="0.01"
                      value={formData.opening_balance}
                      onChange={handleChange}
                      className="pl-8 font-mono"
                      data-testid="customer-balance-input"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="balance_type">Balance Type</Label>
                  <Select
                    value={formData.balance_type}
                    onValueChange={(value) =>
                      setFormData((prev) => ({ ...prev, balance_type: value }))
                    }
                  >
                    <SelectTrigger data-testid="customer-balance-type-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="debit">They owe us</SelectItem>
                      <SelectItem value="credit">We owe them</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

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
                data-testid="save-customer-btn"
              >
                {saving ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {editingCustomer ? "Updating..." : "Saving..."}
                  </>
                ) : (
                  editingCustomer ? "Update Customer" : "Add Customer"
                )}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* --- Delete Confirmation --- */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Customer?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete <strong>{customerToDelete?.name}</strong>. This action cannot be undone.
              {customerToDelete && (customerToDelete.outstanding > 0 || customerToDelete.credit > 0) && (
                <div className="mt-2 text-amber-600 font-medium bg-amber-50 p-2 rounded border border-amber-200">
                  Warning: This customer has an outstanding balance of {formatCurrency(customerToDelete.outstanding)}.
                </div>
              )}
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

      {/* --- Page Header --- */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">Customers</h1>
          <p className="text-slate-500 mt-1">Manage your customers and their balances</p>
        </div>
        <Button
          className="bg-brand-600 hover:bg-brand-700"
          onClick={openAddDialog}
          data-testid="add-customer-btn"
        >
          <Plus className="h-4 w-4 mr-2" />
          Add Customer
        </Button>
      </div>

      {/* --- Search --- */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <Input
          placeholder="Search customers..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10"
          data-testid="customer-search-input"
        />
      </div>

      {/* --- Customers Table --- */}
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
      ) : filteredCustomers.length > 0 ? (
        <Card>
          <CardContent className="p-0 max-md:px-4">
            <ResponsiveList
              items={filteredCustomers}
              renderCard={(customer) => (
                <ListCard
                  primary={customer.name}
                  secondary={customer.phone || customer.address || "—"}
                  amount={
                    customer.outstanding > 0
                      ? formatCurrency(customer.outstanding)
                      : customer.credit_balance > 0
                        ? formatCurrency(customer.credit_balance)
                        : null
                  }
                  amountClassName={
                    customer.outstanding > 0 ? "text-amber-600" : "text-emerald-600"
                  }
                  meta={
                    customer.outstanding > 0
                      ? "Outstanding"
                      : customer.credit_balance > 0
                        ? "In credit"
                        : "Settled"
                  }
                  onClick={() => navigate(`/customers/${customer.id}`)}
                />
              )}
            >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead className="text-right">Outstanding</TableHead>
                  <TableHead className="text-right">Credit</TableHead>
                  <TableHead className="w-[60px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredCustomers.map((customer) => (
                  <TableRow
                    key={customer.id}
                    className="hover:bg-slate-50"
                    data-testid={`customer-row-${customer.id}`}
                  >
                    <TableCell>
                      <Link to={`/customers/${customer.id}`} className="flex items-center gap-3 group">
                        <div className="w-9 h-9 rounded-full bg-brand-50 flex items-center justify-center shrink-0">
                          <span className="text-sm font-medium text-brand-700">
                            {customer.name.charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <div>
                          <p className="font-medium text-slate-900 group-hover:text-brand-600 transition-colors">
                            {customer.name}
                          </p>
                          {customer.address && (
                            <p className="text-sm text-slate-500 truncate max-w-[200px]">
                              {customer.address}
                            </p>
                          )}
                        </div>
                      </Link>
                    </TableCell>
                    <TableCell>
                      {customer.phone && (
                        <div className="flex items-center gap-1 text-slate-600">
                          <Phone className="h-3 w-3" />
                          <span className="text-sm">{customer.phone}</span>
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {customer.outstanding > 0 ? (
                        <span className="font-mono text-amber-600 font-medium">
                          {formatCurrency(customer.outstanding)}
                        </span>
                      ) : (
                        <span className="text-slate-400 text-sm">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {customer.credit > 0 ? (
                        <span className="font-mono text-emerald-600 font-medium">
                          {formatCurrency(customer.credit)}
                        </span>
                      ) : (
                        <span className="text-slate-400 text-sm">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            className="h-8 w-8 p-0"
                            data-testid={`customer-actions-${customer.id}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <span className="sr-only">Open menu</span>
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuLabel>Actions</DropdownMenuLabel>
                          <DropdownMenuItem
                            data-testid={`edit-customer-${customer.id}`}
                            onSelect={() => handleEdit(customer)}
                          >
                            <Pencil className="mr-2 h-4 w-4" />
                            Edit
                          </DropdownMenuItem>
                          <DropdownMenuItem asChild>
                            <Link to={`/customers/${customer.id}`} className="flex items-center w-full cursor-default">
                              <ChevronRight className="mr-2 h-4 w-4" />
                              View Details
                            </Link>
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-red-600 focus:text-red-600"
                            data-testid={`delete-customer-${customer.id}`}
                            onSelect={() => handleDeleteClick(customer)}
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            Delete
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
            <Users className="h-12 w-12 text-slate-300 mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-1">No customers yet</h3>
            <p className="text-slate-500 text-sm mb-4">Add your first customer to get started</p>
            <Button
              onClick={openAddDialog}
              className="bg-brand-600 hover:bg-brand-700"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Customer
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Customers;
