import React, { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getDebitNote, getPurchases, formatCurrency, formatDate } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import {
    ArrowLeft,
    FileText,
} from "lucide-react";

const DebitNoteDetail = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [debitNote, setDebitNote] = useState(null);
    const [utilizedPurchases, setUtilizedPurchases] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchData();
    }, [id]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const dnRes = await getDebitNote(id);
            setDebitNote(dnRes.data);

            // Fetch utilized purchases (Purchases for this supplier with debit_used > 0)
            if (dnRes.data.supplier_id) {
                // getPurchases(supplierId, debitUsedOnly)
                const purRes = await getPurchases(dnRes.data.supplier_id, true);
                setUtilizedPurchases(purRes.data);
            }
        } catch (error) {
            toast.error("Debit Note not found");
            navigate("/debit-notes");
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="space-y-6 max-w-3xl mx-auto">
                <Skeleton className="h-8 w-64" />
                <Skeleton className="h-96" />
            </div>
        );
    }

    if (!debitNote) return null;

    return (
        <div className="max-w-4xl mx-auto animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={() => navigate("/debit-notes")}>
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold font-heading text-slate-900">
                            {debitNote.debit_note_number}
                        </h1>
                        <p className="text-slate-500 mt-1">{debitNote.supplier_name}</p>
                    </div>
                </div>

                {/* Edit Button */}
                <div className="flex gap-2">
                    <Button variant="outline" onClick={() => navigate("/debit-notes", { state: { editId: id } })}>
                        <FileText className="h-4 w-4 mr-2" />
                        Edit
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {/* Main Details */}
                <div className="md:col-span-2 space-y-8">
                    <Card>
                        <CardContent className="p-8">
                            {/* Header */}
                            <div className="flex justify-between mb-8 pb-6 border-b border-slate-200">
                                <div>
                                    <h2 className="text-xl font-bold text-slate-900 mb-1">DEBIT NOTE</h2>
                                    <p className="text-sm text-slate-500">#{debitNote.debit_note_number}</p>
                                </div>
                                <div className="text-right">
                                    <p className="text-sm text-slate-500">Date</p>
                                    <p className="font-medium">{formatDate(debitNote.date)}</p>
                                </div>
                            </div>

                            {/* Items Table */}
                            <div className="mb-8">
                                <table className="w-full">
                                    <thead>
                                        <tr className="border-b border-slate-200">
                                            <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">Item</th>
                                            <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">Qty</th>
                                            <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">Cost</th>
                                            <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">Amount</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {debitNote.items.map((item, index) => (
                                            <tr key={index} className="border-b border-slate-100">
                                                <td className="py-4 text-slate-900">{item.product_name || item.description || "Item"}</td>
                                                <td className="py-4 text-right font-mono text-slate-600">{item.quantity}</td>
                                                <td className="py-4 text-right font-mono text-slate-600">{formatCurrency(item.cost_price)}</td>
                                                <td className="py-4 text-right font-mono font-medium text-slate-900">{formatCurrency(item.amount)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>

                            {/* Total */}
                            <div className="flex justify-end border-t border-slate-200 pt-4">
                                <div className="flex justify-between w-64">
                                    <span className="font-semibold text-slate-900">Total Debit</span>
                                    <span className="text-lg font-bold font-mono text-emerald-600">{formatCurrency(debitNote.total)}</span>
                                </div>
                            </div>

                            {debitNote.reason && (
                                <div className="mt-8 pt-6 border-t border-slate-200">
                                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Reason</p>
                                    <p className="text-sm text-slate-600">{debitNote.reason}</p>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Utilization History */}
                    <Card>
                        <CardContent className="p-8">
                            <h3 className="text-lg font-bold text-slate-900 mb-6">Utilization History</h3>
                            <p className="text-sm text-slate-500 mb-4">
                                Purchases from {debitNote.supplier_name} adjusted using debit notes.
                            </p>

                            {utilizedPurchases.length === 0 ? (
                                <p className="text-slate-500 italic">No debit utilization found.</p>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full">
                                        <thead>
                                            <tr className="border-b border-slate-200">
                                                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">Purchase</th>
                                                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">Date</th>
                                                <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">Total</th>
                                                <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">Debit Used</th>
                                                <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide pb-3">Status</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {utilizedPurchases.map((pur) => (
                                                <tr key={pur.id} className="border-b border-slate-100">
                                                    <td className="py-3 font-medium text-brand-600">{pur.purchase_number}</td>
                                                    <td className="py-3 text-slate-600">{formatDate(pur.date)}</td>
                                                    <td className="py-3 text-right font-mono text-slate-600">{formatCurrency(pur.total)}</td>
                                                    <td className="py-3 text-right font-mono text-emerald-600 font-medium">-{formatCurrency(pur.debit_used)}</td>
                                                    <td className="py-3 text-right">
                                                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${pur.payment_status === 'paid' ? 'bg-emerald-100 text-emerald-800' :
                                                                pur.payment_status === 'partially_paid' ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                                                            }`}>
                                                            {pur.payment_status?.replace('_', ' ') || "Unpaid"}
                                                        </span>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>

                {/* Sidebar */}
                <div className="space-y-6">
                    <Card>
                        <CardContent className="p-6">
                            <h3 className="text-sm font-medium text-slate-500 uppercase tracking-wide mb-4">Supplier Details</h3>
                            <p className="font-semibold text-slate-900">{debitNote.supplier_name}</p>
                            <Link to={`/suppliers/${debitNote.supplier_id}`} className="text-sm text-brand-600 hover:underline mt-2 block">
                                View Supplier Profile
                            </Link>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
};

export default DebitNoteDetail;
