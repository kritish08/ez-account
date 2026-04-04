import React, { useState, useEffect } from "react";
import { getSuppliers, createSupplier, updateSupplier, deleteSupplier, createSupplierPayment, formatCurrency } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent } from "../components/ui/card";
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
import { Plus, Search, Truck, Loader2, Phone, CreditCard, Banknote, Building2, MoreHorizontal, Pencil, Trash2 } from "lucide-react";

const Suppliers = () => {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [selectedSupplier, setSelectedSupplier] = useState(null);
  const [saving, setSaving] = useState(false);
  const [editingSupplier, setEditingSupplier] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [supplierToDelete, setSupplierToDelete] = useState(null);

  const [formData, setFormData] = useState({
    name: "",
    phone: "",
    address: "",
    gstin: "",
    opening_balance: "",
  });
  const [paymentData, setPaymentData] = useState({
    amount: "",
    mode: "cash",
    notes: "",
  });

  useEffect(() => {
    fetchSuppliers();
  }, []);

  const fetchSuppliers = async () => {
    try {
      const response = await getSuppliers();
      setSuppliers(response.data);
    } catch (error) {
      toast.error("Failed to load suppliers");
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({ name: "", phone: "", address: "", gstin: "", opening_balance: "" });
    setEditingSupplier(null);
  }

  const handleEdit = (supplier) => {
    setEditingSupplier(supplier);
    setFormData({
      name: supplier.name,
      phone: supplier.phone || "",
      address: supplier.address || "",
      gstin: supplier.gstin || "",
      opening_balance: "", // Not editable
    });
    setDialogOpen(true);
  };

  const handleDeleteClick = (supplier) => {
    setSupplierToDelete(supplier);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    if (!supplierToDelete) return;
    try {
      await deleteSupplier(supplierToDelete.id);
      toast.success("Supplier deleted successfully");
      fetchSuppliers();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete supplier");
    } finally {
      setDeleteDialogOpen(false);
      setSupplierToDelete(null);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name) {
      toast.error("Supplier name is required");
      return;
    }

    setSaving(true);
    try {
      if (editingSupplier) {
        await updateSupplier(editingSupplier.id, formData);
        toast.success("Supplier updated successfully");
      } else {
        await createSupplier({
          ...formData,
          opening_balance: parseFloat(formData.opening_balance) || 0,
        });
        toast.success("Supplier added successfully");
      }
      setDialogOpen(false);
      resetForm();
      fetchSuppliers();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save supplier");
    } finally {
      setSaving(false);
    }
  };

  const handlePayment = async (e) => {
    e.preventDefault();
    if (!paymentData.amount || parseFloat(paymentData.amount) <= 0) {
      toast.error("Please enter a valid amount");
      return;
    }

    setSaving(true);
    try {
      await createSupplierPayment({
        supplier_id: selectedSupplier.id,
        amount: parseFloat(paymentData.amount),
        mode: paymentData.mode,
        notes: paymentData.notes,
      });
      toast.success("Payment recorded successfully");
      setPaymentDialogOpen(false);
      setPaymentData({ amount: "", mode: "cash", notes: "" });
      setSelectedSupplier(null);
      fetchSuppliers();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to record payment");
    } finally {
      setSaving(false);
    }
  };

  const openPaymentDialog = (supplier) => {
    setSelectedSupplier(supplier);
    setPaymentDialogOpen(true);
  };

  const filteredSuppliers = suppliers.filter(
    (s) => s.name.toLowerCase().includes(search.toLowerCase()) || s.phone?.includes(search)
  );

  return (
    <div className="space-y-6 animate-fade-in" data-testid="suppliers-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">Suppliers</h1>
          <p className="text-slate-500 mt-1">Manage your suppliers and payables</p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) resetForm();
        }}>
          <DialogTrigger asChild>
            <Button className="bg-brand-600 hover:bg-brand-700" data-testid="add-supplier-btn">
              <Plus className="h-4 w-4 mr-2" />
              Add Supplier
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{editingSupplier ? "Edit Supplier" : "Add New Supplier"}</DialogTitle>
              <DialogDescription>{editingSupplier ? "Update supplier details below" : "Enter supplier details below"}</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name *</Label>
                <Input id="name" value={formData.name} onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))} placeholder="Supplier name" data-testid="supplier-name-input" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone">Phone</Label>
                <Input id="phone" value={formData.phone} onChange={(e) => setFormData((prev) => ({ ...prev, phone: e.target.value }))} placeholder="+91 98765 43210" data-testid="supplier-phone-input" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="address">Address</Label>
                <Input id="address" value={formData.address} onChange={(e) => setFormData((prev) => ({ ...prev, address: e.target.value }))} placeholder="Supplier address" data-testid="supplier-address-input" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="gstin">GSTIN (Optional)</Label>
                <Input id="gstin" value={formData.gstin} onChange={(e) => setFormData((prev) => ({ ...prev, gstin: e.target.value }))} placeholder="Tax ID" data-testid="supplier-gstin-input" />
              </div>

              {!editingSupplier && (
                <div className="space-y-2">
                  <Label htmlFor="opening_balance">Opening Payable</Label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono">₹</span>
                    <Input id="opening_balance" type="number" step="0.01" min="0" value={formData.opening_balance} onChange={(e) => setFormData((prev) => ({ ...prev, opening_balance: e.target.value }))} className="pl-8 font-mono" data-testid="supplier-balance-input" />
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4">
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button type="submit" className="bg-brand-600 hover:bg-brand-700" disabled={saving} data-testid="save-supplier-btn">
                  {saving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />{editingSupplier ? "Updating..." : "Saving..."}</> : (editingSupplier ? "Update Supplier" : "Add Supplier")}
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
              This will permanently delete the supplier "{supplierToDelete?.name}".
              This action cannot be undone.
              {supplierToDelete && supplierToDelete.payable > 0 && (
                <div className="mt-2 text-amber-600 font-medium bg-amber-50 p-2 rounded border border-amber-200">
                  Warning: You owe this supplier {formatCurrency(supplierToDelete.payable)}.
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

      {/* Payment Dialog */}
      <Dialog open={paymentDialogOpen} onOpenChange={setPaymentDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Pay Supplier</DialogTitle>
            <DialogDescription>{selectedSupplier?.name} - Payable: {formatCurrency(selectedSupplier?.payable)}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handlePayment} className="space-y-4 mt-4">
            <div className="space-y-2">
              <Label htmlFor="payment_amount">Amount *</Label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono">₹</span>
                <Input id="payment_amount" type="number" step="0.01" min="0" value={paymentData.amount} onChange={(e) => setPaymentData((prev) => ({ ...prev, amount: e.target.value }))} className="pl-8 font-mono" data-testid="supplier-payment-amount-input" />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Payment Mode *</Label>
              <div className="grid grid-cols-2 gap-3">
                <button type="button" onClick={() => setPaymentData((prev) => ({ ...prev, mode: "cash" }))} className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${paymentData.mode === "cash" ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-200 hover:border-slate-300"}`} data-testid="supplier-payment-mode-cash">
                  <Banknote className="h-4 w-4" /><span className="font-medium">Cash</span>
                </button>
                <button type="button" onClick={() => setPaymentData((prev) => ({ ...prev, mode: "bank" }))} className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${paymentData.mode === "bank" ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-200 hover:border-slate-300"}`} data-testid="supplier-payment-mode-bank">
                  <Building2 className="h-4 w-4" /><span className="font-medium">Bank</span>
                </button>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="payment_notes">Notes (Optional)</Label>
              <Input id="payment_notes" value={paymentData.notes} onChange={(e) => setPaymentData((prev) => ({ ...prev, notes: e.target.value }))} placeholder="Reference number, etc." data-testid="supplier-payment-notes-input" />
            </div>
            <div className="flex justify-end gap-3 pt-4">
              <Button type="button" variant="outline" onClick={() => setPaymentDialogOpen(false)}>Cancel</Button>
              <Button type="submit" className="bg-brand-600 hover:bg-brand-700" disabled={saving} data-testid="save-supplier-payment-btn">
                {saving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</> : "Record Payment"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <Input placeholder="Search suppliers..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-10" data-testid="supplier-search-input" />
      </div>

      {/* Suppliers Table */}
      {loading ? (
        <Card><CardContent className="p-6"><div className="space-y-4">{[...Array(5)].map((_, i) => (<Skeleton key={i} className="h-12 w-full" />))}</div></CardContent></Card>
      ) : filteredSuppliers.length > 0 ? (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Supplier</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead className="text-right">Payable</TableHead>
                  <TableHead className="text-right"></TableHead>
                  <TableHead className="w-[80px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredSuppliers.map((supplier) => (
                  <TableRow
                    key={supplier.id}
                    data-testid={`supplier-row-${supplier.id}`}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={(e) => {
                      if (e.target.closest('button')) return;
                      handleEdit(supplier);
                    }}
                  >
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-orange-50 flex items-center justify-center">
                          <span className="text-sm font-medium text-orange-700">{supplier.name.charAt(0).toUpperCase()}</span>
                        </div>
                        <div>
                          <p className="font-medium text-slate-900">{supplier.name}</p>
                          {supplier.address && <p className="text-sm text-slate-500 truncate max-w-[200px]">{supplier.address}</p>}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>{supplier.phone && <div className="flex items-center gap-1 text-slate-600"><Phone className="h-3 w-3" /><span className="text-sm">{supplier.phone}</span></div>}</TableCell>
                    <TableCell className="text-right">
                      {supplier.payable > 0 ? (
                        <span className="font-mono text-rose-600 font-medium">{formatCurrency(supplier.payable)}</span>
                      ) : (
                        <span className="text-slate-400 text-sm">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {supplier.payable > 0 && (
                        <Button variant="outline" size="sm" onClick={() => openPaymentDialog(supplier)} data-testid={`pay-supplier-${supplier.id}`}>
                          <CreditCard className="h-4 w-4 mr-1" />Pay
                        </Button>
                      )}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" className="h-8 w-8 p-0" data-testid={`supplier-actions-${supplier.id}`}>
                            <span className="sr-only">Open menu</span>
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuLabel>Actions</DropdownMenuLabel>
                          <DropdownMenuItem onClick={() => handleEdit(supplier)} data-testid={`edit-supplier-${supplier.id}`}>
                            <Pencil className="mr-2 h-4 w-4" />
                            Edit
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => handleDeleteClick(supplier)}
                            className="text-red-600 focus:text-red-600"
                            data-testid={`delete-supplier-${supplier.id}`}
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
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Truck className="h-12 w-12 text-slate-300 mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-1">No suppliers yet</h3>
            <p className="text-slate-500 text-sm mb-4">Add your first supplier to get started</p>
            <Button onClick={() => setDialogOpen(true)} className="bg-brand-600 hover:bg-brand-700"><Plus className="h-4 w-4 mr-2" />Add Supplier</Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Suppliers;
