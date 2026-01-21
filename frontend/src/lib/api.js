import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Helper to format currency
export const formatCurrency = (amount) => {
  if (amount === null || amount === undefined) return "₹ 0.00";
  return `₹ ${Number(amount).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

// Helper to format date
export const formatDate = (dateStr) => {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
};

// Business
export const getBusiness = () => axios.get(`${API}/business`);
export const setupBusiness = (data) => axios.post(`${API}/business/setup`, data);

// Customers
export const getCustomers = () => axios.get(`${API}/customers`);
export const getCustomer = (id) => axios.get(`${API}/customers/${id}`);
export const createCustomer = (data) => axios.post(`${API}/customers`, data);
export const updateCustomer = (id, data) => axios.put(`${API}/customers/${id}`, data);
export const getCustomerLedger = (id) => axios.get(`${API}/customers/${id}/ledger`);

// Products
export const getProducts = () => axios.get(`${API}/products`);
export const getProduct = (id) => axios.get(`${API}/products/${id}`);
export const createProduct = (data) => axios.post(`${API}/products`, data);
export const updateProduct = (id, data) => axios.put(`${API}/products/${id}`, data);

// Suppliers
export const getSuppliers = () => axios.get(`${API}/suppliers`);
export const getSupplier = (id) => axios.get(`${API}/suppliers/${id}`);
export const createSupplier = (data) => axios.post(`${API}/suppliers`, data);

// Purchases
export const getPurchases = () => axios.get(`${API}/purchases`);
export const createPurchase = (data) => axios.post(`${API}/purchases`, data);

// Invoices
export const getInvoices = (status) => axios.get(`${API}/invoices`, { params: { status } });
export const getInvoice = (id) => axios.get(`${API}/invoices/${id}`);
export const createInvoice = (data) => axios.post(`${API}/invoices`, data);
export const updateInvoice = (id, data) => axios.put(`${API}/invoices/${id}`, data);
export const publishInvoice = (id) => axios.post(`${API}/invoices/${id}/publish`);
export const downloadInvoicePDF = async (id) => {
  const response = await axios.get(`${API}/invoices/${id}/pdf`, {
    responseType: "blob",
  });
  return response.data;
};

// Payments
export const getPayments = () => axios.get(`${API}/payments`);
export const createPayment = (data) => axios.post(`${API}/payments`, data);

// Supplier Payments
export const createSupplierPayment = (data) => 
  axios.post(`${API}/supplier-payments`, null, { params: data });

// Expenses
export const getExpenses = () => axios.get(`${API}/expenses`);
export const createExpense = (data) => axios.post(`${API}/expenses`, data);

// Dashboard
export const getDashboard = () => axios.get(`${API}/dashboard`);

// Reports
export const getOutstandingReport = () => axios.get(`${API}/reports/outstanding`);
export const getCreditReport = () => axios.get(`${API}/reports/credit`);
export const getSalesReport = (startDate, endDate) => 
  axios.get(`${API}/reports/sales`, { params: { start_date: startDate, end_date: endDate } });
export const getExpensesReport = (startDate, endDate) => 
  axios.get(`${API}/reports/expenses`, { params: { start_date: startDate, end_date: endDate } });
export const getCashBankReport = () => axios.get(`${API}/reports/cash-bank`);
export const getInventoryReport = () => axios.get(`${API}/reports/inventory`);
export const getLowStockReport = () => axios.get(`${API}/reports/low-stock`);
export const getStockMovementReport = (productId, startDate, endDate) => 
  axios.get(`${API}/reports/stock-movement`, { params: { product_id: productId, start_date: startDate, end_date: endDate } });
export const getSupplierPayablesReport = () => axios.get(`${API}/reports/supplier-payables`);
export const getProfitReport = (startDate, endDate) => 
  axios.get(`${API}/reports/profit`, { params: { start_date: startDate, end_date: endDate } });

// Export
export const exportReport = (reportType, format = "csv", params = {}) => {
  const queryParams = new URLSearchParams({ format, ...params }).toString();
  return `${API}/export/${reportType}?${queryParams}`;
};

// Settings
export const getS3Settings = () => axios.get(`${API}/settings/s3`);
export const saveS3Settings = (data) => axios.post(`${API}/settings/s3`, data);
export const testS3Connection = (data) => axios.post(`${API}/settings/s3/test`, data);

// Backup
export const createBackup = () => axios.post(`${API}/backup/create`);
export const listBackups = () => axios.get(`${API}/backup/list`);
export const restoreBackup = (filename) => axios.post(`${API}/backup/restore/${filename}`);
