import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useModules } from "../context/ModulesContext";
import { getProducts, createProduct, updateProduct, deleteProduct, formatCurrency } from "../lib/api";
import BarcodeScanner from "../components/LazyBarcodeScanner";
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
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";
import { Plus, Search, Package, Loader2, MoreHorizontal, Pencil, Trash2, AlertTriangle, ScanLine, Layers, Hash } from "lucide-react";

const RawMaterials = () => {
  const navigate = useNavigate();
  const { modules } = useModules();
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [productToDelete, setProductToDelete] = useState(null);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    sku: "",
    selling_price: "",
    cost_price: "",
    opening_stock: "",
    low_stock_threshold: "10",
  });

  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = () => setRefreshKey((k) => k + 1);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getProducts({ item_type: 'raw_material,wip' })
      .then((res) => { if (!cancelled) setProducts(res.data); })
      .catch(() => toast.error("Failed to load products"))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  const resetForm = () => {
    setFormData({
      name: "",
      sku: "",
      selling_price: "",
      cost_price: "",
      opening_stock: "",
      low_stock_threshold: "10",
    });
    setEditingProduct(null);
  };

  const handleScan = (decodedText) => {
    setScannerOpen(false);
    try {
      const parts = decodedText.split('|');
      if (parts[0] === 'EZ') {
        const prdPart = parts.find(p => p.startsWith("PRD:"));
        if (prdPart) {
          const productId = prdPart.replace("PRD:", "");
          navigate(`/products/${productId}`);
          return;
        }
      }
      // Fallback: search by serial/sku text
      setSearch(decodedText);
    } catch (err) {
      toast.error("Invalid QR code scanned");
    }
  };

  const handleEdit = (product) => {
    navigate(`/products/${product.id}`);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name) {
      toast.error("Product name is required");
      return;
    }
    if (!formData.cost_price || parseFloat(formData.cost_price) <= 0) {
      toast.error("Please enter a valid cost price for this raw material");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: formData.name,
        sku: formData.sku || null,
        selling_price: parseFloat(formData.selling_price) || 0,
        cost_price: parseFloat(formData.cost_price) || 0,
        opening_stock: parseFloat(formData.opening_stock) || 0,
        low_stock_threshold: parseFloat(formData.low_stock_threshold) || 10,
        item_type: "raw_material"
      };

      if (editingProduct) {
        await updateProduct(editingProduct.id, payload);
        toast.success("Product updated successfully");
      } else {
        await createProduct(payload);
        toast.success("Product added successfully");
      }

      setDialogOpen(false);
      resetForm();
      refresh();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save product");
      refresh();
    } finally {
      setSaving(false);
    }
  };

  const filteredProducts = products
    .filter(
      (p) =>
        p.name.toLowerCase().includes(search.toLowerCase()) ||
        p.sku?.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => a.name.localeCompare(b.name));

  const handleDeleteClick = (product) => {
    setProductToDelete(product);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    // Pessimistic delete: wait for the server, only update local state on
    // success. Previous code optimistically removed the row first; if the
    // network or server was down, the row stayed gone in the UI until a
    // refresh happened to succeed.
    const deleted = productToDelete;
    setDeleteDialogOpen(false);
    setProductToDelete(null);
    try {
      await deleteProduct(deleted.id);
      setProducts((prev) => prev.filter((p) => p.id !== deleted.id));
      toast.success("Product deleted successfully");
      refresh();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete product");
    }
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="products-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">Raw Materials</h1>
          <p className="text-slate-500 mt-1">Manage your inventory products</p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{editingProduct ? "Edit Product" : "Add New Product"}</DialogTitle>
              <DialogDescription>Enter product details below</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label htmlFor="name">Product Name *</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                  placeholder="Product name"
                  data-testid="product-name-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="sku">SKU (Optional)</Label>
                <Input
                  id="sku"
                  value={formData.sku}
                  onChange={(e) => setFormData((prev) => ({ ...prev, sku: e.target.value }))}
                  placeholder="SKU code"
                  data-testid="product-sku-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="cost_price">Unit Cost Price *</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono">₹</span>
                  <Input
                    id="cost_price"
                    type="number" inputMode="decimal"
                    step="0.01"
                    min="0"
                    value={formData.cost_price}
                    onChange={(e) => setFormData((prev) => ({ ...prev, cost_price: e.target.value }))}
                    className="pl-8 font-mono border-brand-200 focus-visible:ring-brand-500"
                    data-testid="product-cost-price-input"
                    placeholder="0.00"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                {!editingProduct && (
                  <div className="space-y-2">
                    <Label htmlFor="opening_stock">Opening Stock</Label>
                    <Input
                      id="opening_stock"
                      type="number" inputMode="decimal"
                      min="0"
                      value={formData.opening_stock}
                      onChange={(e) => setFormData((prev) => ({ ...prev, opening_stock: e.target.value }))}
                      className="font-mono"
                      data-testid="product-opening-stock-input"
                    />
                  </div>
                )}

                <div className="space-y-2">
                  <Label htmlFor="low_stock_threshold">Low Stock Alert</Label>
                  <Input
                    id="low_stock_threshold"
                    type="number" inputMode="decimal"
                    min="0"
                    value={formData.low_stock_threshold}
                    onChange={(e) => setFormData((prev) => ({ ...prev, low_stock_threshold: e.target.value }))}
                    className="font-mono"
                    data-testid="product-low-stock-input"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4">
                <Button type="button" variant="outline" onClick={() => { setDialogOpen(false); resetForm(); }}>
                  Cancel
                </Button>
                <Button type="submit" className="bg-brand-600 hover:bg-brand-700" disabled={saving} data-testid="save-product-btn">
                  {saving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</> : editingProduct ? "Update Product" : "Add Product"}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>

        <div className="flex flex-col sm:flex-row gap-2">
          <Button className="bg-brand-600 hover:bg-brand-700" onClick={() => { resetForm(); setDialogOpen(true); }} data-testid="add-product-btn">
            <Plus className="h-4 w-4 mr-2" />
            Add Product
          </Button>
          {modules?.enable_advanced_ims && (
            <Button variant="outline" onClick={() => setScannerOpen(true)}>
              <ScanLine className="h-4 w-4 mr-2" />
              Scan to Find
            </Button>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <Input
          placeholder="Search products..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10"
          data-testid="product-search-input"
        />
      </div>

      {/* Delete Alert Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Product?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete "{productToDelete?.name}". Products used in invoices or purchases cannot be deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-red-600 hover:bg-red-700">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Products Table */}
      {loading ? (
        <Card><CardContent className="p-6"><div className="space-y-4">{[...Array(5)].map((_, i) => (<Skeleton key={i} className="h-12 w-full" />))}</div></CardContent></Card>
      ) : filteredProducts.length > 0 ? (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Product</TableHead>
                  <TableHead>SKU</TableHead>
                  <TableHead className="text-right">Stock</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                  <TableHead className="text-right">Selling Price</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredProducts.map((product) => (
                  <TableRow
                    key={product.id}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={(e) => {
                      if (e.target.closest('button')) return;
                      handleEdit(product);
                    }}
                    data-testid={`product-row-${product.id}`}
                  >
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-brand-50 flex items-center justify-center">
                          <Package className="h-4 w-4 text-brand-600" />
                        </div>
                        <div>
                          <span className="font-medium text-slate-900">{product.name}</span>
                          {modules?.enable_advanced_ims && (
                            <div className="flex gap-1 mt-0.5">
                              {product.track_batches && <Badge variant="secondary" className="text-xs px-1 py-0 h-4"><Layers className="h-2.5 w-2.5 mr-0.5" />Batches</Badge>}
                              {product.track_serials && <Badge variant="secondary" className="text-xs px-1 py-0 h-4"><Hash className="h-2.5 w-2.5 mr-0.5" />Serials</Badge>}
                            </div>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-slate-500">{product.sku || "-"}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <span className={`font-mono font-medium ${product.current_stock < 0 ? "text-red-600" : product.is_low_stock ? "text-amber-600" : "text-slate-900"}`}>
                          {product.current_stock}
                        </span>
                        {product.is_low_stock && (
                          <AlertTriangle className="h-4 w-4 text-amber-500" />
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono font-medium">{formatCurrency(product.cost_price)}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" className="h-8 w-8 p-0">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuLabel>Actions</DropdownMenuLabel>
                          <DropdownMenuItem onSelect={() => handleEdit(product)}>
                            <Pencil className="mr-2 h-4 w-4" /> Edit
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onSelect={() => handleDeleteClick(product)} className="text-red-600 focus:text-red-600">
                            <Trash2 className="mr-2 h-4 w-4" /> Delete
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
            <Package className="h-12 w-12 text-slate-300 mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-1">No products yet</h3>
            <p className="text-slate-500 text-sm mb-4">Add your first product to get started</p>
            <Button onClick={() => { resetForm(); setDialogOpen(true); }} className="bg-brand-600 hover:bg-brand-700">
              <Plus className="h-4 w-4 mr-2" />Add Product
            </Button>
          </CardContent>
        </Card>
      )}

      <BarcodeScanner open={scannerOpen} onScan={handleScan} onClose={() => setScannerOpen(false)} />
    </div>
  );
};

export default RawMaterials;
