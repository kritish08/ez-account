import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { getCustomers, createCustomer, formatCurrency } from "../lib/api";
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
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { Plus, Search, Users, Phone, Loader2, ChevronRight } from "lucide-react";

const Customers = () => {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    phone: "",
    address: "",
    gstin: "",
    opening_balance: 0,
    balance_type: "debit",
  });

  useEffect(() => {
    fetchCustomers();
  }, []);

  const fetchCustomers = async () => {
    try {
      const response = await getCustomers();
      setCustomers(response.data);
    } catch (error) {
      toast.error("Failed to load customers");
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    const { name, value, type } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "number" ? parseFloat(value) || 0 : value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name) {
      toast.error("Customer name is required");
      return;
    }

    setSaving(true);
    try {
      await createCustomer(formData);
      toast.success("Customer added successfully");
      setDialogOpen(false);
      setFormData({
        name: "",
        phone: "",
        address: "",
        gstin: "",
        opening_balance: 0,
        balance_type: "debit",
      });
      fetchCustomers();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to add customer");
    } finally {
      setSaving(false);
    }
  };

  const filteredCustomers = customers.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.phone?.includes(search)
  );

  return (
    <div className="space-y-6 animate-fade-in" data-testid="customers-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">Customers</h1>
          <p className="text-slate-500 mt-1">Manage your customers and their balances</p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="bg-brand-600 hover:bg-brand-700" data-testid="add-customer-btn">
              <Plus className="h-4 w-4 mr-2" />
              Add Customer
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Add New Customer</DialogTitle>
              <DialogDescription>Enter customer details below</DialogDescription>
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
                  name="gstin"
                  value={formData.gstin}
                  onChange={handleChange}
                  placeholder="Tax ID"
                  data-testid="customer-gstin-input"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="opening_balance">Opening Balance</Label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono">₹</span>
                    <Input
                      id="opening_balance"
                      name="opening_balance"
                      type="number"
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
                      Saving...
                    </>
                  ) : (
                    "Add Customer"
                  )}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Search */}
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

      {/* Customers Table */}
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
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead className="text-right">Outstanding</TableHead>
                  <TableHead className="text-right">Credit</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredCustomers.map((customer) => (
                  <TableRow key={customer.id} data-testid={`customer-row-${customer.id}`}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-brand-50 flex items-center justify-center">
                          <span className="text-sm font-medium text-brand-700">
                            {customer.name.charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <div>
                          <p className="font-medium text-slate-900">{customer.name}</p>
                          {customer.address && (
                            <p className="text-sm text-slate-500 truncate max-w-[200px]">
                              {customer.address}
                            </p>
                          )}
                        </div>
                      </div>
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
                      <Link to={`/customers/${customer.id}`}>
                        <Button variant="ghost" size="sm">
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </Link>
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
            <Users className="h-12 w-12 text-slate-300 mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-1">No customers yet</h3>
            <p className="text-slate-500 text-sm mb-4">Add your first customer to get started</p>
            <Button
              onClick={() => setDialogOpen(true)}
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
