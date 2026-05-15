import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useModules } from "../context/ModulesContext";
import {
  getProductionOrders, getProductionOrder, createProductionOrder,
  startProductionOrder, completeProductionOrder, cancelProductionOrder, sendToQC,
  getProducts, getProductBOM, saveProductBOM
} from "../lib/api";
import { Button } from "../components/ui/button";
import { SearchableProductSelect } from "../components/SearchableProductSelect";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription
} from "../components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle
} from "../components/ui/alert-dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from "../components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from "../components/ui/select";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import {
  Plus, Loader2, Play, CheckCircle2, XCircle, ClipboardList,
  Package, Layers, ChevronDown, ChevronRight, AlertTriangle, ArrowLeft,
  RefreshCw, FlaskConical, Factory
} from "lucide-react";

const STATUS_COLORS = {
  PLANNED:     "bg-slate-100 text-slate-700 border-slate-200",
  IN_PROGRESS: "bg-blue-100 text-blue-700 border-blue-200",
  QC:          "bg-amber-100 text-amber-700 border-amber-200",
  COMPLETED:   "bg-emerald-100 text-emerald-700 border-emerald-200",
  CANCELLED:   "bg-red-100 text-red-600 border-red-200",
};

const ProductionOrders = () => {
  const { modules } = useModules();
  const navigate = useNavigate();

  const [orders, setOrders] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);
  const [filterStatus, setFilterStatus] = useState("all");

  // Create Dialog
  const [createOpen, setCreateOpen] = useState(false);
  const [formData, setFormData] = useState({ product_id: "", quantity: 1, batch_id: "", notes: "", planned_start_date: "" });
  const [bom, setBom] = useState(null);
  const [bomLoading, setBomLoading] = useState(false);

  // Detail Dialog
  const [detailOrder, setDetailOrder] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null); // {type, orderId}

  // BOM Builder Dialog
  const [bomBuilderOpen, setBomBuilderOpen] = useState(false);
  const [bomBuilderProduct, setBomBuilderProduct] = useState(null);
  const [bomComponents, setBomComponents] = useState([]);
  const [bomSaving, setBomSaving] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [ordersRes, productsRes] = await Promise.all([
        getProductionOrders(filterStatus !== "all" ? { status: filterStatus } : {}),
        getProducts()
      ]);
      setOrders(ordersRes.data);
      setProducts(productsRes.data);
    } catch (err) {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [filterStatus]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const finishedGoods = products.filter(p => p.item_type === "finished_good" || !p.item_type);
  const rawMaterials = products.filter(p => p.item_type === "raw_material" || p.item_type === "wip");

  const handleProductSelect = async (productId) => {
    setFormData(prev => ({ ...prev, product_id: productId }));
    setBom(null);
    if (!productId) return;
    setBomLoading(true);
    try {
      const res = await getProductBOM(productId);
      setBom(res.data.bom);
    } catch (err) { /* no bom yet */ }
    finally { setBomLoading(false); }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!formData.product_id) return toast.error("Select a product to produce");
    if (!formData.quantity || formData.quantity <= 0) return toast.error("Enter a valid quantity");
    setSaving(true);
    try {
      await createProductionOrder({
        product_id: formData.product_id,
        quantity: parseFloat(formData.quantity),
        batch_id: formData.batch_id || null,
        notes: formData.notes,
        planned_start_date: formData.planned_start_date || null
      });
      toast.success("Work Order created!");
      setCreateOpen(false);
      setFormData({ product_id: "", quantity: 1, batch_id: "", notes: "", planned_start_date: "" });
      setBom(null);
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create work order");
    } finally {
      setSaving(false);
    }
  };

  const handleOpenDetail = async (orderId) => {
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      const res = await getProductionOrder(orderId);
      setDetailOrder(res.data);
    } catch (err) {
      toast.error("Failed to load order details");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleAction = async () => {
    if (!confirmAction) return;
    setActionLoading(confirmAction.orderId);
    setConfirmAction(null);
    try {
      if (confirmAction.type === "start") {
        await startProductionOrder(confirmAction.orderId);
        toast.success("Work order started. Raw materials consumed.");
      } else if (confirmAction.type === "qc") {
        await sendToQC(confirmAction.orderId);
        toast.success("Order moved to QC review.");
      } else if (confirmAction.type === "complete") {
        await completeProductionOrder(confirmAction.orderId);
        toast.success("Work order completed. Finished goods added to stock!");
      } else if (confirmAction.type === "cancel") {
        await cancelProductionOrder(confirmAction.orderId);
        toast.success("Work order cancelled.");
      }
      setDetailOpen(false);
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Action failed");
    } finally {
      setActionLoading(null);
    }
  };

  // BOM Builder
  const openBomBuilder = async (product) => {
    setBomBuilderProduct(product);
    setBomBuilderOpen(true);
    try {
      const res = await getProductBOM(product.id);
      if (res.data.bom) {
        setBomComponents(res.data.bom.components.map(c => ({
          material_id: c.material_id,
          quantity: c.quantity,
          unit: c.unit || ""
        })));
      } else {
        setBomComponents([{ material_id: "", quantity: 1, unit: "pcs" }]);
      }
    } catch {
      setBomComponents([{ material_id: "", quantity: 1, unit: "pcs" }]);
    }
  };

  const handleSaveBOM = async () => {
    const valid = bomComponents.filter(c => c.material_id && c.quantity > 0);
    if (valid.length === 0) return toast.error("Add at least one component");
    setBomSaving(true);
    try {
      await saveProductBOM(bomBuilderProduct.id, { components: valid });
      toast.success(`BOM saved for ${bomBuilderProduct.name}`);
      setBomBuilderOpen(false);
    } catch (err) {
      toast.error("Failed to save BOM");
    } finally {
      setBomSaving(false);
    }
  };

  const filteredOrders = filterStatus === "all" ? orders : orders.filter(o => o.status === filterStatus);

  if (!modules?.enable_production) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-slate-500 animate-fade-in">
        <div className="w-16 h-16 bg-violet-100 rounded-2xl flex items-center justify-center">
          <Factory className="h-8 w-8 text-violet-500" />
        </div>
        <h2 className="text-xl font-bold text-slate-800">Production Module is Disabled</h2>
        <p className="text-sm text-center max-w-sm">Enable the Production Module in Settings to track work orders, Bills of Materials, and raw material consumption.</p>
        <Button onClick={() => navigate("/settings")} variant="outline">
          Go to Settings
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900 flex items-center gap-2">
            <Factory className="h-6 w-6 text-violet-600" />
            Production Orders
          </h1>
          <p className="text-slate-500 mt-1">Manage work orders, track raw material consumption and finished good output</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setBomBuilderOpen(true)} className="border-violet-200 text-violet-700 hover:bg-violet-50">
            <FlaskConical className="h-4 w-4 mr-2" />
            Manage BOMs
          </Button>
          <Button className="bg-violet-600 hover:bg-violet-700" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            New Work Order
          </Button>
        </div>
      </div>

      {/* Status Filter */}
      <div className="flex gap-2 flex-wrap">
        {["all", "PLANNED", "IN_PROGRESS", "QC", "COMPLETED", "CANCELLED"].map(s => (
          <Button
            key={s}
            variant={filterStatus === s ? "default" : "outline"}
            size="sm"
            onClick={() => setFilterStatus(s)}
            className={filterStatus === s ? "bg-violet-600 hover:bg-violet-700" : ""}
          >
            {s === "all" ? "All Orders" : s.replace("_", " ")}
          </Button>
        ))}
      </div>

      {/* Orders Table */}
      {loading ? (
        <Card><CardContent className="p-6 space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-12 w-full" />)}</CardContent></Card>
      ) : filteredOrders.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 gap-4">
            <ClipboardList className="h-12 w-12 text-slate-300" />
            <h3 className="text-lg font-medium text-slate-700">No work orders {filterStatus !== "all" ? `with status "${filterStatus.replace("_"," ")}"` : "yet"}</h3>
            <Button className="bg-violet-600 hover:bg-violet-700" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4 mr-2" /> Create First Work Order
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Order #</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead>Output Batch</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredOrders.map(order => (
                  <TableRow key={order.id} className="cursor-pointer hover:bg-slate-50" onClick={() => handleOpenDetail(order.id)}>
                    <TableCell className="font-mono font-medium text-violet-700">{order.order_number}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Package className="h-4 w-4 text-slate-400" />
                        <span className="font-medium">{order.product_name}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono">{order.quantity}</TableCell>
                    <TableCell className="text-slate-500 font-mono text-sm">{order.batch_id || "—"}</TableCell>
                    <TableCell>
                      <Badge className={`border ${STATUS_COLORS[order.status] || ""} bg-transparent`}>
                        {order.status.replace("_", " ")}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-slate-500 text-sm">{order.created_at?.split("T")[0]}</TableCell>
                    <TableCell>
                      {actionLoading === order.id && <Loader2 className="h-4 w-4 animate-spin text-violet-600" />}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* ── Create Work Order Dialog ── */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Factory className="h-5 w-5 text-violet-600" />
              New Work Order
            </DialogTitle>
            <DialogDescription>Plan a production run. Raw materials will be consumed when you start the order.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4 mt-2">
            <div className="space-y-2">
              <Label>Finished Product *</Label>
              <SearchableProductSelect
                products={products.filter(p => !["raw_material", "consumable", "service"].includes(p.item_type))}
                value={formData.product_id}
                onValueChange={handleProductSelect}
                placeholder="Select product to produce..."
                itemType="finished_good"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Quantity to Produce *</Label>
                <Input type="number" min="1" step="1" value={formData.quantity}
                  onChange={e => setFormData(prev => ({...prev, quantity: e.target.value}))} />
              </div>
              <div className="space-y-2">
                <Label>Output Batch ID (optional)</Label>
                <Input value={formData.batch_id}
                  onChange={e => setFormData(prev => ({...prev, batch_id: e.target.value}))}
                  placeholder="e.g. FG-2024-01" />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Planned Start Date</Label>
              <Input type="date" value={formData.planned_start_date}
                onChange={e => setFormData(prev => ({...prev, planned_start_date: e.target.value}))} />
            </div>

            {/* BOM Preview */}
            {formData.product_id && (
              <div className="rounded-lg border border-violet-100 bg-violet-50 p-3">
                <p className="text-xs font-semibold text-violet-700 mb-2 uppercase tracking-wide">Bill of Materials Preview</p>
                {bomLoading ? (
                  <p className="text-sm text-slate-500">Loading BOM…</p>
                ) : !bom ? (
                  <p className="text-sm text-amber-600 flex items-center gap-1">
                    <AlertTriangle className="h-3.5 w-3.5" /> No BOM defined yet — add one via "Manage BOMs"
                  </p>
                ) : (
                  <div className="space-y-1">
                    {bom.components.map((c, i) => (
                      <div key={i} className="flex items-center justify-between text-sm">
                        <span className="text-slate-700">{c.material_name}</span>
                        <span className={`font-mono font-medium ${c.sufficient ? "text-emerald-600" : "text-red-600"}`}>
                          {c.quantity * formData.quantity} {c.material_unit}
                          {!c.sufficient && <span className="ml-1 text-xs">(only {c.current_stock} available)</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="space-y-2">
              <Label>Notes</Label>
              <Textarea value={formData.notes} onChange={e => setFormData(prev => ({...prev, notes: e.target.value}))}
                placeholder="Production notes…" rows={2} />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button type="submit" className="bg-violet-600 hover:bg-violet-700" disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                Create Order
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Order Detail Dialog ── */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ClipboardList className="h-5 w-5 text-violet-600" />
              {detailOrder?.order_number} — {detailOrder?.product_name}
            </DialogTitle>
            <DialogDescription>
              Work Order Details
            </DialogDescription>
          </DialogHeader>
          {detailLoading ? (
            <div className="space-y-3 py-4"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-2/3" /></div>
          ) : detailOrder && (
            <div className="space-y-4">
              {/* Status + Meta */}
              <div className="flex flex-wrap gap-4 text-sm">
                <div>
                  <span className="text-slate-500">Status: </span>
                  <Badge className={`border ${STATUS_COLORS[detailOrder.status] || ""} bg-transparent ml-1`}>
                    {detailOrder.status.replace("_", " ")}
                  </Badge>
                </div>
                <div><span className="text-slate-500">Quantity:</span> <span className="font-mono font-bold">{detailOrder.quantity}</span></div>
                {detailOrder.batch_id && <div><span className="text-slate-500">Output Batch:</span> <span className="font-mono text-emerald-600">{detailOrder.batch_id}</span></div>}
                {detailOrder.planned_start_date && <div><span className="text-slate-500">Planned:</span> {detailOrder.planned_start_date}</div>}
                {detailOrder.started_at && <div><span className="text-slate-500">Started:</span> {detailOrder.started_at?.split("T")[0]}</div>}
                {detailOrder.completed_at && <div><span className="text-slate-500">Completed:</span> {detailOrder.completed_at?.split("T")[0]}</div>}
              </div>

              {/* Ingredients */}
              {detailOrder.ingredients?.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Raw Materials</p>
                  <div className="rounded-lg border border-slate-200 overflow-hidden">
                    <Table>
                      <TableHeader className="bg-slate-50">
                        <TableRow>
                          <TableHead>Material</TableHead>
                          <TableHead className="text-right">Required</TableHead>
                          <TableHead className="text-right">Available</TableHead>
                          <TableHead className="text-right">Consumed</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {detailOrder.ingredients.map((ing, i) => (
                          <TableRow key={i}>
                            <TableCell className="font-medium">{ing.material_name}</TableCell>
                            <TableCell className="text-right font-mono">{ing.quantity_required}</TableCell>
                            <TableCell className={`text-right font-mono ${ing.current_stock >= ing.quantity_required ? "text-emerald-600" : "text-red-600"}`}>
                              {ing.current_stock}
                              {ing.current_stock < ing.quantity_required && (
                                <AlertTriangle className="h-3.5 w-3.5 inline-block ml-1" />
                              )}
                            </TableCell>
                            <TableCell className="text-right font-mono text-slate-500">{ing.quantity_consumed}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}

              {detailOrder.notes && (
                <div><p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Notes</p><p className="text-sm text-slate-700">{detailOrder.notes}</p></div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100">
                {detailOrder.status === "PLANNED" && (
                  <Button className="bg-blue-600 hover:bg-blue-700" onClick={() => setConfirmAction({ type: "start", orderId: detailOrder.id })}>
                    <Play className="h-4 w-4 mr-2" /> Start & Consume Materials
                  </Button>
                )}
                {detailOrder.status === "IN_PROGRESS" && (
                  <Button className="bg-amber-600 hover:bg-amber-700" onClick={() => setConfirmAction({ type: "qc", orderId: detailOrder.id })}>
                    <CheckCircle2 className="h-4 w-4 mr-2" /> Send to QC
                  </Button>
                )}
                {(detailOrder.status === "IN_PROGRESS" || detailOrder.status === "QC") && (
                  <Button className="bg-emerald-600 hover:bg-emerald-700" onClick={() => setConfirmAction({ type: "complete", orderId: detailOrder.id })}>
                    <CheckCircle2 className="h-4 w-4 mr-2" /> Mark Completed
                  </Button>
                )}
                {detailOrder.status !== "COMPLETED" && detailOrder.status !== "CANCELLED" && (
                  <Button variant="outline" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => setConfirmAction({ type: "cancel", orderId: detailOrder.id })}>
                    <XCircle className="h-4 w-4 mr-2" /> Cancel Order
                  </Button>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ── BOM Builder Dialog ── */}
      <Dialog open={bomBuilderOpen} onOpenChange={setBomBuilderOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FlaskConical className="h-5 w-5 text-violet-600" />
              Bill of Materials
            </DialogTitle>
            <DialogDescription>Define which raw materials are consumed to produce one unit of a finished good.</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 mt-2">
            {/* Product selector */}
            {!bomBuilderProduct ? (
              <div className="space-y-2">
                <Label>Select Finished Product</Label>
                <SearchableProductSelect
                  products={products.filter(p => !["raw_material", "consumable", "service"].includes(p.item_type))}
                  value=""
                  onValueChange={v => {
                    const p = products.find(x => x.id === v);
                    if (p) openBomBuilder(p);
                  }}
                  placeholder="Choose product..."
                  itemType="finished_good"
                />
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-800">
                    BOM for: <span className="text-violet-700">{bomBuilderProduct.name}</span>
                  </p>
                  <Button variant="ghost" size="sm" onClick={() => { setBomBuilderProduct(null); setBomComponents([]); }}>
                    Change
                  </Button>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs text-slate-500 uppercase tracking-wide">Components</Label>
                  {bomComponents.map((comp, idx) => (
                    <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                      <div className="col-span-6">
                        <SearchableProductSelect
                          products={products.filter(p => p.id !== bomBuilderProduct.id)}
                          value={comp.material_id}
                          onValueChange={v => {
                            const updated = [...bomComponents];
                            updated[idx].material_id = v;
                            setBomComponents(updated);
                          }}
                          placeholder="Material..."
                        />
                      </div>
                      <div className="col-span-3">
                        <Input type="number" min="0.001" step="0.001" value={comp.quantity} className="font-mono text-sm"
                          onChange={e => { const u = [...bomComponents]; u[idx].quantity = parseFloat(e.target.value) || 1; setBomComponents(u); }} />
                      </div>
                      <div className="col-span-2">
                        <Input value={comp.unit} placeholder="pcs" className="text-sm"
                          onChange={e => { const u = [...bomComponents]; u[idx].unit = e.target.value; setBomComponents(u); }} />
                      </div>
                      <div className="col-span-1">
                        <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-red-400 hover:text-red-600"
                          onClick={() => setBomComponents(prev => prev.filter((_, i) => i !== idx))}>
                          ×
                        </Button>
                      </div>
                    </div>
                  ))}
                  <Button type="button" variant="outline" size="sm" className="w-full"
                    onClick={() => setBomComponents(prev => [...prev, { material_id: "", quantity: 1, unit: "pcs" }])}>
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add Component
                  </Button>
                </div>

                <div className="flex justify-end gap-3 pt-2">
                  <Button variant="outline" onClick={() => setBomBuilderOpen(false)}>Cancel</Button>
                  <Button className="bg-violet-600 hover:bg-violet-700" onClick={handleSaveBOM} disabled={bomSaving}>
                    {bomSaving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                    Save BOM
                  </Button>
                </div>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Confirm Action Dialog ── */}
      <AlertDialog open={!!confirmAction} onOpenChange={() => setConfirmAction(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmAction?.type === "start" && "Start Work Order?"}
              {confirmAction?.type === "qc" && "Send to QC?"}
              {confirmAction?.type === "complete" && "Mark as Completed?"}
              {confirmAction?.type === "cancel" && "Cancel Work Order?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction?.type === "start" && "This will immediately deduct the required raw material quantities from your stock. This cannot be undone unless you cancel the order."}
              {confirmAction?.type === "qc" && "This will move the order to QC status. Materials have already been consumed. You can then complete or cancel the order after review."}
              {confirmAction?.type === "complete" && "This will add the finished good quantity to your stock and optionally assign it to the output batch."}
              {confirmAction?.type === "cancel" && "If the order was in progress or under QC, raw materials will be returned to stock."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Back</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleAction}
              className={confirmAction?.type === "cancel" ? "bg-red-600 hover:bg-red-700" : confirmAction?.type === "complete" ? "bg-emerald-600 hover:bg-emerald-700" : confirmAction?.type === "qc" ? "bg-amber-600 hover:bg-amber-700" : "bg-blue-600 hover:bg-blue-700"}
            >
              {confirmAction?.type === "start" && <><Play className="h-4 w-4 mr-2" />Start & Consume</>}
              {confirmAction?.type === "qc" && <><CheckCircle2 className="h-4 w-4 mr-2" />Send to QC</>}
              {confirmAction?.type === "complete" && <><CheckCircle2 className="h-4 w-4 mr-2" />Complete Order</>}
              {confirmAction?.type === "cancel" && <><XCircle className="h-4 w-4 mr-2" />Cancel Order</>}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default ProductionOrders;
