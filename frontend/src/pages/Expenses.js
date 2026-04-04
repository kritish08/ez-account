import React, { useState, useEffect } from "react";
import { getExpenses, createExpense, updateExpense, deleteExpense, formatCurrency, formatDate } from "../lib/api";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { PageHeader } from "../components/PageHeader";
import { UIFilters } from "../components/UIFilters";
import { Plus, Banknote, Building2, MoreHorizontal, Pencil, Trash2, Receipt, Loader2 } from "lucide-react";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent } from "../components/ui/card";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
const EXPENSE_CATEGORIES = [
  "Office Supplies",
  "Utilities",
  "Rent",
  "Transport",
  "Salary",
  "Marketing",
  "Maintenance",
  "Other",
];

const Expenses = () => {
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingExpense, setEditingExpense] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [expenseToDelete, setExpenseToDelete] = useState(null);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [modeFilter, setModeFilter] = useState("all");
  const [dateRange, setDateRange] = useState(undefined);

  const [formData, setFormData] = useState({
    description: "",
    amount: "",
    mode: "cash",
    category: "",
    date: new Date().toISOString().split("T")[0],
  });

  useEffect(() => {
    fetchExpenses();
  }, [categoryFilter, modeFilter, dateRange]);

  const fetchExpenses = async () => {
    try {
      setLoading(true);
      const startDate = dateRange?.from ? dateRange.from.toISOString().split('T')[0] : null;
      const endDate = dateRange?.to ? dateRange.to.toISOString().split('T')[0] : null;

      // Note: Filtering by category/mode is currently done client-side in the render
      // But we pass dates to backend
      const response = await getExpenses(startDate, endDate);
      setExpenses(response.data);
    } catch (error) {
      toast.error("Failed to load expenses");
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({
      description: "",
      amount: "",
      mode: "cash",
      category: "",
      date: new Date().toISOString().split("T")[0],
    });
    setEditingExpense(null);
  };

  const handleEdit = (expense) => {
    setEditingExpense(expense);
    setFormData({
      description: expense.description,
      amount: expense.amount,
      mode: expense.mode,
      category: expense.category || "",
      date: expense.date.split("T")[0],
    });
    setDialogOpen(true);
  };

  const handleDeleteClick = (expense) => {
    setExpenseToDelete(expense);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    if (!expenseToDelete) return;
    try {
      await deleteExpense(expenseToDelete.id);
      toast.success("Expense deleted successfully");
      fetchExpenses();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete expense");
    } finally {
      setDeleteDialogOpen(false);
      setExpenseToDelete(null);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.description) {
      toast.error("Please enter a description");
      return;
    }

    if (!formData.amount || parseFloat(formData.amount) <= 0) {
      toast.error("Please enter a valid amount");
      return;
    }

    setSaving(true);
    try {
      if (editingExpense) {
        await updateExpense(editingExpense.id, {
          ...formData,
          amount: parseFloat(formData.amount),
        });
        toast.success("Expense updated successfully!");
      } else {
        await createExpense({
          ...formData,
          amount: parseFloat(formData.amount),
        });
        toast.success("Expense recorded successfully!");
      }
      setDialogOpen(false);
      resetForm();
      fetchExpenses();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save expense");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="expenses-page">
      <PageHeader
        title="Expenses"
        description="Track your business expenses"
        action={
          <Button onClick={() => setDialogOpen(true)} className="bg-brand-600 hover:bg-brand-700" data-testid="add-expense-btn">
            <Plus className="h-4 w-4 mr-2" />
            Add Expense
          </Button>
        }
      />

      <Dialog open={dialogOpen} onOpenChange={(open) => {
        setDialogOpen(open);
        if (!open) resetForm();
      }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingExpense ? "Edit Expense" : "Add Expense"}</DialogTitle>
            <DialogDescription>{editingExpense ? "Update expense details below" : "Record a new business expense"}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 mt-4">
            <div className="space-y-2">
              <Label htmlFor="description">Description *</Label>
              <Input
                id="description"
                value={formData.description}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, description: e.target.value }))
                }
                placeholder="What was this expense for?"
                data-testid="expense-description-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="amount">Amount *</Label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono">₹</span>
                <Input
                  id="amount"
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.amount}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, amount: e.target.value }))
                  }
                  className="pl-8 font-mono"
                  placeholder="0.00"
                  data-testid="expense-amount-input"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Category</Label>
              <Select
                value={formData.category}
                onValueChange={(value) =>
                  setFormData((prev) => ({ ...prev, category: value }))
                }
              >
                <SelectTrigger data-testid="expense-category-select">
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
                <SelectContent>
                  {EXPENSE_CATEGORIES.map((cat) => (
                    <SelectItem key={cat} value={cat}>
                      {cat}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Paid Via *</Label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setFormData((prev) => ({ ...prev, mode: "cash" }))}
                  className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${formData.mode === "cash"
                    ? "border-brand-600 bg-brand-50 text-brand-700"
                    : "border-slate-200 hover:border-slate-300"
                    }`}
                  data-testid="expense-mode-cash"
                >
                  <Banknote className="h-4 w-4" />
                  <span className="font-medium">Cash</span>
                </button>
                <button
                  type="button"
                  onClick={() => setFormData((prev) => ({ ...prev, mode: "bank" }))}
                  className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${formData.mode === "bank"
                    ? "border-brand-600 bg-brand-50 text-brand-700"
                    : "border-slate-200 hover:border-slate-300"
                    }`}
                  data-testid="expense-mode-bank"
                >
                  <Building2 className="h-4 w-4" />
                  <span className="font-medium">Bank</span>
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="date">Date</Label>
              <Input
                id="date"
                type="date"
                value={formData.date}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, date: e.target.value }))
                }
                data-testid="expense-date-input"
              />
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
                data-testid="save-expense-btn"
              >
                {saving ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {editingExpense ? "Updating..." : "Saving..."}
                  </>
                ) : (
                  editingExpense ? "Update Expense" : "Add Expense"
                )}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Alert Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the expense "{expenseToDelete?.description}" of {expenseToDelete && formatCurrency(expenseToDelete.amount)}.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-red-600 hover:bg-red-700">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Search & Filters */}
      <UIFilters
        search={search}
        setSearch={setSearch}
        searchPlaceholder="Search expenses..."
        statusFilter={categoryFilter}
        setStatusFilter={setCategoryFilter}
        statusLabel="All Categories"
        statusOptions={[
          ...EXPENSE_CATEGORIES.map(cat => ({ value: cat, label: cat }))
        ]}
        dateRange={dateRange}
        setDateRange={setDateRange}
        onClear={() => {
          setSearch("");
          setCategoryFilter("all");
          setModeFilter("all");
          setDateRange(undefined);
        }}
      >
        <div className="flex items-center gap-2">
          <Select value={modeFilter} onValueChange={setModeFilter}>
            <SelectTrigger className="w-[130px]">
              <SelectValue placeholder="Paid Via" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Modes</SelectItem>
              <SelectItem value="cash">Cash</SelectItem>
              <SelectItem value="bank">Bank</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </UIFilters>

      {/* Expenses Table */}
      {
        loading ? (
          <Card>
            <CardContent className="p-6">
              <div className="space-y-4">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            </CardContent>
          </Card>
        ) : (() => {
          const filtered = expenses.filter((exp) => {
            const q = search.toLowerCase();
            const matchSearch = !q || exp.description?.toLowerCase().includes(q) || exp.category?.toLowerCase().includes(q);
            const matchCategory = categoryFilter === "all" || exp.category === categoryFilter;
            const matchMode = modeFilter === "all" || exp.mode === modeFilter;
            return matchSearch && matchCategory && matchMode; // Date filtering is server-side now
          });
          return filtered.length > 0 ? (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Description</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead>Paid Via</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                      <TableHead className="w-[80px]"></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filtered.map((expense) => (
                      <TableRow
                        key={expense.id}
                        className="cursor-pointer hover:bg-slate-50"
                        onClick={(e) => {
                          if (e.target.closest('button')) return;
                          handleEdit(expense);
                        }}
                        data-testid={`expense-row-${expense.id}`}
                      >
                        <TableCell className="font-medium">{expense.description}</TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="font-normal">
                            {expense.category || "Other"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-slate-500">{formatDate(expense.date)}</TableCell>
                        <TableCell>
                          <span className="inline-flex items-center gap-1 text-sm capitalize">
                            {expense.mode === "cash" ? (
                              <Banknote className="h-3 w-3 text-emerald-600" />
                            ) : (
                              <Building2 className="h-3 w-3 text-blue-600" />
                            )}
                            {expense.mode}
                          </span>
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium text-rose-600">
                          -{formatCurrency(expense.amount)}
                        </TableCell>
                        <TableCell>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" className="h-8 w-8 p-0" data-testid={`expense-actions-${expense.id}`}>
                                <span className="sr-only">Open menu</span>
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuLabel>Actions</DropdownMenuLabel>
                              <DropdownMenuItem onClick={() => handleEdit(expense)} data-testid={`edit-expense-${expense.id}`}>
                                <Pencil className="mr-2 h-4 w-4" />
                                Edit
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => handleDeleteClick(expense)}
                                className="text-red-600 focus:text-red-600"
                                data-testid={`delete-expense-${expense.id}`}
                              >
                                <Trash2 className="mr-2 h-4 w-4" />
                                Delete
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
                <Receipt className="h-12 w-12 text-slate-300 mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-1">No expenses found</h3>
                <p className="text-slate-500 text-sm mb-4">{search || categoryFilter !== 'all' || modeFilter !== 'all' ? 'Try adjusting your search or filters' : 'Record your first expense to track spending'}</p>
                <Button
                  onClick={() => setDialogOpen(true)}
                  className="bg-brand-600 hover:bg-brand-700"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add Expense
                </Button>
              </CardContent>
            </Card>
          );
        })()
      }
    </div >
  );
};

export default Expenses;
