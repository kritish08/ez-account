import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useModules } from "../context/ModulesContext";
import { getPurchases, getProducts, getSuppliers, createPurchase, updatePurchase, deletePurchase, formatCurrency, formatDate, parseInvoice, getSupplierLedger } from "../lib/api";
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
import { Plus, ShoppingCart, Loader2, Trash2, Banknote, Building2, Clock, MoreHorizontal, Pencil, ScanLine, Upload, CheckCircle2, XCircle, FileText } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { UIFilters } from "../components/UIFilters";
import { SearchableProductSelect } from '../components/SearchableProductSelect';

const Purchases = () => {
  const navigate = useNavigate();
  const { modules } = useModules();
  const [purchases, setPurchases] = useState([]);
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false); // Renamed from scanning to parsing
  const fileInputRef = React.useRef(null);
  const fileInputCameraRef = React.useRef(null);
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
    attachment_url: "",
    apply_debit: false
  });
  const [supplierBalance, setSupplierBalance] = useState(0);

  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = () => setRefreshKey((k) => k + 1);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const startDate = dateRange?.from ? dateRange.from.toISOString().split('T')[0] : null;
    const endDate = dateRange?.to ? dateRange.to.toISOString().split('T')[0] : null;
    Promise.all([getPurchases(startDate, endDate), getProducts(), getSuppliers()])
      .then(([purchasesRes, productsRes, suppliersRes]) => {
        if (!cancelled) {
          setPurchases(purchasesRes.data);
          setProducts(productsRes.data);
          setSuppliers(suppliersRes.data);
        }
      })
      .catch(() => toast.error("Failed to load data"))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshKey, dateRange]);

  const resetForm = () => {
    setFormData({
      supplier_id: "",
      payment_status: "unpaid",
      date: new Date().toISOString().split("T")[0],
      notes: "",
      items: [{ product_id: "", quantity: "", cost_price: "", batch_id: "", serial_numbers_text: "" }],
      attachment_url: "",
      apply_debit: false
    });
    setEditingPurchase(null);
    setSupplierBalance(0);
  };

  const fetchSupplierBalance = async (supplierId) => {
    if (!supplierId || supplierId === "no_supplier") {
      setSupplierBalance(0);
      return;
    }
    try {
      const res = await getSupplierLedger(supplierId);
      // If balance is negative, it means we have a debit balance (we paid them more / returns)
      // Actually, for Liability: Credit is normal.
      // If balance < 0, it means Debit > Credit. So we have an Advance/Debit balance.
      // Correct.
      setSupplierBalance(res.data.current_balance);
      setFormData(prev => ({ ...prev, apply_debit: false }));
    } catch (err) {
      console.error("Failed to fetch balance", err);
    }
  };

  const handleScanClick = () => {
    fileInputRef.current?.click();
  };

  const handleCameraClick = () => {
    fileInputCameraRef.current?.click();
  };

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    try {
      setParsing(true); // Changed from setScanning to setParsing
      toast.info("Scanning invoice with AI...", { duration: 3000 });

      const response = await parseInvoice(file);
      const data = response.data;

      if (data.error) {
        toast.error(data.error);
        return;
      }

      // Auto-fill logic
      const updates = {};

      if (data.date) updates.date = data.date;
      if (data.attachment_url) updates.attachment_url = data.attachment_url;

      const detectedName = data.supplier_name || data.party_name;
      if (detectedName) {
        // Try to find supplier with improved matching
        const normalize = (str) => str.toLowerCase().replace(/[^a-z0-9]/g, "");
        const searchName = normalize(detectedName);

        const match = suppliers.find(s => {
          const sName = normalize(s.name);
          return sName.includes(searchName) || searchName.includes(sName);
        });

        if (match) {
          updates.supplier_id = match.id;
          toast.success(`Matched Supplier: ${match.name}`);
        } else {
          updates.notes = `Supplier: ${detectedName}. ` + (formData.notes || "");
          toast.info(`Supplier '${detectedName}' not found in list.`);
        }
      }

      if (data.items && data.items.length > 0) {
        const newItems = data.items.map(item => ({
          product_id: "", // User must map or we fuzzy match if we want advanced
          description: item.description || "Item",
          quantity: item.quantity || 1,
          cost_price: item.rate || item.amount || 0
        }));
        updates.items = newItems;
      }

      if (data.invoice_number) {
        updates.notes = (updates.notes || "") + ` Invoice #: ${data.invoice_number}`;
      }

      setFormData(prev => ({ ...prev, ...updates }));
      if (data.attachment_url) toast.info("Invoice image attached");
      toast.success("Invoice scanned successfully!");

    } catch (error) {
      console.error(error);
      toast.error("Failed to parse invoice. Please try manually.");
    } finally {
      setParsing(false); // Changed from setScanning to setParsing
      // Reset input
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (fileInputCameraRef.current) fileInputCameraRef.current.value = "";
    }
  };

  const handleScan = (decodedText) => {
    setScannerOpen(false);
    try {
      // payload format: EZ|PRD:65a12b|BAT:BCH-01|SER:SN10023
      const parts = decodedText.split('|');
      if (parts[0] !== 'EZ') throw new Error("Not a valid EZ barcode");
      
      let prd = "";
      let bat = "";
      let ser = "";
      
      parts.forEach(p => {
        if (p.startsWith("PRD:")) prd = p.replace("PRD:", "");
        if (p.startsWith("BAT:")) bat = p.replace("BAT:", "");
        if (p.startsWith("SER:")) ser = p.replace("SER:", "");
      });
      
      if (!prd) throw new Error("No product ID found in barcode");
      
      const product = products.find(p => p.id === prd);
      if (!product) throw new Error("Product not found in database");
      
      setFormData(prev => {
        let newItems = [...prev.items];
        if (newItems.length === 1 && !newItems[0].product_id) {
          newItems = [];
        }
        
        let existingItemIndex = bat || ser 
          ? newItems.findIndex(i => i.product_id === prd && i.batch_id === bat && i.cost_price === product.cost_price)
          : newItems.findIndex(i => i.product_id === prd && i.cost_price === product.cost_price);
        
        if (existingItemIndex >= 0 && ser) {
          const item = newItems[existingItemIndex];
          const currentSerials = item.serial_numbers_text ? item.serial_numbers_text.split(",").map(s => s.trim()).filter(s => s) : [];
          if (!currentSerials.includes(ser)) {
             currentSerials.push(ser);
             item.serial_numbers_text = currentSerials.join(", ");
             item.quantity = currentSerials.length;
          } else {
             toast.info("Serial number already scanned");
          }
        } else if (existingItemIndex >= 0 && !ser) {
          newItems[existingItemIndex].quantity += 1;
        } else {
          newItems.push({
            product_id: product.id,
            quantity: 1,
            cost_price: product.cost_price || 0,
            batch_id: bat || "",
            serial_numbers_text: ser || ""
          });
        }
        
        return { ...prev, items: newItems };
      });
      
      toast.success(`Scanned: ${product.name}`);
    } catch (err) {
      toast.error(err.message || "Invalid barcode scanned");
    }
  };

  const handleEdit = (purchase) => {
    setEditingPurchase(purchase);
    // Transform purchase items for form
    const items = purchase.items.map(item => ({
      product_id: item.product_id,
      quantity: item.quantity,
      cost_price: item.cost_price,
      batch_id: item.batch_id || "",
      serial_numbers_text: item.serial_numbers ? item.serial_numbers.join(", ") : ""
    }));

    setFormData({
      supplier_id: purchase.supplier_id || "no_supplier",
      payment_status: purchase.payment_status,
      date: purchase.date.split("T")[0],
      notes: purchase.notes || "",
      items: items.length > 0 ? items : [{ product_id: "", quantity: "", cost_price: "", batch_id: "", serial_numbers_text: "" }],
      attachment_url: purchase.attachment_url || "",
      apply_debit: false
    });
    if (purchase.supplier_id) {
      fetchSupplierBalance(purchase.supplier_id);
    }
    setDialogOpen(true);
  };

  const handleDeleteClick = (purchase) => {
    setPurchaseToDelete(purchase);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    // Optimistic delete
    setPurchases((prev) => prev.filter((p) => p.id !== purchaseToDelete.id));
    setDeleteDialogOpen(false);
    const deleted = purchaseToDelete;
    setPurchaseToDelete(null);
    try {
      await deletePurchase(deleted.id);
      toast.success("Purchase deleted successfully");
      refresh();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete purchase");
      refresh();
    }
  };

  const handleAddItem = () => {
    setFormData((prev) => ({
      ...prev,
      items: [...prev.items, { product_id: "", quantity: "", cost_price: "", batch_id: "", serial_numbers_text: "" }],
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
        attachment_url: formData.attachment_url || null,
        items: validItems.map((item) => {
          const payloadItem = {
            product_id: item.product_id,
            quantity: parseFloat(item.quantity),
            cost_price: parseFloat(item.cost_price),
          };
          if (item.batch_id && item.batch_id.trim() !== '') {
            payloadItem.batch_id = item.batch_id.trim();
          }
          if (item.serial_numbers_text && item.serial_numbers_text.trim() !== '') {
            payloadItem.serial_numbers = item.serial_numbers_text.split(',').map(s => s.trim()).filter(s => s);
          }
          return payloadItem;
        }),
        apply_debit: formData.apply_debit
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
      refresh();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to record purchase");
      refresh();
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
              <DialogDescription>
                Enter the purchase details below.
              </DialogDescription>
            </DialogHeader>

            {/* AI Scan Button */}
            {!editingPurchase && (
              <div className="bg-slate-50 p-4 rounded-lg flex items-center justify-between border border-dashed border-slate-300">
                <div className="flex items-center gap-3">
                  <div className="bg-brand-100 p-2 rounded-full">
                    <ScanLine className="h-5 w-5 text-brand-600" />
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-slate-900">Auto-fill with AI</h4>
                    <p className="text-xs text-slate-500">Upload an improved bill/invoice to auto-fill details.</p>
                  </div>
                </div>
                <div>
                  <input
                    type="file"
                    ref={fileInputRef}
                    className="hidden"
                    accept="image/*,application/pdf"
                    onChange={handleFileChange}
                  />
                  <input
                    type="file"
                    ref={fileInputCameraRef}
                    className="hidden"
                    accept="image/*"
                    capture="environment"
                    onChange={handleFileChange}
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleScanClick}
                      disabled={parsing} // Changed from scanning to parsing
                    >
                      {parsing ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Upload className="h-4 w-4 mr-2" />}
                      {parsing ? "Scanning..." : "Upload Bill"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCameraClick}
                      disabled={parsing} // Changed from scanning to parsing
                      className="hidden md:flex" // Ideally visible on mobile, keeping consistent
                    >
                      <ScanLine className="h-4 w-4 mr-2" />
                      Take Photo
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {formData.attachment_url && (
              <div className="bg-slate-50 p-3 rounded-lg flex items-center gap-2 border border-slate-200 mt-2 text-sm">
                <ScanLine className="h-4 w-4 text-emerald-600" />
                <span className="text-slate-700">Invoice attached</span>
                <a href={`http://localhost:8000${formData.attachment_url}`} target="_blank" rel="noopener noreferrer" className="ml-auto text-brand-600 hover:underline font-medium">
                  View Original Invoice
                </a>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6 mt-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Supplier (Optional)</Label>
                  <Select value={formData.supplier_id} onValueChange={(value) => {
                    setFormData((prev) => ({ ...prev, supplier_id: value }));
                    fetchSupplierBalance(value);
                  }}>
                    <SelectTrigger data-testid="purchase-supplier-select">
                      <SelectValue placeholder="Select supplier" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="no_supplier">No supplier</SelectItem>
                      {suppliers.map((s) => (<SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>))}
                    </SelectContent>
                  </Select>
                  {supplierBalance < 0 && formData.payment_status === "unpaid" && (
                    <div className="flex items-center space-x-2 mt-2 p-2 bg-green-50 text-green-700 rounded-md">
                      <input
                        type="checkbox"
                        id="apply_debit"
                        checked={formData.apply_debit}
                        onChange={(e) => setFormData(prev => ({ ...prev, apply_debit: e.target.checked }))}
                        className="h-4 w-4 text-brand-600 focus:ring-brand-500 border-gray-300 rounded"
                      />
                      <label htmlFor="apply_debit" className="text-sm font-medium">
                        Apply available debit of {formatCurrency(Math.abs(supplierBalance))}
                      </label>
                    </div>
                  )}
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
                  {formData.items.map((item, index) => {
                    const selectedProduct = products.find(p => p.id === item.product_id);
                    const showBatch = modules?.enable_advanced_ims && selectedProduct?.track_batches;
                    const showSerials = modules?.enable_advanced_ims && selectedProduct?.track_serials;

                    return (
                      <div key={index} className="grid grid-cols-12 gap-2 p-3 bg-slate-50 rounded-lg border border-slate-100 mb-2">
                        <div className="col-span-12 md:col-span-5 space-y-1">
                          <Label className="text-xs">Product</Label>
                          <SearchableProductSelect
                            products={products}
                            value={item.product_id}
                            onValueChange={(value) => handleItemChange(index, "product_id", value)}
                            placeholder="Search product"
                            itemType="raw_material,wip"
                          />
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
                        <div className="col-span-4 md:col-span-2 flex justify-end items-end h-[56px]">
                          <Button type="button" variant="ghost" size="icon" onClick={() => handleRemoveItem(index)} disabled={formData.items.length === 1} className="text-slate-400 hover:text-red-600 mb-[2px]">
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                        
                        {(showBatch || showSerials) && (
                          <div className="col-span-12 grid grid-cols-12 gap-2 mt-2 pt-2 border-t border-slate-200 border-dashed">
                            {showBatch && (
                              <div className="col-span-12 md:col-span-4 space-y-1">
                                <Label className="text-xs text-brand-600">Batch Number</Label>
                                <Input value={item.batch_id} onChange={(e) => handleItemChange(index, "batch_id", e.target.value)} placeholder="e.g. BATCH-001" className="text-sm" />
                              </div>
                            )}
                            {showSerials && (
                              <div className={`col-span-12 ${showBatch ? 'md:col-span-8' : 'md:col-span-12'} space-y-1`}>
                                <Label className="text-xs text-brand-600">Serial Numbers (comma separated)</Label>
                                <Input value={item.serial_numbers_text} onChange={(e) => handleItemChange(index, "serial_numbers_text", e.target.value)} placeholder="SN1001, SN1002..." className="text-sm font-mono" />
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  <div className="flex flex-col sm:flex-row gap-2 mt-4">
                    <Button type="button" variant="outline" onClick={handleAddItem} className="w-full" data-testid="add-purchase-item-btn">
                      <Plus className="h-4 w-4 mr-2" />Add Item
                    </Button>
                    {modules?.enable_advanced_ims && (
                      <Button 
                        type="button" 
                        variant="outline" 
                        onClick={() => setScannerOpen(true)} 
                        className="w-full border-brand-200 text-brand-700 hover:bg-brand-50 hover:text-brand-800"
                      >
                        <ScanLine className="h-4 w-4 mr-2" />
                        Scan Item QR
                      </Button>
                    )}
                  </div>
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
                            <DropdownMenuItem onSelect={() => handleEdit(purchase)} data-testid={`edit-purchase-${purchase.id}`}>
                              <Pencil className="mr-2 h-4 w-4" />
                              Edit
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onSelect={() => handleDeleteClick(purchase)}
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
