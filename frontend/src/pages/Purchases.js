import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getPurchases, getProducts, getSuppliers, createPurchase, updatePurchase, deletePurchase, formatCurrency, formatDate } from "../lib/api";
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
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";
import { Plus, ShoppingCart, Loader2, Trash2, Banknote, Building2, Clock, MoreHorizontal, Pencil } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { UIFilters } from "../components/UIFilters";

const Purchases = () => {
  const navigate = useNavigate();
  const [purchases, setPurchases] = useState([]);
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingPurchase, setEditingPurchase] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [purchaseToDelete, setPurchaseToDelete] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dateRange, setDateRange] = useState(undefined);

  const [formData, setFormData] = useState({
    supplier_id: "",
    payment_status: "unpaid",
    date: new Date().toISOString().split("T")[0],
    notes: "",
    items: [{ product_id: "", quantity: "", cost_price: "" }],
  });

  useEffect(() => {
    fetchData();
  }, [dateRange]); // Added dateRange dep

  const fetchData = async () => {
    try {
      setLoading(true);
      const startDate = dateRange?.from ? dateRange.from.toISOString().split('T')[0] : null;
      const endDate = dateRange?.to ? dateRange.to.toISOString().split('T')[0] : null;

      const [purchasesRes, productsRes, suppliersRes] = await Promise.all([
        getPurchases(startDate, endDate),
        getProducts(),
        getSuppliers(),
      ]);
      setPurchases(purchasesRes.data);
      setProducts(productsRes.data);
      setSuppliers(suppliersRes.data);
    } catch (error) {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({
      supplier_id: "",
      payment_status: "unpaid",
      date: new Date().toISOString().split("T")[0],
      notes: "",
      items: [{ product_id: "", quantity: "", cost_price: "" }],
    });
    setEditingPurchase(null);
  };

  const handleEdit = (purchase) => {
    setEditingPurchase(purchase);
    // Transform purchase items for form
    const items = purchase.items.map(item => ({
      product_id: item.product_id,
      quantity: item.quantity,
      cost_price: item.cost_price,
    }));

    setFormData({
      supplier_id: purchase.supplier_id || "no_supplier",
      payment_status: purchase.payment_status,
      date: purchase.date.split("T")[0],
      notes: purchase.notes || "",
      items: items.length > 0 ? items : [{ product_id: "", quantity: "", cost_price: "" }],
    });
    setDialogOpen(true);
  };

  const handleDeleteClick = (purchase) => {
    setPurchaseToDelete(purchase);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    if (!purchaseToDelete) return;
    try {
      await deletePurchase(purchaseToDelete.id);
      toast.success("Purchase deleted successfully");
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete purchase");
    } finally {
      setDeleteDialogOpen(false);
      setPurchaseToDelete(null);
    }
  };

  const handleAddItem = () => {
    setFormData((prev) => ({
      ...prev,
      items: [...prev.items, { product_id: "", quantity: "", cost_price: "" }],
    }));
  };

  const handleRemoveItem = (index) => {
    if (formData.items.length === 1) return;
    setFormData((prev) => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== index),
    }));
  };

  const handleItemChange = (index, field, value) => {
    setFormData((prev) => ({
      ...prev,
      items: prev.items.map((item, i) => {
        if (i !== index) return item;
        const updatedItem = { ...item, [field]: value };

        // Auto-fill cost price when product is selected
        if (field === "product_id") {
          const product = products.find((p) => p.id === value);
          if (product) {
            updatedItem.cost_price = product.cost_price.toString();
          }
        }
        return updatedItem;
      }),
    }));
  };

  const calculateTotal = () => {
    return formData.items.reduce((sum, item) => {
      const qty = parseFloat(item.quantity) || 0;
      const price = parseFloat(item.cost_price) || 0;
      return sum + qty * price;
    }, 0);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const validItems = formData.items.filter(
      (item) => item.product_id && parseFloat(item.quantity) > 0 && parseFloat(item.cost_price) > 0
    );

    if (validItems.length === 0) {
      toast.error("Please add at least one item with quantity and price");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        supplier_id: (formData.supplier_id && formData.supplier_id !== "no_supplier") ? formData.supplier_id : null,
        payment_status: formData.payment_status,
        date: formData.date,
        notes: formData.notes || null,
        items: validItems.map((item) => ({
          product_id: item.product_id,
          quantity: parseFloat(item.quantity),
          cost_price: parseFloat(item.cost_price),
        })),
      };

      if (editingPurchase) {
        await updatePurchase(editingPurchase.id, payload);
        toast.success(`Purchase updated successfully!`);
      } else {
        const response = await createPurchase(payload);
        if (response.data.debit_used && response.data.debit_used > 0) {
          toast.success(`Purchase recorded! Used ${formatCurrency(response.data.debit_used)} from debit balance.`);
        } else {
          toast.success(`Purchase ${response.data.purchase_number} recorded!`);
        }
      }

      setDialogOpen(false);
      resetForm();
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to record purchase");
    } finally {
      setSaving(false);
    }
  };

  const paymentStatusBadge = {
    cash: "bg-emerald-50 text-emerald-700",
    bank: "bg-blue-50 text-blue-700",
    unpaid: "bg-amber-50 text-amber-700",
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="purchases-page">
      <div className="space-y-6 animate-fade-in" data-testid="purchases-page">
        <PageHeader
          title="Purchases"
          description="Record stock purchases from suppliers"
          action={
            <Button onClick={() => setDialogOpen(true)} className="bg-brand-600 hover:bg-brand-700" data-testid="add-purchase-btn">
              <Plus className="h-4 w-4 mr-2" />
              New Purchase
            </Button>
          }
        />

        <Dialog open={dialogOpen} onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) resetForm();
        }}>
          <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editingPurchase ? "Edit Purchase" : "Record Purchase"}</DialogTitle>
              <DialogDescription>{editingPurchase ? "Update purchase details" : "Add products received from supplier"}</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-6 mt-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Supplier (Optional)</Label>
                  <Select value={formData.supplier_id} onValueChange={(value) => setFormData((prev) => ({ ...prev, supplier_id: value }))}>
                    <SelectTrigger data-testid="purchase-supplier-select">
                      <SelectValue placeholder="Select supplier" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="no_supplier">No supplier</SelectItem>
                      {suppliers.map((s) => (<SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="date">Date</Label>
                  <Input id="date" type="date" value={formData.date} onChange={(e) => setFormData((prev) => ({ ...prev, date: e.target.value }))} data-testid="purchase-date-input" />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Payment Status</Label>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { value: "cash", icon: Banknote, label: "Cash" },
                    { value: "bank", icon: Building2, label: "Bank" },
                    { value: "unpaid", icon: Clock, label: "Unpaid" },
                  ].map(({ value, icon: Icon, label }) => (
                    <button key={value} type="button" onClick={() => setFormData((prev) => ({ ...prev, payment_status: value }))} className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${formData.payment_status === value ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-200 hover:border-slate-300"}`} data-testid={`purchase-status-${value}`}>
                      <Icon className="h-4 w-4" /><span className="font-medium">{label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-base">Items</CardTitle></CardHeader>
                <CardContent className="space-y-3">
                  {formData.items.map((item, index) => (
                    <div key={index} className="grid grid-cols-12 gap-2 items-end p-3 bg-slate-50 rounded-lg">
                      <div className="col-span-12 md:col-span-5 space-y-1">
                        <Label className="text-xs">Product</Label>
                        <Select value={item.product_id} onValueChange={(value) => handleItemChange(index, "product_id", value)}>
                          <SelectTrigger data-testid={`purchase-item-product-${index}`}>
                            <SelectValue placeholder="Select product" />
                          </SelectTrigger>
                          <SelectContent>
                            {products.map((p) => (<SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="col-span-4 md:col-span-2 space-y-1">
                        <Label className="text-xs">Qty</Label>
                        <Input type="number" min="0" step="1" value={item.quantity} onChange={(e) => handleItemChange(index, "quantity", e.target.value)} className="font-mono" data-testid={`purchase-item-qty-${index}`} />
                      </div>
                      <div className="col-span-4 md:col-span-3 space-y-1">
                        <Label className="text-xs">Cost Price</Label>
                        <div className="relative">
                          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs">₹</span>
                          <Input type="number" min="0" step="0.01" value={item.cost_price} onChange={(e) => handleItemChange(index, "cost_price", e.target.value)} className="pl-5 font-mono" data-testid={`purchase-item-price-${index}`} />
                        </div>
                      </div>
                      <div className="col-span-4 md:col-span-1 flex justify-end">
                        <Button type="button" variant="ghost" size="icon" onClick={() => handleRemoveItem(index)} disabled={formData.items.length === 1} className="text-slate-400 hover:text-red-600">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                  <Button type="button" variant="outline" onClick={handleAddItem} className="w-full" data-testid="add-purchase-item-btn">
                    <Plus className="h-4 w-4 mr-2" />Add Item
                  </Button>
                </CardContent>
              </Card>

              <div className="flex justify-between items-center p-4 bg-slate-100 rounded-lg">
                <span className="font-medium text-slate-700">Total</span>
                <span className="text-xl font-bold font-mono text-brand-600">{formatCurrency(calculateTotal())}</span>
              </div>

              <div className="flex justify-end gap-3">
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button type="submit" className="bg-brand-600 hover:bg-brand-700" disabled={saving} data-testid="save-purchase-btn">
                  {saving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />{editingPurchase ? "Updating..." : "Record Purchase"}</> : (editingPurchase ? "Update Purchase" : "Record Purchase")}
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
              This will permanently delete purchase #{purchaseToDelete?.purchase_number}.
              This action cannot be undone and will reverse stock movements.
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
        searchPlaceholder="Search purchases..."
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
        statusLabel="All Statuses"
        statusOptions={[
          { value: "unpaid", label: "Unpaid" },
          { value: "partially_paid", label: "Partially Paid" },
          { value: "paid", label: "Paid" }
        ]}
        dateRange={dateRange}
        setDateRange={setDateRange}
        onClear={() => {
          setSearch("");
          setStatusFilter("all");
          setDateRange(undefined);
        }}
      />

      {/* Purchases Table */}
      {loading ? (
        <Card><CardContent className="p-6"><div className="space-y-4">{[...Array(5)].map((_, i) => (<Skeleton key={i} className="h-12 w-full" />))}</div></CardContent></Card>
      ) : (() => {
        const filtered = purchases.filter((p) => {
          const q = search.toLowerCase();
          const matchSearch = !q || p.purchase_number?.toLowerCase().includes(q) || p.supplier_name?.toLowerCase().includes(q);
          const matchStatus = statusFilter === "all" || p.payment_status === statusFilter;
          return matchSearch && matchStatus;
        });
        return filtered.length > 0 ? (
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Purchase #</TableHead>
                    <TableHead>Supplier</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead>Payment</TableHead>
                    <TableHead className="w-[80px]"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((purchase) => (
                    <TableRow
                      key={purchase.id}
                      className="cursor-pointer hover:bg-slate-50"
                      onClick={(e) => {
                        if (e.target.closest('button')) return;
                        handleEdit(purchase); // Purchases opens Edit dialog instead of a detail page
                      }}
                      data-testid={`purchase-row-${purchase.id}`}
                    >
                      <TableCell className="font-medium text-brand-600">{purchase.purchase_number}</TableCell>
                      <TableCell>{purchase.supplier_name || <span className="text-slate-400">-</span>}</TableCell>
                      <TableCell className="text-slate-500">{formatDate(purchase.date)}</TableCell>
                      <TableCell className="text-right font-mono font-medium">{formatCurrency(purchase.total)}</TableCell>
                      <TableCell>
                        <Badge variant={
                          purchase.payment_status === "paid" ? "success" :
                            purchase.payment_status === "partially_paid" ? "warning" : "destructive"
                        }>
                          {purchase.payment_status === "unpaid" ? "Unpaid" : purchase.payment_status.charAt(0).toUpperCase() + purchase.payment_status.slice(1).replace("_", " ")}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" className="h-8 w-8 p-0" data-testid={`purchase-actions-${purchase.id}`}>
                              <span className="sr-only">Open menu</span>
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                            <DropdownMenuItem onClick={() => handleEdit(purchase)} data-testid={`edit-purchase-${purchase.id}`}>
                              <Pencil className="mr-2 h-4 w-4" />
                              Edit
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => handleDeleteClick(purchase)}
                              className="text-red-600 focus:text-red-600"
                              data-testid={`delete-purchase-${purchase.id}`}
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
              <ShoppingCart className="h-12 w-12 text-slate-300 mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-1">No purchases found</h3>
              <p className="text-slate-500 text-sm mb-4">{search || statusFilter !== 'all' ? 'Try adjusting your search or filters' : 'Record your first purchase to add stock'}</p>
              <Button onClick={() => setDialogOpen(true)} className="bg-brand-600 hover:bg-brand-700"><Plus className="h-4 w-4 mr-2" />New Purchase</Button>
            </CardContent>
          </Card>
        );
      })()}
    </div>
  );
};

export default Purchases;
