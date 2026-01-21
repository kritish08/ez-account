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

// Invoices
export const getInvoices = (status) => axios.get(`${API}/invoices`, { params: { status } });
export const getInvoice = (id) => axios.get(`${API}/invoices/${id}`);
export const createInvoice = (data) => axios.post(`${API}/invoices`, data);
export const downloadInvoicePDF = async (id) => {
  const response = await axios.get(`${API}/invoices/${id}/pdf`, {
    responseType: "blob",
  });
  return response.data;
};

// Payments
export const getPayments = () => axios.get(`${API}/payments`);
export const createPayment = (data) => axios.post(`${API}/payments`, data);

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
