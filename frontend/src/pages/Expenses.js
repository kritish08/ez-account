import React, { useState, useEffect } from "react";
import { getExpenses, createExpense, formatCurrency, formatDate } from "../lib/api";
import { Button } from "../components/ui/button";
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
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { Plus, Receipt, Loader2, Banknote, Building2 } from "lucide-react";

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
  const [formData, setFormData] = useState({
    description: "",
    amount: "",
    mode: "cash",
    category: "",
    date: new Date().toISOString().split("T")[0],
  });

  useEffect(() => {
    fetchExpenses();
  }, []);

  const fetchExpenses = async () => {
    try {
      const response = await getExpenses();
      setExpenses(response.data);
    } catch (error) {
      toast.error("Failed to load expenses");
    } finally {
      setLoading(false);
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
      await createExpense({
        ...formData,
        amount: parseFloat(formData.amount),
      });
      toast.success("Expense recorded successfully!");
      setDialogOpen(false);
      setFormData({
        description: "",
        amount: "",
        mode: "cash",
        category: "",
        date: new Date().toISOString().split("T")[0],
      });
      fetchExpenses();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to record expense");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="expenses-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-slate-900">Expenses</h1>
          <p className="text-slate-500 mt-1">Track your business expenses</p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="bg-brand-600 hover:bg-brand-700" data-testid="add-expense-btn">
              <Plus className="h-4 w-4 mr-2" />
              Add Expense
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Add Expense</DialogTitle>
              <DialogDescription>Record a new business expense</DialogDescription>
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
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${
                      formData.mode === "cash"
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
                    className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${
                      formData.mode === "bank"
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
                      Saving...
                    </>
                  ) : (
                    "Add Expense"
                  )}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Expenses Table */}
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
      ) : expenses.length > 0 ? (
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
                </TableRow>
              </TableHeader>
              <TableBody>
                {expenses.map((expense) => (
                  <TableRow key={expense.id} data-testid={`expense-row-${expense.id}`}>
                    <TableCell className="font-medium">{expense.description}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center rounded-full bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-600 ring-1 ring-inset ring-slate-500/10">
                        {expense.category || "Other"}
                      </span>
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
            <h3 className="text-lg font-medium text-slate-900 mb-1">No expenses yet</h3>
            <p className="text-slate-500 text-sm mb-4">Record your first expense to track spending</p>
            <Button
              onClick={() => setDialogOpen(true)}
              className="bg-brand-600 hover:bg-brand-700"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Expense
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Expenses;
