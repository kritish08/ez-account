import React, { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getCustomer, getCustomerLedger, formatCurrency, formatDate } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";
import {
  ArrowLeft,
  Phone,
  MapPin,
  CreditCard,
  TrendingUp,
  TrendingDown,
  FileText,
  Plus,
} from "lucide-react";

const CustomerDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [customer, setCustomer] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [id]);

  const fetchData = async () => {
    try {
      const [customerRes, ledgerRes] = await Promise.all([
        getCustomer(id),
        getCustomerLedger(id),
      ]);
      setCustomer(customerRes.data);
      setLedger(ledgerRes.data.ledger || []);
    } catch (error) {
      toast.error("Failed to load customer details");
      navigate("/customers");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (!customer) {
    return null;
  }

  return (
    <div className="space-y-6 animate-fade-in" data-testid="customer-detail-page">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate("/customers")}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold font-heading text-slate-900">{customer.name}</h1>
          <div className="flex items-center gap-4 mt-1 text-sm text-slate-500">
            {customer.phone && (
              <span className="flex items-center gap-1">
                <Phone className="h-3 w-3" />
                {customer.phone}
              </span>
            )}
            {customer.address && (
              <span className="flex items-center gap-1">
                <MapPin className="h-3 w-3" />
                {customer.address}
              </span>
            )}
          </div>
        </div>
        <Link to={`/invoices/new?customer=${id}`}>
          <Button className="bg-brand-600 hover:bg-brand-700" data-testid="new-invoice-for-customer-btn">
            <Plus className="h-4 w-4 mr-2" />
            New Invoice
          </Button>
        </Link>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-amber-50 rounded-lg">
                <TrendingUp className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500">Outstanding</p>
                <p className="text-2xl font-bold font-mono text-amber-600">
                  {formatCurrency(customer.outstanding)}
                </p>
                <p className="text-xs text-slate-400">Amount to collect</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-emerald-50 rounded-lg">
                <CreditCard className="h-5 w-5 text-emerald-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500">Available Credit</p>
                <p className="text-2xl font-bold font-mono text-emerald-600">
                  {formatCurrency(customer.credit)}
                </p>
                <p className="text-xs text-slate-400">Advance balance</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-slate-100 rounded-lg">
                <FileText className="h-5 w-5 text-slate-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500">GSTIN</p>
                <p className="text-lg font-medium text-slate-900">
                  {customer.gstin || "Not provided"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Ledger */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Transaction History</CardTitle>
        </CardHeader>
        <CardContent>
          {ledger.length > 0 ? (
            <div className="space-y-3">
              {ledger.map((entry, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-4 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div
                      className={`p-2 rounded-lg ${
                        entry.type === "sale"
                          ? "bg-blue-50"
                          : entry.type === "payment"
                          ? "bg-emerald-50"
                          : entry.type === "credit_added"
                          ? "bg-indigo-50"
                          : "bg-amber-50"
                      }`}
                    >
                      {entry.type === "sale" ? (
                        <FileText className="h-4 w-4 text-blue-600" />
                      ) : entry.type === "payment" ? (
                        <TrendingDown className="h-4 w-4 text-emerald-600" />
                      ) : (
                        <CreditCard className="h-4 w-4 text-indigo-600" />
                      )}
                    </div>
                    <div>
                      <p className="font-medium text-sm text-slate-900">{entry.description}</p>
                      <p className="text-xs text-slate-500">{formatDate(entry.date)}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p
                      className={`font-mono font-medium ${
                        entry.type === "payment" || entry.type === "credit_used"
                          ? "text-emerald-600"
                          : "text-slate-900"
                      }`}
                    >
                      {entry.type === "payment" ? "-" : ""}
                      {formatCurrency(entry.amount)}
                    </p>
                    <p className="text-xs text-slate-400 font-mono">
                      Bal: {formatCurrency(entry.balance)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-slate-500">
              <FileText className="h-12 w-12 mx-auto mb-4 text-slate-300" />
              <p>No transactions yet</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default CustomerDetail;
