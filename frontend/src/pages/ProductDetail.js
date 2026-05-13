import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { 
  getProduct, 
  getProductStockMovements, 
  getProductBatches, 
  getProductSerialNumbers,
  updateProduct,
  formatCurrency,
  formatDate,
  getBarcodeLabels
} from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { toast } from "sonner";
import {
  ArrowLeft,
  Package,
  Barcode,
  History,
  Layers,
  Hash,
  TrendingDown,
  TrendingUp,
  Settings,
  Edit,
  Loader2,
  ScanLine,
  Printer
} from "lucide-react";
import { useModules } from "../context/ModulesContext";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";

const ProductDetail = () => {
  const { id } = useParams();
  const { modules } = useModules();
  const navigate = useNavigate();
  const [product, setProduct] = useState(null);
  const [movements, setMovements] = useState([]);
  const [batches, setBatches] = useState([]);
  const [serials, setSerials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [printing, setPrinting] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    sku: "",
    barcode: "",
    selling_price: "",
    cost_price: "",
    low_stock_threshold: "10",
    track_batches: false,
    track_serials: false,
    hsn: "",
    category: "",
    item_type: "finished_good",
    reorder_point: "0"
  });

  const handleEditClick = () => {
    setFormData({
      name: product.name,
      sku: product.sku || "",
      barcode: product.barcode || "",
      selling_price: (product.selling_price || 0).toString(),
      cost_price: (product.cost_price || 0).toString(),
      low_stock_threshold: (product.low_stock_threshold || 10).toString(),
      track_batches: product.track_batches || false,
      track_serials: product.track_serials || false,
      hsn: product.hsn || "",
      category: product.category || "",
      item_type: product.item_type || "finished_good",
      reorder_point: (product.reorder_point || 0).toString()
    });
    setDialogOpen(true);
  };

  const handleUpdate = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        name: formData.name,
        sku: formData.sku || null,
        barcode: formData.barcode || null,
        selling_price: parseFloat(formData.selling_price),
        cost_price: parseFloat(formData.cost_price) || 0,
        low_stock_threshold: parseFloat(formData.low_stock_threshold) || 10,
        track_batches: formData.track_batches,
        track_serials: formData.track_serials,
        hsn: formData.hsn || null,
        category: formData.category || null,
        item_type: formData.item_type,
        reorder_point: parseFloat(formData.reorder_point) || 0,
      };
      await updateProduct(product.id, payload);
      toast.success("Product updated successfully");
      setDialogOpen(false);
      fetchData(); // reload
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to update product");
    } finally {
      setSaving(false);
    }
  };
  const handlePrintLabels = async (type) => {
    try {
      setPrinting(true);
      
      if (type === 'general') {
        const res = await getBarcodeLabels(id, {});
        printLabels(res.data.labels);
      } else if (type === 'serial') {
        const activeSerials = serials.filter(s => s.status === 'IN_STOCK').slice(0, 50).map(s => s.serial_number);
        if (activeSerials.length === 0) return toast.info("No active serials to print");
        const res = await getBarcodeLabels(id, { serial_numbers: activeSerials.join(",") });
        printLabels(res.data.labels);
      } else if (type === 'batch') {
        const activeBatches = batches.slice(0, 10).map(b => b.batch_number);
        if (activeBatches.length === 0) return toast.info("No active batches to print");
        const res = await getBarcodeLabels(id, { batch_id: activeBatches[0] });
        printLabels(res.data.labels);
      }
    } catch (err) {
      toast.error("Failed to generate labels");
    } finally {
      setPrinting(false);
    }
  };

  const printLabels = (labels) => {
    // Build the print page via a Blob URL + DOM manipulation rather than
    // `document.write` + inline `<script>`. Strict CSPs (script-src 'self')
    // block inline scripts in the popup, silently preventing the print
    // dialog from opening. Also avoids document.write XSS-pattern warnings.
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    const cards = labels.map(l => `
      <div class="label-card">
        <img src="${esc(l.qr_code)}" alt="QR" />
        <div class="label-text">
          ${esc((product?.name || "").substring(0, 15))}<br/>
          ${l.batch_id ? 'B: ' + esc(l.batch_id) + '<br/>' : ''}
          ${l.serial_number ? 'S: ' + esc(l.serial_number) : ''}
        </div>
      </div>`).join('');
    const html = `<!doctype html><html><head><title>Print Labels</title>
      <style>
        body { font-family: monospace; display: flex; flex-wrap: wrap; gap: 20px; padding: 20px; }
        .label-card { border: 1px dashed #ccc; padding: 10px; display: flex; flex-direction: column; align-items: center; width: 140px; }
        .label-card img { width: 120px; height: 120px; margin-bottom: 5px; }
        .label-text { font-size: 10px; text-align: center; word-break: break-all; }
      </style></head><body>${cards}</body></html>`;

    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const printWindow = window.open(url, '_blank');
    if (!printWindow) {
      URL.revokeObjectURL(url);
      toast.error("Please allow pop-ups to print labels");
      return;
    }
    // Trigger print from the opener once the popup has rendered.
    printWindow.addEventListener('load', () => {
      setTimeout(() => {
        try { printWindow.print(); } catch {}
        try { printWindow.close(); } catch {}
        URL.revokeObjectURL(url);
      }, 250);
    });
  };


  useEffect(() => {
    fetchData();
  }, [id, modules]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await getProduct(id);
      setProduct(res.data);
      
      const movRes = await getProductStockMovements(id);
      setMovements(movRes.data);

      if (modules?.enable_advanced_ims) {
        if (res.data.track_batches) {
          const batchRes = await getProductBatches(id);
          setBatches(batchRes.data);
        }
        if (res.data.track_serials) {
          const serialRes = await getProductSerialNumbers(id);
          setSerials(serialRes.data);
        }
      }
    } catch (error) {
      toast.error("Failed to load product details");
      navigate("/finished-goods");
    } finally {
      setLoading(false);
    }
  };

  if (loading && !product) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in" data-testid="product-detail-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => {
            const backRoute = product?.item_type === "raw_material" || product?.item_type === "wip"
              ? "/raw-materials"
              : "/finished-goods";
            navigate(backRoute);
          }}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold font-heading text-slate-900">{product.name}</h1>
              {product.is_low_stock && (
                <Badge variant="destructive" className="bg-red-100 text-red-700 border-red-200">
                  Low Stock
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-4 mt-1 text-sm text-slate-500">
              {product.sku && (
                <span className="flex items-center gap-1">
                  SKU: <span className="font-medium text-slate-700">{product.sku}</span>
                </span>
              )}
              {product.barcode && (
                <span className="flex items-center gap-1">
                  <Barcode className="h-4 w-4" />
                  <span className="font-medium text-slate-700">{product.barcode}</span>
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-2" onClick={handleEditClick}>
            <Edit className="h-4 w-4" /> Edit Product
          </Button>
        </div>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit Product Details</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleUpdate} className="space-y-6 pt-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Product Name</Label>
                <Input value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Category</Label>
                <Input value={formData.category} onChange={e => setFormData({...formData, category: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>SKU</Label>
                <Input value={formData.sku} onChange={e => setFormData({...formData, sku: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Barcode</Label>
                <Input value={formData.barcode} onChange={e => setFormData({...formData, barcode: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>HSN/SAC</Label>
                <Input value={formData.hsn} onChange={e => setFormData({...formData, hsn: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Item Type</Label>
                <Select value={formData.item_type} onValueChange={v => setFormData({...formData, item_type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="finished_good">Finished Good</SelectItem>
                    <SelectItem value="raw_material">Raw Material</SelectItem>
                    <SelectItem value="wip">Semi-Finished / WIP</SelectItem>
                    <SelectItem value="consumable">Consumable</SelectItem>
                    <SelectItem value="service">Service</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Low Stock Alert</Label>
                <Input type="number" value={formData.low_stock_threshold} onChange={e => setFormData({...formData, low_stock_threshold: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Reorder Point</Label>
                <Input type="number" value={formData.reorder_point} onChange={e => setFormData({...formData, reorder_point: e.target.value})} placeholder="0" />
              </div>
              <div className="space-y-2">
                <Label>Cost Price</Label>
                <Input type="number" step="0.01" value={formData.cost_price} onChange={e => setFormData({...formData, cost_price: e.target.value})} />
              </div>
              <div className="space-y-2">
                <Label>Selling Price</Label>
                <Input type="number" step="0.01" value={formData.selling_price} onChange={e => setFormData({...formData, selling_price: e.target.value})} />
              </div>
            </div>

            {modules?.enable_advanced_ims && (
              <div className="grid grid-cols-2 gap-4 pt-4 border-t">
                <div className="flex items-center justify-between p-4 border rounded-lg bg-slate-50">
                  <div className="space-y-0.5">
                    <Label className="text-base">Track Batches</Label>
                    <p className="text-sm text-slate-500">Enable batch tracking and expiry dates</p>
                  </div>
                  <Switch checked={formData.track_batches} onCheckedChange={c => setFormData({...formData, track_batches: c})} />
                </div>
                <div className="flex items-center justify-between p-4 border rounded-lg bg-slate-50">
                  <div className="space-y-0.5">
                    <Label className="text-base">Track Serials</Label>
                    <p className="text-sm text-slate-500">Track unique individual units</p>
                  </div>
                  <Switch checked={formData.track_serials} onCheckedChange={c => setFormData({...formData, track_serials: c})} />
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3 pt-4 border-t">
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
              <Button type="submit" className="bg-brand-600 hover:bg-brand-700" disabled={saving}>
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Save Changes
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Card className="bg-slate-50 border-slate-100">
          <CardContent className="p-6">
            <div className="flex justify-between items-start">
              <div className="space-y-1">
                <p className="text-sm font-medium text-slate-500">Current Stock</p>
                <p className={`text-2xl font-semibold ${product.is_low_stock ? 'text-red-600' : 'text-slate-900'}`}>
                  {product.current_stock} <span className="text-sm text-slate-500">{product.unit}</span>
                </p>
              </div>
              <div className="p-2 bg-blue-100 text-blue-600 rounded-lg">
                <Package className="h-5 w-5" />
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card className="bg-slate-50 border-slate-100">
          <CardContent className="p-6">
            <div className="flex justify-between items-start">
              <div className="space-y-1">
                <p className="text-sm font-medium text-slate-500">Selling Price</p>
                <p className="text-2xl font-semibold text-slate-900">
                  {formatCurrency(product.selling_price)}
                </p>
              </div>
              <div className="p-2 bg-green-100 text-green-600 rounded-lg">
                <TrendingUp className="h-5 w-5" />
              </div>
            </div>
          </CardContent>
        </Card>

        {modules?.enable_advanced_ims && product.track_batches && (
          <Card className="bg-slate-50 border-slate-100">
            <CardContent className="p-6">
              <div className="flex justify-between items-start">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-slate-500">Active Batches</p>
                  <p className="text-2xl font-semibold text-slate-900">
                    {batches.length}
                  </p>
                </div>
                <div className="p-2 bg-purple-100 text-purple-600 rounded-lg">
                  <Layers className="h-5 w-5" />
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {modules?.enable_advanced_ims && product.track_serials && (
          <Card className="bg-slate-50 border-slate-100">
            <CardContent className="p-6">
              <div className="flex justify-between items-start">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-slate-500">In-Stock Serials</p>
                  <p className="text-2xl font-semibold text-slate-900">
                    {serials.filter(s => s.status === "IN_STOCK").length}
                  </p>
                </div>
                <div className="p-2 bg-amber-100 text-amber-600 rounded-lg">
                  <Hash className="h-5 w-5" />
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="mb-4 bg-white border border-slate-200">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="history">Stock History</TabsTrigger>
          {modules?.enable_advanced_ims && product.track_batches && (
            <TabsTrigger value="batches">Batches</TabsTrigger>
          )}
          {modules?.enable_advanced_ims && product.track_serials && (
            <TabsTrigger value="serials">Serial Numbers</TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Product Details</CardTitle>
                <CardDescription>Basic attributes and inventory settings</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-sm text-slate-500 mb-1">Category</p>
                    <p className="font-medium text-slate-900">{product.category || "Uncategorized"}</p>
                  </div>
                  <div>
                    <p className="text-sm text-slate-500 mb-1">HSN/SAC</p>
                    <p className="font-medium text-slate-900">{product.hsn || "-"}</p>
                  </div>
                  <div>
                    <p className="text-sm text-slate-500 mb-1">Low Stock Threshold</p>
                    <p className="font-medium text-slate-900">{product.low_stock_threshold || 10}</p>
                  </div>
                  <div>
                    <p className="text-sm text-slate-500 mb-1">Cost Price</p>
                    <p className="font-medium text-slate-900">{formatCurrency(product.cost_price)}</p>
                  </div>
                </div>
                {modules?.enable_advanced_ims && (
                  <div className="pt-4 border-t flex gap-6">
                    <div className="flex items-center gap-2">
                        <Badge variant={product.track_batches ? "default" : "secondary"}>
                           {product.track_batches ? "Tracking Batches" : "No Batch Tracking"}
                        </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                        <Badge variant={product.track_serials ? "default" : "secondary"}>
                           {product.track_serials ? "Serialized" : "No Serial Tracking"}
                        </Badge>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardHeader>
              <CardTitle>Stock Audit Trail</CardTitle>
              <CardDescription>Comprehensive history of all stock movements for this product.</CardDescription>
            </CardHeader>
            <CardContent>
              {movements.length === 0 ? (
                <div className="text-center py-12 text-slate-500">
                  <History className="mx-auto h-8 w-8 mb-3 opacity-20" />
                  <p>No stock movements recorded yet</p>
                </div>
              ) : (
                <div className="rounded-md border border-slate-200">
                  <Table>
                    <TableHeader className="bg-slate-50">
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Reference</TableHead>
                        <TableHead className="text-right">Qty In</TableHead>
                        <TableHead className="text-right">Qty Out</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {movements.map((mov) => (
                        <TableRow key={mov.id}>
                          <TableCell className="text-slate-600">{formatDate(mov.date)}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className="capitalize">
                              {mov.ref_type.replace('_', ' ')}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-slate-500 text-sm">
                            {mov.ref_id.substring(0, 8)}...
                          </TableCell>
                          <TableCell className="text-right">
                            {mov.quantity_in > 0 ? (
                              <span className="text-emerald-600 font-medium">+{mov.quantity_in}</span>
                            ) : "-"}
                          </TableCell>
                          <TableCell className="text-right">
                            {mov.quantity_out > 0 ? (
                              <span className="text-rose-600 font-medium">-{mov.quantity_out}</span>
                            ) : "-"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        
        {modules?.enable_advanced_ims && product.track_batches && (
          <TabsContent value="batches">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div>
                  <CardTitle>Batches</CardTitle>
                  <CardDescription>Manage active product batches and expirations.</CardDescription>
                </div>
                {batches.length > 0 && (
                  <Button variant="outline" size="sm" onClick={() => handlePrintLabels('batch')} disabled={printing}>
                    {printing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Printer className="h-4 w-4 mr-2" />}
                    Print Newest Batch
                  </Button>
                )}
              </CardHeader>
              <CardContent>
                {batches.length === 0 ? (
                  <div className="text-center py-12 text-slate-500">
                    <Layers className="mx-auto h-8 w-8 mb-3 opacity-20" />
                    <p>No batches recorded</p>
                  </div>
                ) : (
                  <div className="rounded-md border border-slate-200">
                    <Table>
                        <TableHeader className="bg-slate-50">
                        <TableRow>
                            <TableHead>Batch #</TableHead>
                            <TableHead>Qty Received</TableHead>
                            <TableHead>Mfg Date</TableHead>
                            <TableHead>Expiry Date</TableHead>
                        </TableRow>
                        </TableHeader>
                        <TableBody>
                        {batches.map((b) => (
                            <TableRow key={b.id}>
                            <TableCell className="font-medium">{b.batch_number}</TableCell>
                            <TableCell>{b.quantity}</TableCell>
                            <TableCell>{formatDate(b.manufacturing_date) || "-"}</TableCell>
                            <TableCell>{formatDate(b.expiry_date) || "-"}</TableCell>
                            </TableRow>
                        ))}
                        </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        )}

        {modules?.enable_advanced_ims && product.track_serials && (
          <TabsContent value="serials">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div>
                  <CardTitle>Serial Numbers</CardTitle>
                  <CardDescription>Track unique individual units.</CardDescription>
                </div>
                {serials.length > 0 && (
                  <Button variant="outline" size="sm" onClick={() => handlePrintLabels('serial')} disabled={printing}>
                    {printing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Printer className="h-4 w-4 mr-2" />}
                    Print In-Stock Serials
                  </Button>
                )}
              </CardHeader>
              <CardContent>
                {serials.length === 0 ? (
                  <div className="text-center py-12 text-slate-500">
                    <Hash className="mx-auto h-8 w-8 mb-3 opacity-20" />
                    <p>No serial numbers recorded</p>
                  </div>
                ) : (
                  <div className="rounded-md border border-slate-200">
                    <Table>
                        <TableHeader className="bg-slate-50">
                        <TableRow>
                            <TableHead>Serial Number</TableHead>
                            <TableHead>Batch</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Date Added</TableHead>
                        </TableRow>
                        </TableHeader>
                        <TableBody>
                        {serials.map((s) => (
                            <TableRow key={s.id}>
                            <TableCell className="font-mono">{s.serial_number}</TableCell>
                            <TableCell className="text-slate-500 text-sm">{s.batch_id || "-"}</TableCell>
                            <TableCell>
                                <Badge variant={s.status === "IN_STOCK" ? "default" : "secondary"}>
                                  {s.status.replace("_", " ")}
                                </Badge>
                            </TableCell>
                            <TableCell className="text-slate-500">{formatDate(s.created_at)}</TableCell>
                            </TableRow>
                        ))}
                        </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        )}

      </Tabs>
    </div>
  );
};

export default ProductDetail;
