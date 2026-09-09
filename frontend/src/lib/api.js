import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Global 401 handler: clear stale auth and bounce to /login so list pages
// don't silently render as "empty" when the token has expired or was missing.
let interceptorInstalled = false;
if (!interceptorInstalled) {
  axios.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error?.response?.status === 401) {
        const onLoginPage = window.location.pathname === "/login";
        if (!onLoginPage) {
          localStorage.removeItem("token");
          delete axios.defaults.headers.common["Authorization"];
          window.location.assign("/login");
        }
      }
      return Promise.reject(error);
    }
  );
  interceptorInstalled = true;
}

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

// Auth
export const getAuthConfig = () => axios.get(`${API}/auth/config`);

// Health (no auth required)
export const getHealth = () => axios.get(`${API}/health`);

// Scheduled backup (cron config)
export const getBackupSchedule = () => axios.get(`${API}/settings/backup/schedule`);
export const updateBackupSchedule = (data) => axios.put(`${API}/settings/backup/schedule`, data);

// WebAuthn / Passkey
export const registerPasskeyBegin = () => axios.post(`${API}/auth/passkey/register/begin`);
export const registerPasskeyComplete = (data) => axios.post(`${API}/auth/passkey/register/complete`, data);
export const authenticatePasskeyBegin = (email) => axios.post(`${API}/auth/passkey/authenticate/begin`, { email });
export const authenticatePasskeyComplete = (email, credentialData) =>
  axios.post(`${API}/auth/passkey/authenticate/complete`, { email, credential_data: credentialData });
export const getPasskeys = () => axios.get(`${API}/auth/passkeys`);
export const deletePasskey = (id) => axios.delete(`${API}/auth/passkeys/${encodeURIComponent(id)}`);
export const renamePasskey = (id, name) => axios.patch(`${API}/auth/passkeys/${encodeURIComponent(id)}`, { name });

// Business
export const getBusiness = () => axios.get(`${API}/business`);
export const setupBusiness = (data) => axios.post(`${API}/business/setup`, data);

// Customers
export const getCustomers = () => axios.get(`${API}/customers`);
export const getCustomer = (id) => axios.get(`${API}/customers/${id}`);
export const createCustomer = (data) => axios.post(`${API}/customers`, data);
export const updateCustomer = (id, data) => axios.put(`${API}/customers/${id}`, data);
export const deleteCustomer = (id) => axios.delete(`${API}/customers/${id}`);
export const getCustomerLedger = (id, startDate, endDate) =>
  axios.get(`${API}/customers/${id}/ledger`, { params: { start_date: startDate, end_date: endDate } });


// Products
export const getProducts = (params) => axios.get(`${API}/products`, { params });
export const getProduct = (id) => axios.get(`${API}/products/${id}`);
export const getBarcodeLabels = (id, params) => axios.get(`${API}/products/${id}/labels`, { params });
export const createProduct = (data) => axios.post(`${API}/products`, data);
export const updateProduct = (id, data) => axios.put(`${API}/products/${id}`, data);
export const deleteProduct = (id) => axios.delete(`${API}/products/${id}`);
export const getProductStockMovements = (id) => axios.get(`${API}/products/${id}/stock-movements`);
export const getProductBatches = (id) => axios.get(`${API}/products/${id}/batches`);
export const getProductSerialNumbers = (id) => axios.get(`${API}/products/${id}/serial-numbers`);
export const getProductBOM = (id) => axios.get(`${API}/products/${id}/bom`);
export const saveProductBOM = (id, data) => axios.post(`${API}/products/${id}/bom`, data);

// Production Orders
export const getProductionOrders = (params) => axios.get(`${API}/production-orders`, { params });
export const getProductionOrder = (id) => axios.get(`${API}/production-orders/${id}`);
export const createProductionOrder = (data) => axios.post(`${API}/production-orders`, data);
export const startProductionOrder = (id) => axios.put(`${API}/production-orders/${id}/start`);
export const completeProductionOrder = (id) => axios.put(`${API}/production-orders/${id}/complete`);
export const cancelProductionOrder = (id) => axios.put(`${API}/production-orders/${id}/cancel`);
export const sendToQC = (id) => axios.put(`${API}/production-orders/${id}/qc`);

// Suppliers
export const getSuppliers = () => axios.get(`${API}/suppliers`);
export const getSupplier = (id) => axios.get(`${API}/suppliers/${id}`);
export const createSupplier = (data) => axios.post(`${API}/suppliers`, data);
export const updateSupplier = (id, data) => axios.put(`${API}/suppliers/${id}`, data);
export const deleteSupplier = (id) => axios.delete(`${API}/suppliers/${id}`);
export const getSupplierLedger = (id) => axios.get(`${API}/suppliers/${id}/ledger`);

// Purchases
export const getPurchases = (supplierId, debitUsedOnly) => axios.get(`${API}/purchases`, { params: { supplier_id: supplierId, debit_used_only: debitUsedOnly } });
export const getPurchase = (id) => axios.get(`${API}/purchases/${id}`);
export const createPurchase = (data) => axios.post(`${API}/purchases`, data);
export const updatePurchase = (id, data) => axios.put(`${API}/purchases/${id}`, data);
export const deletePurchase = (id) => axios.delete(`${API}/purchases/${id}`);

// Invoices
export const getInvoices = (status, customerId, creditAppliedOnly) => axios.get(`${API}/invoices`, { params: { status, customer_id: customerId, credit_applied_only: creditAppliedOnly } });
export const getInvoice = (id) => axios.get(`${API}/invoices/${id}`);
export const createInvoice = (data) => axios.post(`${API}/invoices`, data);
export const updateInvoice = (id, data) => axios.put(`${API}/invoices/${id}`, data);
export const deleteInvoice = (id) => axios.delete(`${API}/invoices/${id}`);
export const publishInvoice = (id, applyCredit) => axios.post(`${API}/invoices/${id}/publish`, null, { params: { apply_credit: applyCredit } });
export const downloadInvoicePDF = async (id) => {
  const response = await axios.get(`${API}/invoices/${id}/pdf`, {
    responseType: "blob",
  });
  return response.data;
};

// Payments
export const getPayments = (startDate, endDate) =>
  axios.get(`${API}/payments`, { params: { start_date: startDate, end_date: endDate } });
export const createPayment = (data) => axios.post(`${API}/payments`, data);
export const deletePayment = (id) => axios.delete(`${API}/payments/${id}`);

// Supplier Payments
export const createSupplierPayment = (data) => axios.post(`${API}/supplier-payments`, data);
export const deleteSupplierPayment = (id) => axios.delete(`${API}/supplier-payments/${id}`);

// Expenses
export const getExpenses = (startDate, endDate) =>
  axios.get(`${API}/expenses`, { params: { start_date: startDate, end_date: endDate } });
export const getExpense = (id) => axios.get(`${API}/expenses/${id}`);
export const createExpense = (data) => axios.post(`${API}/expenses`, data);
export const updateExpense = (id, data) => axios.put(`${API}/expenses/${id}`, data);
export const deleteExpense = (id) => axios.delete(`${API}/expenses/${id}`);

// Credit Notes
export const getCreditNotes = (startDate, endDate) =>
  axios.get(`${API}/credit-notes`, { params: { start_date: startDate, end_date: endDate } });
export const getCreditNote = (id) => axios.get(`${API}/credit-notes/${id}`);
export const createCreditNote = (data) => axios.post(`${API}/credit-notes`, data);
export const updateCreditNote = (id, data) => axios.put(`${API}/credit-notes/${id}`, data);
export const deleteCreditNote = (id) => axios.delete(`${API}/credit-notes/${id}`);

// Debit Notes
export const getDebitNotes = (startDate, endDate) =>
  axios.get(`${API}/debit-notes`, { params: { start_date: startDate, end_date: endDate } });
export const getDebitNote = (id) => axios.get(`${API}/debit-notes/${id}`);
export const createDebitNote = (data) => axios.post(`${API}/debit-notes`, data);
export const updateDebitNote = (id, data) => axios.put(`${API}/debit-notes/${id}`, data);
export const deleteDebitNote = (id) => axios.delete(`${API}/debit-notes/${id}`);

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
export const getInventoryByTypeReport = () => axios.get(`${API}/reports/inventory-by-type`);
export const getBatchTraceabilityReport = () => axios.get(`${API}/reports/batch-traceability`);
export const getProductionYieldReport = () => axios.get(`${API}/reports/production-yield`);
export const getLowStockReport = () => axios.get(`${API}/reports/low-stock`);
export const getStockMovementReport = (productId, startDate, endDate) =>
  axios.get(`${API}/reports/stock-movement`, { params: { product_id: productId, start_date: startDate, end_date: endDate } });
export const getSupplierPayablesReport = () => axios.get(`${API}/reports/supplier-payables`);
export const getProfitReport = (startDate, endDate) =>
  axios.get(`${API}/reports/profit`, { params: { start_date: startDate, end_date: endDate } });
export const getProfitLossReport = (startDate, endDate) =>
  axios.get(`${API}/reports/profit-loss`, { params: { start_date: startDate, end_date: endDate } });
// Trial balance and balance sheet are as-of-now snapshots. The backend
// doesn't accept a date parameter, so the previous `asOfDate` argument
// was silently ignored — point-in-time variants would need a new endpoint.
export const getBalanceSheetReport = () => axios.get(`${API}/reports/balance-sheet`);
export const getTrialBalanceReport = () => axios.get(`${API}/reports/trial-balance`);

// Export
export const exportReport = (reportType, format = "csv", params = {}) => {
  const queryParams = new URLSearchParams({ format, ...params }).toString();
  return `${API}/export/${reportType}?${queryParams}`;
};

// Settings
export const getSystemSettings = () => axios.get(`${API}/settings/system`);
export const updateSystemSettings = (data) => axios.post(`${API}/settings/system`, data);
export const getModulesSettings = () => axios.get(`${API}/settings/modules`);
export const updateModulesSettings = (data) => axios.put(`${API}/settings/modules`, data);
export const getS3Settings = () => axios.get(`${API}/settings/s3`);
export const saveS3Settings = (data) => axios.post(`${API}/settings/s3`, data);
export const testS3Connection = (data) => axios.post(`${API}/settings/s3/test`, data);

// Backup. Note: S3 credential config lives under /settings/s3 (see above) —
// the previous getS3Config/updateS3Config exports pointed at a /backup/config
// route that doesn't exist on the backend; removed.
export const createBackup = () => axios.post(`${API}/backup/create`);
export const listBackups = () => axios.get(`${API}/backup/list`);
// Restore overwrites every collection in the archive, so it takes the same
// password + verbatim-phrase confirmation as a factory reset.
export const restoreBackup = (filename, data) =>
  axios.post(`${API}/backup/restore/${filename}`, data);

// AI Invoice Parsing (GPT-5.2 with Hindi/Hinglish support)
export const parseInvoiceImage = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return axios.post(`${API}/ai/parse-invoice`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

// System Reset
export const resetSystem = (data) => axios.post(`${API}/system/reset`, data);

// Alias for backward compatibility (used in Expenses and Purchases)
export const parseInvoice = parseInvoiceImage;
