import React, { useState, useEffect } from "react";
import {
    getCreditNotes, createCreditNote, deleteCreditNote,
    getCustomers, getProducts, formatCurrency, formatDate
} from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent } from "../components/ui/card";
import {
    Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from "../components/ui/dialog";
import {
    Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "../components/ui/table";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../components/ui/select";
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import {
    AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../components/ui/alert-dialog";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { Plus, RotateCcw, Loader2, MoreHorizontal, Trash2, X } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { UIFilters } from "../components/UIFilters";

const CreditNotes = () => {
    const [notes, setNotes] = useState([]);
    const [customers, setCustomers] = useState([]);
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [noteToDelete, setNoteToDelete] = useState(null);
    const [search, setSearch] = useState("");
    const [dateRange, setDateRange] = useState(undefined);

    const [formData, setFormData] = useState({
        customer_id: "",
        reason: "",
        date: new Date().toISOString().split("T")[0],
        items: [{ product_id: "", description: "", quantity: 1, rate: 0 }],
    });

    useEffect(() => {
        fetchAll();
    }, [dateRange]);

    const fetchAll = async () => {
        try {
            setLoading(true);
            const startDate = dateRange?.from ? dateRange.from.toISOString().split('T')[0] : null;
            const endDate = dateRange?.to ? dateRange.to.toISOString().split('T')[0] : null;

            const [notesRes, custRes, prodRes] = await Promise.all([
                getCreditNotes(startDate, endDate), getCustomers(), getProducts()
            ]);
            setNotes(notesRes.data);
            setCustomers(custRes.data);
            setProducts(prodRes.data);
        } catch (error) {
            toast.error("Failed to load data");
        } finally {
            setLoading(false);
        }
    };

    const resetForm = () => {
        setFormData({
            customer_id: "",
            reason: "",
            date: new Date().toISOString().split("T")[0],
            items: [{ product_id: "", description: "", quantity: 1, rate: 0 }],
        });
    };

    const addItem = () => {
        setFormData((prev) => ({
            ...prev,
            items: [...prev.items, { product_id: "", description: "", quantity: 1, rate: 0 }],
        }));
    };

    const removeItem = (index) => {
        if (formData.items.length <= 1) return;
        setFormData((prev) => ({
            ...prev,
            items: prev.items.filter((_, i) => i !== index),
        }));
    };

    const updateItem = (index, field, value) => {
        setFormData((prev) => {
            const items = [...prev.items];
            items[index] = { ...items[index], [field]: value };
            if (field === "product_id" && value) {
                const product = products.find((p) => p.id === value);
                if (product) {
                    items[index].description = product.name;
                    items[index].rate = product.selling_price || 0;
                }
            }
            return { ...prev, items };
        });
    };

    const getTotal = () =>
        formData.items.reduce((sum, item) => sum + item.quantity * item.rate, 0);

    const handleDeleteClick = (note) => {
        setNoteToDelete(note);
        setDeleteDialogOpen(true);
    };

    const confirmDelete = async () => {
        if (!noteToDelete) return;
        try {
            await deleteCreditNote(noteToDelete.id);
            toast.success("Credit Note deleted & effects reversed");
            fetchAll();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to delete");
        } finally {
            setDeleteDialogOpen(false);
            setNoteToDelete(null);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!formData.customer_id) { toast.error("Please select a customer"); return; }
        if (formData.items.some((i) => !i.description || i.quantity <= 0 || i.rate <= 0)) {
            toast.error("Fill in all item details"); return;
        }
        setSaving(true);
        try {
            await createCreditNote({
                customer_id: formData.customer_id,
                items: formData.items.map((i) => ({
                    product_id: i.product_id || null,
                    description: i.description,
                    quantity: parseFloat(i.quantity),
                    rate: parseFloat(i.rate),
                })),
                reason: formData.reason || null,
                date: formData.date,
            });
            toast.success("Credit Note created!");
            setDialogOpen(false);
            resetForm();
            fetchAll();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to create Credit Note");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="space-y-6 animate-fade-in" data-testid="credit-notes-page">
            <PageHeader
                title="Credit Notes"
                description="Sales returns — issue credits to customers"
                action={
                    <Button onClick={() => setDialogOpen(true)} className="bg-brand-600 hover:bg-brand-700" data-testid="add-credit-note-btn">
                        <Plus className="h-4 w-4 mr-2" /> New Credit Note
                    </Button>
                }
            />

            <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
                <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>Create Credit Note</DialogTitle>
                        <DialogDescription>Issue a credit for returned goods or adjustments</DialogDescription>
                    </DialogHeader>
                    <form onSubmit={handleSubmit} className="space-y-4 mt-4">
                        <div className="space-y-2">
                            <Label>Customer *</Label>
                            <Select value={formData.customer_id} onValueChange={(v) => setFormData((p) => ({ ...p, customer_id: v }))}>
                                <SelectTrigger><SelectValue placeholder="Select customer" /></SelectTrigger>
                                <SelectContent>
                                    {customers.map((c) => (
                                        <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-2">
                            <Label>Reason</Label>
                            <Input value={formData.reason} onChange={(e) => setFormData((p) => ({ ...p, reason: e.target.value }))} placeholder="e.g. Defective goods returned" />
                        </div>

                        <div className="space-y-2">
                            <Label>Date</Label>
                            <Input type="date" value={formData.date} onChange={(e) => setFormData((p) => ({ ...p, date: e.target.value }))} />
                        </div>

                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <Label>Items</Label>
                                <Button type="button" variant="outline" size="sm" onClick={addItem}>
                                    <Plus className="h-3 w-3 mr-1" /> Add Item
                                </Button>
                            </div>
                            {formData.items.map((item, index) => (
                                <div key={index} className="p-3 border rounded-lg space-y-3 bg-slate-50">
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-medium text-slate-500">Item {index + 1}</span>
                                        {formData.items.length > 1 && (
                                            <Button type="button" variant="ghost" size="sm" className="h-6 w-6 p-0 text-slate-400 hover:text-red-500" onClick={() => removeItem(index)}>
                                                <X className="h-3 w-3" />
                                            </Button>
                                        )}
                                    </div>
                                    <Select value={item.product_id} onValueChange={(v) => updateItem(index, "product_id", v)}>
                                        <SelectTrigger><SelectValue placeholder="Select product (optional)" /></SelectTrigger>
                                        <SelectContent>
                                            {products.map((p) => (
                                                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Input placeholder="Description" value={item.description} onChange={(e) => updateItem(index, "description", e.target.value)} />
                                    <div className="grid grid-cols-2 gap-2">
                                        <div>
                                            <Label className="text-xs">Qty</Label>
                                            <Input type="number" min="1" value={item.quantity} onChange={(e) => updateItem(index, "quantity", e.target.value)} />
                                        </div>
                                        <div>
                                            <Label className="text-xs">Rate (₹)</Label>
                                            <Input type="number" min="0" step="0.01" value={item.rate} onChange={(e) => updateItem(index, "rate", e.target.value)} />
                                        </div>
                                    </div>
                                </div>
                            ))}
                            <div className="text-right font-medium text-slate-700">
                                Total: <span className="font-mono text-brand-700">{formatCurrency(getTotal())}</span>
                            </div>
                        </div>

                        <div className="flex justify-end gap-3 pt-4">
                            <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                            <Button type="submit" className="bg-brand-600 hover:bg-brand-700" disabled={saving}>
                                {saving ? (<><Loader2 className="mr-2 h-4 w-4 animate-spin" />Creating...</>) : "Create Credit Note"}
                            </Button>
                        </div>
                    </form>
                </DialogContent>
            </Dialog>


            {/* Delete Alert Dialog */}
            <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Credit Note?</AlertDialogTitle>
                        <AlertDialogDescription>
                            This will delete credit note {noteToDelete?.credit_note_number} of {noteToDelete && formatCurrency(noteToDelete.total)} and reverse all stock & ledger effects. This cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={confirmDelete} className="bg-red-600 hover:bg-red-700">Delete</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            {/* Search & Filter */}
            <UIFilters
                search={search}
                setSearch={setSearch}
                searchPlaceholder="Search credit notes..."
                dateRange={dateRange}
                setDateRange={setDateRange}
                onClear={() => {
                    setSearch("");
                    setDateRange(undefined);
                }}
            />

            {/* Table */}
            {
                loading ? (
                    <div className="space-y-4">{[...Array(5)].map((_, i) => (<Skeleton key={i} className="h-12 w-full" />))}</div>
                ) : (() => {
                    const filtered = notes.filter((n) => {
                        const q = search.toLowerCase();
                        return !q || n.credit_note_number?.toLowerCase().includes(q) || n.customer_name?.toLowerCase().includes(q) || n.reason?.toLowerCase().includes(q);
                    });
                    return filtered.length > 0 ? (
                        <Card>
                            <CardContent className="p-0">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>CN #</TableHead>
                                            <TableHead>Customer</TableHead>
                                            <TableHead>Date</TableHead>
                                            <TableHead>Reason</TableHead>
                                            <TableHead className="text-right">Amount</TableHead>
                                            <TableHead className="w-[80px]"></TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {filtered.map((note) => (
                                            <TableRow key={note.id}>
                                                <TableCell className="font-medium font-mono">{note.credit_note_number}</TableCell>
                                                <TableCell>{note.customer_name}</TableCell>
                                                <TableCell className="text-slate-500">{formatDate(note.date)}</TableCell>
                                                <TableCell className="text-slate-500 max-w-[200px] truncate">{note.reason || "—"}</TableCell>
                                                <TableCell className="text-right font-mono font-medium text-orange-600">-{formatCurrency(note.total)}</TableCell>
                                                <TableCell>
                                                    <DropdownMenu>
                                                        <DropdownMenuTrigger asChild>
                                                            <Button variant="ghost" className="h-8 w-8 p-0"><MoreHorizontal className="h-4 w-4" /></Button>
                                                        </DropdownMenuTrigger>
                                                        <DropdownMenuContent align="end">
                                                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                                            <DropdownMenuSeparator />
                                                            <DropdownMenuItem onClick={() => handleDeleteClick(note)} className="text-red-600 focus:text-red-600">
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
                                <RotateCcw className="h-12 w-12 text-slate-300 mb-4" />
                                <h3 className="text-lg font-medium text-slate-900 mb-1">No credit notes found</h3>
                                <p className="text-slate-500 text-sm mb-4">{search ? "Try adjusting your search" : "Issue a credit note when a customer returns goods"}</p>
                                <Button onClick={() => setDialogOpen(true)} className="bg-brand-600 hover:bg-brand-700">
                                    <Plus className="h-4 w-4 mr-2" /> New Credit Note
                                </Button>
                            </CardContent>
                        </Card>
                    );
                })()
            }

        </div >
    );
};

export default CreditNotes;
