import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useModules } from "../context/ModulesContext";
import { getCustomers, getProducts, createInvoice, formatCurrency, parseInvoiceImage, getCustomerLedger } from "../lib/api";
import { levenshteinDistance } from "../lib/utils";
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
import { ArrowLeft, Plus, Trash2, Loader2, Package, AlertTriangle, Info, Camera, Upload, ScanLine } from "lucide-react";
import BarcodeScanner from '../components/LazyBarcodeScanner';
import { SearchableProductSelect } from '../components/SearchableProductSelect';

const CreateInvoice = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedCustomer = searchParams.get("customer");

  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [scannerOpen, setScannerOpen] = useState(false);
  const fileInputRef = useRef(null);
  const fileInputCameraRef = useRef(null);
  const { modules } = useModules();
  const [formData, setFormData] = useState({
    customer_id: preselectedCustomer || "",
    date: new Date().toISOString().split("T")[0],
    notes: "",
    is_draft: false,
    items: [{ product_id: "", description: "", quantity: 1, rate: 0, batch_id: "", serial_numbers_text: "" }],
    apply_credit: false
  });
  const [customerBalance, setCustomerBalance] = useState(0);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [customersRes, productsRes] = await Promise.all([
        getCustomers(),
        getProducts({ item_type: 'finished_good' }),
      ]);
      setCustomers(customersRes.data);
      setProducts(productsRes.data);
      if (preselectedCustomer) {
        fetchCustomerBalance(preselectedCustomer);
      }
    } catch (error) {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  };



  const fetchCustomerBalance = async (customerId) => {
    if (!customerId) {
      setCustomerBalance(0);
      return;
    }
    try {
      const res = await getCustomerLedger(customerId);
      // If balance is negative, it means they have credit (we owe them)
      setCustomerBalance(res.data.current_balance);

      // Auto-check if credit exists? No, let user decide.
      // But if we change customer, reset checkbox?
      setFormData(prev => ({ ...prev, apply_credit: false }));
    } catch (err) {
      console.error("Failed to fetch balance", err);
    }
  };

  const handleAddItem = () => {
    setFormData((prev) => ({
      ...prev,
      items: [...prev.items, { product_id: "", description: "", quantity: 1, rate: 0, batch_id: "", serial_numbers_text: "" }],
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
        attachment_url: formData.attachment_url || null,
        items: validItems.map((item) => {
          const payloadItem = {
            product_id: (item.product_id && item.product_id !== "manual_entry") ? item.product_id : null,
            description: item.description,
            quantity: item.quantity,
            rate: item.rate,
          };
          if (item.batch_id && item.batch_id.trim() !== '') {
            payloadItem.batch_id = item.batch_id.trim();
          }
          if (item.serial_numbers_text && item.serial_numbers_text.trim() !== '') {
            payloadItem.serial_numbers = item.serial_numbers_text.split(',').map(s => s.trim()).filter(s => s);
          }
          return payloadItem;
        }),
        apply_credit: formData.apply_credit
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

  const handleCameraClick = () => {
    fileInputCameraRef.current?.click();
  };

  const findBestProduct = (searchTerm) => {
    if (!searchTerm || !products.length) return null;
    const normalizedSearch = searchTerm.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();
    if (!normalizedSearch) return null;

    let bestMatch = null;
    let bestScore = 0;

    for (const product of products) {
      const normalizedProduct = product.name.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();

      // 1. Exact Match
      if (normalizedProduct === normalizedSearch) return product;

      // 2. Contains Match (High confidence)
      if (normalizedProduct.includes(normalizedSearch) || normalizedSearch.includes(normalizedProduct)) {
        // Prefer the one with closer length ratio
        const score = 0.9 - (Math.abs(normalizedProduct.length - normalizedSearch.length) / Math.max(normalizedProduct.length, normalizedSearch.length)) * 0.1;
        if (score > bestScore) {
          bestScore = score;
          bestMatch = product;
        }
        continue;
      }

      // 3. Levenshtein Distance (Fuzzy)
      const dist = levenshteinDistance(normalizedProduct, normalizedSearch);
      const maxLength = Math.max(normalizedProduct.length, normalizedSearch.length);
      const score = 1 - (dist / maxLength);

      if (score > bestScore) {
        bestScore = score;
        bestMatch = product;
      }
    }

    // Threshold for "Try Hard" matching - let's set it to 0.4 (40% similarity) to be very aggressive as requested
    // "try hard to match the handwritten spelling closest to the product"
    if (bestScore > 0.4) {
      return bestMatch;
    }
    return null;
  };

  const handleImageUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      toast.error('Please upload an image file');
      return;
    }

    setParsing(true);
    try {
      const response = await parseInvoiceImage(file);
      const parsed = response.data;

      let customerId = '';

      // Try to find customer match
      // Fallback to supplier_name if customer_name is not found, as AI might misclassify the main name on a handwritten note
      const detectedName = parsed.customer_name || parsed.party_name || parsed.supplier_name;
      if (detectedName) {
        const normalize = (str) => str.toLowerCase().replace(/[^a-z0-9]/g, "");
        const searchName = normalize(detectedName);

        const match = customers.find(c => {
          const cName = normalize(c.name);
          return cName.includes(searchName) || searchName.includes(cName);
        });

        if (match) {
          customerId = match.id;
          toast.success(`Matched Customer: ${match.name}`);
        } else {
          // Find "Other" as fallback
          const otherCustomer = customers.find(c => c.name.toLowerCase() === 'other');
          if (otherCustomer) customerId = otherCustomer.id;
          toast.info(`Customer '${detectedName}' not found.`);
        }
      } else {
        // Default to Other if no name found
        const otherCustomer = customers.find(c => c.name.toLowerCase() === 'other');
        if (otherCustomer) customerId = otherCustomer.id;
      }

      // Map parsed items to products
      const mappedItems = (parsed.items || []).map(item => {
        const matchedProduct = findBestProduct(item.description);

        if (matchedProduct) {
          return {
            product_id: matchedProduct.id,
            description: matchedProduct.name, // Use product name to ensure consistency
            quantity: item.quantity || 1,
            rate: matchedProduct.selling_price || item.rate || 0 // Prefer system price, fallback to parsed
          };
        } else {
          return {
            product_id: "",
            description: item.description || "Unknown Item",
            quantity: item.quantity || 1,
            rate: item.rate || 0
          };
        }
      });

      if (mappedItems.length === 0) {
        mappedItems.push({ product_id: "", description: "", quantity: 1, rate: 0 });
      }

      // Map parsed data to form
      setFormData({
        customer_id: customerId,
        date: parsed.date || new Date().toISOString().split("T")[0],
        notes: parsed.notes || '',
        is_draft: false,
        items: mappedItems,
        attachment_url: parsed.attachment_url || "",
        apply_credit: false
      });

      if (customerId) {
        fetchCustomerBalance(customerId);
      }

      toast.success(`✨ Invoice parsed! ${parsed.items?.length || 0} items found`);
      if (parsed.attachment_url) toast.info("Image attached to invoice");

    } catch (error) {
      console.error('Parse error:', error);
      toast.error(error.response?.data?.detail || 'Failed to parse invoice. Please try again.');
    } finally {
      setParsing(false);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      if (fileInputCameraRef.current) {
        fileInputCameraRef.current.value = '';
      }
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
        if (newItems.length === 1 && !newItems[0].product_id && !newItems[0].description) {
          newItems = [];
        }
        
        let existingItemIndex = bat || ser 
          ? newItems.findIndex(i => i.product_id === prd && i.batch_id === bat)
          : newItems.findIndex(i => i.product_id === prd);
        
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
            description: product.name,
            quantity: 1,
            rate: product.selling_price || 0,
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

  const selectedCustomer = customers.find((c) => c.id === formData.customer_id);


  return (
    <div className="max-w-3xl mx-auto animate-fade-in" data-testid="create-invoice-page">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate("/invoices")}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold font-heading text-slate-900">Create Invoice</h1>
            <p className="text-slate-500 mt-1">Add items and generate a new invoice</p>
          </div>
        </div>

        {/* AI Upload Button */}
        <div className="flex items-center gap-2">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleImageUpload}
            accept="image/*"
            className="hidden"
            disabled={parsing}
          />
          <input
            type="file"
            ref={fileInputCameraRef}
            onChange={handleImageUpload}
            accept="image/*"
            capture="environment"
            className="hidden"
            disabled={parsing}
          />
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={parsing}
              className="gap-2"
            >
              {parsing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Parsing...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4" />
                  Upload Bill
                </>
              )}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={handleCameraClick}
              disabled={parsing}
              className="gap-2 hidden md:flex"
            >
              <Camera className="h-4 w-4" />
              Take Photo
            </Button>
          </div>
          {formData.attachment_url && (
            <div className="text-sm text-emerald-600 flex items-center gap-1 mt-2">
              <Info className="h-4 w-4" />
              <a href={`${process.env.REACT_APP_BACKEND_URL}${formData.attachment_url}`} target="_blank" rel="noopener noreferrer" className="underline">
                View Attached Bill
              </a>
            </div>
          )}
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
                  onValueChange={(value) => {
                    setFormData((prev) => ({ ...prev, customer_id: value }));
                    fetchCustomerBalance(value);
                  }}
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
                {customerBalance < 0 && (
                  <div className="flex items-center space-x-2 mt-2 p-2 bg-green-50 text-green-700 rounded-md">
                    <Checkbox
                      id="apply_credit"
                      checked={formData.apply_credit}
                      onCheckedChange={(checked) => setFormData(prev => ({ ...prev, apply_credit: checked }))}
                    />
                    <label
                      htmlFor="apply_credit"
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                    >
                      Apply available credit of {formatCurrency(Math.abs(customerBalance))}
                    </label>
                  </div>
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
            {formData.items.map((item, index) => {
              const selectedProduct = products.find(p => p.id === item.product_id);
              const showBatch = modules?.enable_advanced_ims && selectedProduct?.track_batches;
              const showSerials = modules?.enable_advanced_ims && selectedProduct?.track_serials;

              return (
                <div key={index} className="grid grid-cols-12 gap-3 p-4 bg-slate-50 rounded-lg border border-slate-100 mb-2">
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
                      className="text-slate-400 hover:text-red-600 mt-6"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>

                  {(showBatch || showSerials) && (
                    <div className="col-span-12 grid grid-cols-12 gap-2 mt-2 pt-2 border-t border-slate-200 border-dashed">
                      {showBatch && (
                        <div className="col-span-12 md:col-span-4 space-y-1">
                          <Label className="text-xs text-brand-600">Sell from Batch</Label>
                          <Input value={item.batch_id} onChange={(e) => handleItemChange(index, "batch_id", e.target.value)} placeholder="e.g. BATCH-001" className="text-sm" />
                        </div>
                      )}
                      {showSerials && (
                        <div className={`col-span-12 ${showBatch ? 'md:col-span-8' : 'md:col-span-12'} space-y-1`}>
                          <Label className="text-xs text-brand-600">Select Serial Numbers to Sell</Label>
                          <Input value={item.serial_numbers_text} onChange={(e) => handleItemChange(index, "serial_numbers_text", e.target.value)} placeholder="SN1001, SN1002..." className="text-sm font-mono" />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            <div className="flex flex-col sm:flex-row gap-2">
              <Button type="button" variant="outline" onClick={handleAddItem} className="w-full" data-testid="add-item-btn">
                <Plus className="h-4 w-4 mr-2" />
                Add Item
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

      <BarcodeScanner 
        open={scannerOpen} 
        onScan={handleScan} 
        onClose={() => setScannerOpen(false)} 
      />
    </div>
  );
};

export default CreateInvoice;
