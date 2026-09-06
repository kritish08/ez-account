import React, { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getBusiness, setupBusiness } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { toast } from "sonner";
import { Loader2, Building2, Sparkles } from "lucide-react";

const Setup = () => {
  const location = useLocation();
  const isFirstRun = Boolean(location.state?.firstRun);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [formData, setFormData] = useState({
    name: "",
    address: "",
    phone: "",
    email: "",
    gstin: "",
    financial_year_start: "April",
    opening_cash: 0,
    opening_bank: 0,
  });

  useEffect(() => {
    fetchBusiness();
  }, []);

  const fetchBusiness = async () => {
    try {
      const response = await getBusiness();
      if (response.data) {
        setFormData({
          name: response.data.name || "",
          address: response.data.address || "",
          phone: response.data.phone || "",
          email: response.data.email || "",
          gstin: response.data.gstin || "",
          financial_year_start: response.data.financial_year_start || "April",
          opening_cash: response.data.opening_cash || 0,
          opening_bank: response.data.opening_bank || 0,
        });
      }
    } catch (error) {
      // No existing business, that's fine
    } finally {
      setFetching(false);
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
      toast.error("Business name is required");
      return;
    }

    setLoading(true);
    try {
      await setupBusiness(formData);
      toast.success("Business setup complete!");
      navigate("/");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save business details");
    } finally {
      setLoading(false);
    }
  };

  if (fetching) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-brand-600" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto animate-fade-in">
      {/* Explain the redirect. Being dropped somewhere you didn't ask to go
          is disorienting unless the page says why you're there and what
          happens next. */}
      {isFirstRun && (
        <div className="mb-6 rounded-lg border border-brand-200 bg-brand-50 p-4">
          <div className="flex gap-3">
            <Sparkles className="h-5 w-5 shrink-0 text-brand-600" />
            <div className="text-sm">
              <p className="font-semibold text-brand-900">Let's set up your business</p>
              <p className="mt-1 text-brand-800">
                This takes a minute and only happens once. Your business name and
                address go on every invoice you send, and the cash and bank
                amounts you enter here are your starting balances — get these
                right and your reports will be right from day one.
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="mb-8">
        <h1 className="text-2xl font-bold font-heading text-slate-900">Business Setup</h1>
        <p className="text-slate-500 mt-1">Configure your business details</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-brand-600" />
            Business Information
          </CardTitle>
          <CardDescription>
            This information will appear on your invoices and reports
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="name">Business Name *</Label>
                <Input
                  id="name"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  placeholder="Your Business Name"
                  data-testid="business-name-input"
                />
              </div>

              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="address">Address</Label>
                <Input
                  id="address"
                  name="address"
                  value={formData.address}
                  onChange={handleChange}
                  placeholder="Business address"
                  data-testid="business-address-input"
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
                  data-testid="business-phone-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="business@example.com"
                  data-testid="business-email-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="gstin">GSTIN (Optional)</Label>
                <Input
                  id="gstin"
                  autoCapitalize="characters"
                  autoCorrect="off"
                  spellCheck={false}
                  name="gstin"
                  value={formData.gstin}
                  onChange={handleChange}
                  placeholder="22AAAAA0000A1Z5"
                  data-testid="business-gstin-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="financial_year_start">Financial Year Starts</Label>
                <Input
                  id="financial_year_start"
                  name="financial_year_start"
                  value={formData.financial_year_start}
                  disabled
                  className="bg-slate-50"
                />
              </div>
            </div>

            <div className="border-t border-slate-200 pt-6">
              <h3 className="text-sm font-medium text-slate-900 mb-4">Opening Balances</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="opening_cash">Cash in Hand</Label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono">₹</span>
                    <Input
                      id="opening_cash"
                      name="opening_cash"
                      type="number" inputMode="decimal"
                      step="0.01"
                      value={formData.opening_cash}
                      onChange={handleChange}
                      className="pl-8 font-mono"
                      data-testid="opening-cash-input"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="opening_bank">Bank Balance</Label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono">₹</span>
                    <Input
                      id="opening_bank"
                      name="opening_bank"
                      type="number" inputMode="decimal"
                      step="0.01"
                      value={formData.opening_bank}
                      onChange={handleChange}
                      className="pl-8 font-mono"
                      data-testid="opening-bank-input"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-4">
              <Button type="button" variant="outline" onClick={() => navigate("/")}>
                Cancel
              </Button>
              <Button
                type="submit"
                className="bg-brand-600 hover:bg-brand-700"
                disabled={loading}
                data-testid="save-business-btn"
              >
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  "Save Business"
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

export default Setup;
