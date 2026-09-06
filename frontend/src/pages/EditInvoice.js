import React, { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getInvoice, getProducts, updateInvoice, formatCurrency } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Alert, AlertDescription } from "../components/ui/alert";
import { SearchableProductSelect } from "../components/SearchableProductSelect";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { ArrowLeft, Plus, Trash2, Loader2, Package, Info } from "lucide-react";

const EditInvoice = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [invoice, setInvoice] = useState(null);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    date: "",
    notes: "",
    items: [],
  });

  useEffect(() => {
    fetchData();
  }, [id]);

  const fetchData = async () => {
    // Clear stale form data immediately so navigating between
    // /invoices/A/edit -> /invoices/B/edit doesn't show A's items
    // for a frame while B is loading.
    setLoading(true);
    setInvoice(null);
    setFormData({ date: "", notes: "", items: [] });
    try {
      const [invoiceRes, productsRes] = await Promise.all([
        getInvoice(id),
        getProducts({ item_type: 'finished_good' }),
      ]);

      setInvoice(invoiceRes.data);
      setProducts(productsRes.data);
      setFormData({
        date: invoiceRes.data.date,
        notes: invoiceRes.data.notes || "",
        items: invoiceRes.data.items.map((item) => ({
          product_id: item.product_id || "manual_entry",
          description: item.description,
          quantity: item.quantity,
          rate: item.rate,
        })),
      });
    } catch (error) {
      toast.error("Failed to load invoice");
      navigate("/invoices");
    } finally {
      setLoading(false);
    }
  };

  const handleAddItem = () => {
    setFormData((prev) => ({
      ...prev,
      items: [...prev.items, { product_id: "", description: "", quantity: 1, rate: 0 }],
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
        const updatedItem = { ...item, [field]: field === "quantity" || field === "rate" ? parseFloat(value) || 0 : value };

        if (field === "product_id" && value) {
          const product = products.find((p) => p.id === value);
          if (product) {
            updatedItem.description = product.name;
            updatedItem.rate = product.selling_price;
          }
        }

        if (field === "description" && item.product_id) {
          const product = products.find((p) => p.id === item.product_id);
          if (product && value !== product.name) {
            updatedItem.product_id = "";
          }
        }

        return updatedItem;
      }),
    }));
  };

  const calculateTotal = () => {
    return formData.items.reduce((sum, item) => sum + item.quantity * item.rate, 0);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const validItems = formData.items.filter((item) => item.description && item.rate > 0);
    if (validItems.length === 0) {
      toast.error("Please add at least one item");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        date: formData.date,
        notes: formData.notes || null,
        items: validItems.map((item) => ({
          product_id: (item.product_id && item.product_id !== "manual_entry") ? item.product_id : null,
          description: item.description,
          quantity: item.quantity,
          rate: item.rate,
        })),
      };

      const response = await updateInvoice(id, payload);

      let message = "Invoice updated successfully!";
      if (response.data.credit_applied > 0) {
        message += ` ${formatCurrency(response.data.credit_applied)} customer credit applied.`;
      }
      toast.success(message);

      if (response.data.stock_warnings?.length > 0) {
        toast.warning(response.data.warning_message, {
          description: response.data.stock_warnings.map((w) => `${w.product}: ${w.current_stock} in stock`).join(", "),
        });
      }

      navigate(`/invoices/${id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to update invoice");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  const isDraft = invoice?.status === "draft";

  return (
    <div className="max-w-3xl mx-auto animate-fade-in" data-testid="edit-invoice-page">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <Button variant="ghost" size="icon" aria-label="Back to invoice" onClick={() => navigate(`/invoices/${id}`)}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">
            Edit Invoice {invoice?.invoice_number}
          </h1>
          <p className="text-slate-500 mt-1">
            {isDraft ? "Edit your draft invoice" : "Update invoice details"}
          </p>
        </div>
      </div>

      {!isDraft && (
        <Alert className="mb-6 bg-blue-50 border-blue-200">
          <Info className="h-4 w-4 text-blue-600" />
          <AlertDescription className="text-blue-700">
            Editing this invoice will automatically update stock and balances.
          </AlertDescription>
        </Alert>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Invoice Info */}
        <Card>
          <CardContent className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label>Customer</Label>
                <Input value={invoice?.customer_name} disabled className="bg-slate-50" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="date">Invoice Date</Label>
                <Input
                  id="date"
                  type="date"
                  value={formData.date}
                  onChange={(e) => setFormData((prev) => ({ ...prev, date: e.target.value }))}
                  data-testid="edit-invoice-date-input"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Line Items */}
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-lg">Items</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {formData.items.map((item, index) => (
              <div key={index} className="grid grid-cols-12 gap-3 items-end p-4 bg-slate-50 rounded-lg">
                <div className="col-span-12 md:col-span-5 space-y-2">
                  <Label className="text-xs text-slate-500">Product or Description</Label>
                  <div className="space-y-2">
                    <SearchableProductSelect
                      products={products}
                      value={item.product_id || "manual_entry"}
                      onValueChange={(value) => handleItemChange(index, "product_id", value)}
                      includeManual={true}
                      placeholder="Search product (optional)"
                    />
                    <Input
                      value={item.description}
                      onChange={(e) => handleItemChange(index, "description", e.target.value)}
                      placeholder="Item description"
                      data-testid={`edit-item-description-${index}`}
                    />
                  </div>
                </div>

                <div className="col-span-4 md:col-span-2 space-y-2">
                  <Label className="text-xs text-slate-500">Qty</Label>
                  <Input
                    type="number" inputMode="decimal"
                    min="0"
                    step="0.01"
                    value={item.quantity}
                    onChange={(e) => handleItemChange(index, "quantity", e.target.value)}
                    className="font-mono"
                    data-testid={`edit-item-qty-${index}`}
                  />
                </div>

                <div className="col-span-4 md:col-span-2 space-y-2">
                  <Label className="text-xs text-slate-500">Rate</Label>
                  <div className="relative">
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-sm">₹</span>
                    <Input
                      type="number" inputMode="decimal"
                      min="0"
                      step="0.01"
                      value={item.rate}
                      onChange={(e) => handleItemChange(index, "rate", e.target.value)}
                      className="pl-6 font-mono"
                      data-testid={`edit-item-rate-${index}`}
                    />
                  </div>
                </div>

                <div className="col-span-3 md:col-span-2 space-y-2">
                  <Label className="text-xs text-slate-500">Amount</Label>
                  <div className="h-10 flex items-center font-mono font-medium text-slate-900">
                    {formatCurrency(item.quantity * item.rate)}
                  </div>
                </div>

                <div className="col-span-1 flex justify-end">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon" aria-label="Remove this line item"
                    onClick={() => handleRemoveItem(index)}
                    disabled={formData.items.length === 1}
                    className="text-slate-400 hover:text-red-600"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}

            <Button type="button" variant="outline" onClick={handleAddItem} className="w-full" data-testid="edit-add-item-btn">
              <Plus className="h-4 w-4 mr-2" />
              Add Item
            </Button>
          </CardContent>
        </Card>

        {/* Notes & Total */}
        <Card>
          <CardContent className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label htmlFor="notes">Notes (Optional)</Label>
                <Textarea
                  id="notes"
                  value={formData.notes}
                  onChange={(e) => setFormData((prev) => ({ ...prev, notes: e.target.value }))}
                  placeholder="Any additional notes..."
                  rows={3}
                  data-testid="edit-invoice-notes-input"
                />
              </div>

              <div className="flex flex-col justify-end">
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="flex justify-between items-center pt-2">
                    <span className="font-semibold">Total</span>
                    <span className="text-xl font-bold font-mono text-brand-600">
                      {formatCurrency(calculateTotal())}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <Button type="button" variant="outline" onClick={() => navigate(`/invoices/${id}`)}>
            Cancel
          </Button>
          <Button type="submit" className="bg-brand-600 hover:bg-brand-700" disabled={saving} data-testid="update-invoice-btn">
            {saving ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Updating...</>
            ) : (
              "Update Invoice"
            )}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default EditInvoice;
