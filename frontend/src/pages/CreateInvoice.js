import React, { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getCustomers, getProducts, createInvoice, formatCurrency } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Checkbox } from "../components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Alert, AlertDescription } from "../components/ui/alert";
import { toast } from "sonner";
import { ArrowLeft, Plus, Trash2, Loader2, Package, AlertTriangle, Info } from "lucide-react";

const CreateInvoice = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedCustomer = searchParams.get("customer");

  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    customer_id: preselectedCustomer || "",
    date: new Date().toISOString().split("T")[0],
    notes: "",
    is_draft: false,
    items: [{ product_id: "", description: "", quantity: 1, rate: 0 }],
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [customersRes, productsRes] = await Promise.all([
        getCustomers(),
        getProducts(),
      ]);
      setCustomers(customersRes.data);
      setProducts(productsRes.data);
    } catch (error) {
      toast.error("Failed to load data");
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

        // Auto-fill when product is selected
        if (field === "product_id" && value) {
          const product = products.find((p) => p.id === value);
          if (product) {
            updatedItem.description = product.name;
            updatedItem.rate = product.selling_price;
          }
        }

        // Clear product_id if description is manually changed
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

    if (!formData.customer_id) {
      toast.error("Please select a customer");
      return;
    }

    const validItems = formData.items.filter((item) => item.description && item.rate > 0);
    if (validItems.length === 0) {
      toast.error("Please add at least one item");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        customer_id: formData.customer_id,
        date: formData.date,
        notes: formData.notes || null,
        is_draft: formData.is_draft,
        items: validItems.map((item) => ({
          product_id: (item.product_id && item.product_id !== "manual_entry") ? item.product_id : null,
          description: item.description,
          quantity: item.quantity,
          rate: item.rate,
        })),
      };

      const response = await createInvoice(payload);

      let message = `Invoice ${response.data.invoice_number} created!`;
      if (response.data.credit_applied > 0) {
        message += ` ${formatCurrency(response.data.credit_applied)} customer credit applied automatically.`;
      }
      toast.success(message);

      if (response.data.stock_warnings?.length > 0) {
        toast.warning(response.data.warning_message, {
          description: response.data.stock_warnings.map((w) => `${w.product}: ${w.current_stock} in stock`).join(", "),
        });
      }

      navigate(`/invoices/${response.data.id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to create invoice");
    } finally {
      setSaving(false);
    }
  };

  const selectedCustomer = customers.find((c) => c.id === formData.customer_id);

  return (
    <div className="max-w-3xl mx-auto animate-fade-in" data-testid="create-invoice-page">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <Button variant="ghost" size="icon" onClick={() => navigate("/invoices")}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">Create Invoice</h1>
          <p className="text-slate-500 mt-1">Add items and generate a new invoice</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Customer & Date */}
        <Card>
          <CardContent className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label>Customer *</Label>
                <Select
                  value={formData.customer_id}
                  onValueChange={(value) => setFormData((prev) => ({ ...prev, customer_id: value }))}
                  disabled={loading}
                >
                  <SelectTrigger data-testid="invoice-customer-select">
                    <SelectValue placeholder="Select customer" />
                  </SelectTrigger>
                  <SelectContent>
                    {customers.map((customer) => (
                      <SelectItem key={customer.id} value={customer.id}>
                        {customer.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedCustomer?.credit > 0 && (
                  <p className="text-xs text-emerald-600 flex items-center gap-1">
                    <Info className="h-3 w-3" />
                    {formatCurrency(selectedCustomer.credit)} credit will be auto-applied
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="date">Invoice Date</Label>
                <Input
                  id="date"
                  type="date"
                  value={formData.date}
                  onChange={(e) => setFormData((prev) => ({ ...prev, date: e.target.value }))}
                  data-testid="invoice-date-input"
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
                    <Select
                      value={item.product_id || "manual_entry"}
                      onValueChange={(value) => handleItemChange(index, "product_id", value)}
                    >
                      <SelectTrigger data-testid={`item-product-${index}`}>
                        <SelectValue placeholder="Select product (optional)" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="manual_entry">Free text item</SelectItem>
                        {products.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            <div className="flex items-center gap-2">
                              <Package className="h-3 w-3 text-slate-400" />
                              {p.name}
                              <span className="text-xs text-slate-400">({p.current_stock} in stock)</span>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      value={item.description}
                      onChange={(e) => handleItemChange(index, "description", e.target.value)}
                      placeholder="Item description"
                      data-testid={`item-description-${index}`}
                    />
                  </div>
                </div>

                <div className="col-span-4 md:col-span-2 space-y-2">
                  <Label className="text-xs text-slate-500">Qty</Label>
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    value={item.quantity}
                    onChange={(e) => handleItemChange(index, "quantity", e.target.value)}
                    className="font-mono"
                    data-testid={`item-qty-${index}`}
                  />
                </div>

                <div className="col-span-4 md:col-span-2 space-y-2">
                  <Label className="text-xs text-slate-500">Rate</Label>
                  <div className="relative">
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-sm">₹</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={item.rate}
                      onChange={(e) => handleItemChange(index, "rate", e.target.value)}
                      className="pl-6 font-mono"
                      data-testid={`item-rate-${index}`}
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
                    size="icon"
                    onClick={() => handleRemoveItem(index)}
                    disabled={formData.items.length === 1}
                    className="text-slate-400 hover:text-red-600"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}

            <Button type="button" variant="outline" onClick={handleAddItem} className="w-full" data-testid="add-item-btn">
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
                  data-testid="invoice-notes-input"
                />

                <div className="flex items-center space-x-2 pt-2">
                  <Checkbox
                    id="is_draft"
                    checked={formData.is_draft}
                    onCheckedChange={(checked) => setFormData((prev) => ({ ...prev, is_draft: checked }))}
                    data-testid="invoice-draft-checkbox"
                  />
                  <Label htmlFor="is_draft" className="text-sm text-slate-600 cursor-pointer">
                    Save as draft (won't affect stock or balances)
                  </Label>
                </div>
              </div>

              <div className="flex flex-col justify-end">
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm text-slate-500">Subtotal</span>
                    <span className="font-mono">{formatCurrency(calculateTotal())}</span>
                  </div>
                  {selectedCustomer?.credit > 0 && !formData.is_draft && (
                    <div className="flex justify-between items-center mb-2 text-emerald-600">
                      <span className="text-sm">Credit to apply</span>
                      <span className="font-mono">
                        -{formatCurrency(Math.min(selectedCustomer.credit, calculateTotal()))}
                      </span>
                    </div>
                  )}
                  <div className="flex justify-between items-center pt-2 border-t border-slate-200">
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
          <Button type="button" variant="outline" onClick={() => navigate("/invoices")}>
            Cancel
          </Button>
          <Button type="submit" className="bg-brand-600 hover:bg-brand-700" disabled={saving} data-testid="save-invoice-btn">
            {saving ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Creating...</>
            ) : formData.is_draft ? (
              "Save Draft"
            ) : (
              "Create Invoice"
            )}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default CreateInvoice;
