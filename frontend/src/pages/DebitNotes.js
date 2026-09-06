import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
    getDebitNotes, createDebitNote, updateDebitNote, deleteDebitNote,
    getSuppliers, getProducts, formatCurrency, formatDate
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
import { Plus, Undo2, Loader2, MoreHorizontal, Trash2, X } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { UIFilters } from "../components/UIFilters";

const DebitNotes = () => {
    const [notes, setNotes] = useState([]);
    const [suppliers, setSuppliers] = useState([]);
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [noteToDelete, setNoteToDelete] = useState(null);
    const [search, setSearch] = useState("");
    const [dateRange, setDateRange] = useState(undefined);
    const [editingId, setEditingId] = useState(null);

    const [formData, setFormData] = useState({
        supplier_id: "",
        reason: "",
        date: new Date().toISOString().split("T")[0],
        items: [{ product_id: "", quantity: 1, cost_price: 0 }],
    });

    const [refreshKey, setRefreshKey] = useState(0);
    const refresh = () => setRefreshKey((k) => k + 1);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        const startDate = dateRange?.from ? dateRange.from.toISOString().split('T')[0] : null;
        const endDate = dateRange?.to ? dateRange.to.toISOString().split('T')[0] : null;
        Promise.all([getDebitNotes(startDate, endDate), getSuppliers(), getProducts()])
            .then(([notesRes, suppRes, prodRes]) => {
                if (!cancelled) {
                    setNotes(notesRes.data);
                    setSuppliers(suppRes.data);
                    setProducts(prodRes.data);
                }
            })
            .catch(() => toast.error("Failed to load data"))
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [refreshKey, dateRange]);

    const resetForm = () => {
        setFormData({
            supplier_id: "",
            reason: "",
            date: new Date().toISOString().split("T")[0],
            items: [{ product_id: "", quantity: 1, cost_price: 0 }],
        });
        setEditingId(null);
    };

    const addItem = () => {
        setFormData((prev) => ({
            ...prev,
            items: [...prev.items, { product_id: "", quantity: 1, cost_price: 0 }],
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
                    items[index].cost_price = product.cost_price || 0;
                }
            }
            return { ...prev, items };
        });
    };

    const getTotal = () =>
        formData.items.reduce((sum, item) => sum + item.quantity * item.cost_price, 0);

    const getProductName = (id) => {
        const p = products.find((pr) => pr.id === id);
        return p ? p.name : id;
    };

    const handleDeleteClick = (note) => {
        setNoteToDelete(note);
        setDeleteDialogOpen(true);
    };

    const handleEditClick = (note) => {
        setEditingId(note.id);
        setFormData({
            supplier_id: note.supplier_id,
            reason: note.reason || "",
            date: note.date,
            items: note.items.map(i => ({
                product_id: i.product_id,
                quantity: i.quantity,
                cost_price: i.cost_price
            }))
        });
        setDialogOpen(true);
    };

    const confirmDelete = async () => {
        // Optimistic delete
        setNotes((prev) => prev.filter((n) => n.id !== noteToDelete.id));
        setDeleteDialogOpen(false);
        const deleted = noteToDelete;
        setNoteToDelete(null);
        try {
            await deleteDebitNote(deleted.id);
            toast.success("Debit Note deleted & effects reversed");
            refresh();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to delete");
            refresh();
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!formData.supplier_id) { toast.error("Please select a supplier"); return; }
        if (formData.items.some((i) => !i.product_id || i.quantity <= 0 || i.cost_price <= 0)) {
            toast.error("Fill in all item details"); return;
        }
        setSaving(true);
        try {
            const payload = {
                supplier_id: formData.supplier_id,
                items: formData.items.map((i) => ({
                    product_id: i.product_id,
                    quantity: parseFloat(i.quantity),
                    cost_price: parseFloat(i.cost_price),
                })),
                reason: formData.reason || null,
                date: formData.date,
            };

            if (editingId) {
                await updateDebitNote(editingId, payload);
                toast.success("Debit Note updated!");
            } else {
                await createDebitNote(payload);
                toast.success("Debit Note created!");
            }

            setDialogOpen(false);
            resetForm();
            refresh();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to save Debit Note");
            refresh();
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="space-y-6 animate-fade-in" data-testid="debit-notes-page">
            <PageHeader
                title="Debit Notes"
                description="Purchase returns — return goods to suppliers"
                action={
                    <Button onClick={() => setDialogOpen(true)} className="bg-brand-600 hover:bg-brand-700" data-testid="add-debit-note-btn">
                        <Plus className="h-4 w-4 mr-2" /> New Debit Note
                    </Button>
                }
            />

            <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
                <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>{editingId ? "Edit Debit Note" : "Create Debit Note"}</DialogTitle>
                        <DialogDescription>Return goods to a supplier to reduce your payable</DialogDescription>
                    </DialogHeader>
                    <form onSubmit={handleSubmit} className="space-y-4 mt-4">
                        <div className="space-y-2">
                            <Label>Supplier *</Label>
                            <Select value={formData.supplier_id} onValueChange={(v) => setFormData((p) => ({ ...p, supplier_id: v }))}>
                                <SelectTrigger><SelectValue placeholder="Select supplier" /></SelectTrigger>
                                <SelectContent>
                                    {suppliers.map((s) => (
                                        <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <Select value={formData.supplier_id} onValueChange={(v) => setFormData((p) => ({ ...p, supplier_id: v }))} disabled={!!editingId}>
                                <SelectTrigger><SelectValue placeholder="Select supplier" /></SelectTrigger>
                                <SelectContent>
                                    {suppliers.map((s) => (
                                        <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
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
                                        <SelectTrigger><SelectValue placeholder="Select product *" /></SelectTrigger>
                                        <SelectContent>
                                            {products.map((p) => (
                                                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <div className="grid grid-cols-2 gap-2">
                                        <div>
                                            <Label className="text-xs">Qty</Label>
                                            <Input type="number" inputMode="decimal" min="1" value={item.quantity} onChange={(e) => updateItem(index, "quantity", e.target.value)} />
                                        </div>
                                        <div>
                                            <Label className="text-xs">Cost Price (₹)</Label>
                                            <Input type="number" inputMode="decimal" min="0" step="0.01" value={item.cost_price} onChange={(e) => updateItem(index, "cost_price", e.target.value)} />
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
                                {saving ? (<><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</>) : (editingId ? "Update Debit Note" : "Create Debit Note")}
                            </Button>
                        </div>
                    </form>
                </DialogContent>
            </Dialog>


            {/* Delete Alert Dialog */}
            <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Debit Note?</AlertDialogTitle>
                        <AlertDialogDescription>
                            This will delete debit note {noteToDelete?.debit_note_number} of {noteToDelete && formatCurrency(noteToDelete.total)} and reverse all stock & ledger effects. This cannot be undone.
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
                searchPlaceholder="Search debit notes..."
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
                        return !q || n.debit_note_number?.toLowerCase().includes(q) || n.supplier_name?.toLowerCase().includes(q) || n.reason?.toLowerCase().includes(q);
                    });
                    return filtered.length > 0 ? (
                        <Card>
                            <CardContent className="p-0">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>DN #</TableHead>
                                            <TableHead>Supplier</TableHead>
                                            <TableHead>Date</TableHead>
                                            <TableHead>Reason</TableHead>
                                            <TableHead className="text-right">Amount</TableHead>
                                            <TableHead className="w-[80px]"></TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {filtered.map((note) => (
                                            <TableRow key={note.id}>
                                                <TableCell className="font-medium font-mono">
                                                    <Link to={`/debit-notes/${note.id}`} className="text-brand-600 hover:underline">
                                                        {note.debit_note_number}
                                                    </Link>
                                                </TableCell>
                                                <TableCell>{note.supplier_name}</TableCell>
                                                <TableCell className="text-slate-500">{formatDate(note.date)}</TableCell>
                                                <TableCell className="text-slate-500 max-w-[200px] truncate">{note.reason || "—"}</TableCell>
                                                <TableCell className="text-right font-mono font-medium text-orange-600">-{formatCurrency(note.total)}</TableCell>
                                                <TableCell>
                                                    <DropdownMenu>
                                                        <DropdownMenuTrigger asChild>
                                                            <Button variant="ghost" className="h-8 w-8 p-0" aria-label="Row actions"><MoreHorizontal className="h-4 w-4" /></Button>
                                                        </DropdownMenuTrigger>
                                                        <DropdownMenuContent align="end">
                                                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                                            <DropdownMenuSeparator />
                                                            <DropdownMenuItem onSelect={() => handleEditClick(note)}>
                                                                Edit
                                                            </DropdownMenuItem>
                                                            <DropdownMenuItem onSelect={() => handleDeleteClick(note)} className="text-red-600 focus:text-red-600">
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
                                <Undo2 className="h-12 w-12 text-slate-300 mb-4" />
                                <h3 className="text-lg font-medium text-slate-900 mb-1">No debit notes found</h3>
                                <p className="text-slate-500 text-sm mb-4">{search ? "Try adjusting your search" : "Return goods to a supplier to reduce your payable"}</p>
                                <Button onClick={() => setDialogOpen(true)} className="bg-brand-600 hover:bg-brand-700">
                                    <Plus className="h-4 w-4 mr-2" /> New Debit Note
                                </Button>
                            </CardContent>
                        </Card>
                    );
                })()
            }
        </div >
    );
};

export default DebitNotes;
