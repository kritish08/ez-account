import React, { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";

// Eager: everything needed to render the very first paint on either the
// login screen or an authenticated route. Layout is the shell every page
// renders inside, and PageLoader is the Suspense fallback itself, so
// deferring either would just add a round-trip before anything appears.
import Login from "./pages/Login";
import Layout from "./components/Layout";
import PageLoader from "./components/PageLoader";

// Lazy: one chunk per route. Previously all 25 pages were static imports,
// so a user landing on /login downloaded and parsed the entire application —
// Reports, Settings, the invoice editors, the barcode scanner — before the
// password field became interactive.
const Setup = lazy(() => import("./pages/Setup"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Customers = lazy(() => import("./pages/Customers"));
const CustomerDetail = lazy(() => import("./pages/CustomerDetail"));
const Invoices = lazy(() => import("./pages/Invoices"));
const CreateInvoice = lazy(() => import("./pages/CreateInvoice"));
const EditInvoice = lazy(() => import("./pages/EditInvoice"));
const InvoiceDetail = lazy(() => import("./pages/InvoiceDetail"));
const Payments = lazy(() => import("./pages/Payments"));
const Expenses = lazy(() => import("./pages/Expenses"));
const Reports = lazy(() => import("./pages/Reports"));
const RawMaterials = lazy(() => import("./pages/RawMaterials"));
const FinishedGoods = lazy(() => import("./pages/FinishedGoods"));
const ProductDetail = lazy(() => import("./pages/ProductDetail"));
const Suppliers = lazy(() => import("./pages/Suppliers"));
const SupplierDetail = lazy(() => import("./pages/SupplierDetail"));
const Purchases = lazy(() => import("./pages/Purchases"));
const CreditNotes = lazy(() => import("./pages/CreditNotes"));
const CreditNoteDetail = lazy(() => import("./pages/CreditNoteDetail"));
const DebitNotes = lazy(() => import("./pages/DebitNotes"));
const DebitNoteDetail = lazy(() => import("./pages/DebitNoteDetail"));
const Settings = lazy(() => import("./pages/Settings"));
const ProductionOrders = lazy(() => import("./pages/ProductionOrders"));
const NotFound = lazy(() => import("./pages/NotFound"));

// The voice assistant is ~500 lines plus its own stylesheet, a MediaRecorder
// graph and a WebSocket, and it mounted on every authenticated page whether
// or not anyone opened it.
const VoiceAssistant = lazy(() => import("./components/VoiceAssistant"));

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
      <Suspense fallback={<PageLoader />}>
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

            {/* 404 inside the shell, so a bad link keeps the nav rather than
                ejecting the user to a bare page with a "Go home" button. */}
            <Route path="*" element={<NotFound />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>

      {/* Voice Assistant — only shown when logged in. Its own Suspense
          boundary so loading it never blanks the page behind it. */}
      {token && (
        <Suspense fallback={null}>
          <VoiceAssistant />
        </Suspense>
      )}
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
