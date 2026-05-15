import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";

// Pages
import Login from "./pages/Login";
import Setup from "./pages/Setup";
import Dashboard from "./pages/Dashboard";
import Customers from "./pages/Customers";
import CustomerDetail from "./pages/CustomerDetail";
import Invoices from "./pages/Invoices";
import CreateInvoice from "./pages/CreateInvoice";
import EditInvoice from "./pages/EditInvoice";
import InvoiceDetail from "./pages/InvoiceDetail";
import Payments from "./pages/Payments";
import Expenses from "./pages/Expenses";
import Reports from "./pages/Reports";
import RawMaterials from "./pages/RawMaterials";
import FinishedGoods from "./pages/FinishedGoods";
import ProductDetail from "./pages/ProductDetail";
import Suppliers from "./pages/Suppliers";
import SupplierDetail from "./pages/SupplierDetail";
import Purchases from "./pages/Purchases";
import CreditNotes from "./pages/CreditNotes";
import CreditNoteDetail from "./pages/CreditNoteDetail";
import DebitNotes from "./pages/DebitNotes";
import DebitNoteDetail from "./pages/DebitNoteDetail";
import Settings from "./pages/Settings";
import ProductionOrders from "./pages/ProductionOrders";
import NotFound from "./pages/NotFound";
import Layout from "./components/Layout";
import VoiceAssistant from "./components/VoiceAssistant";
import PageLoader from "./components/PageLoader";

// Auth context
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ModulesProvider } from "./context/ModulesContext";

const ProtectedRoute = ({ children }) => {
  const { token, loading } = useAuth();

  if (loading) {
    return <PageLoader />;
  }

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return children;
};

function AppRoutes() {
  const { token } = useAuth();

  return (
    <>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route path="/" element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }>
          <Route index element={<Dashboard />} />
          <Route path="setup" element={<Setup />} />
          <Route path="customers" element={<Customers />} />
          <Route path="customers/:id" element={<CustomerDetail />} />
          <Route path="raw-materials" element={<RawMaterials />} />
          <Route path="finished-goods" element={<FinishedGoods />} />
          <Route path="products/:id" element={<ProductDetail />} />
          <Route path="suppliers" element={<Suppliers />} />
          <Route path="suppliers/:id" element={<SupplierDetail />} />
          <Route path="purchases" element={<Purchases />} />
          <Route path="production" element={<ProductionOrders />} />
          <Route path="invoices" element={<Invoices />} />
          <Route path="invoices/new" element={<CreateInvoice />} />
          <Route path="invoices/:id" element={<InvoiceDetail />} />
          <Route path="invoices/:id/edit" element={<EditInvoice />} />
          <Route path="payments" element={<Payments />} />
          <Route path="expenses" element={<Expenses />} />
          <Route path="credit-notes" element={<CreditNotes />} />
          <Route path="credit-notes/:id" element={<CreditNoteDetail />} />
          <Route path="debit-notes" element={<DebitNotes />} />
          <Route path="debit-notes/:id" element={<DebitNoteDetail />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
        </Route>

        {/* Catch-all 404 */}
        <Route path="*" element={<NotFound />} />
      </Routes>

      {/* Voice Assistant — only shown when logged in */}
      {token && <VoiceAssistant />}
    </>
  );
}

function App() {
  return (
    <AuthProvider>
      <ModulesProvider>
        <BrowserRouter>
          <AppRoutes />
          <Toaster position="top-right" richColors />
        </BrowserRouter>
      </ModulesProvider>
    </AuthProvider>
  );
}

export default App;
