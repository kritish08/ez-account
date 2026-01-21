# EZ Accounts - PRD (Product Requirements Document)

## Original Problem Statement
Build a modern, simple accounting web application for a single-owner wholesale business. The app must be extremely easy to use, require no accounting knowledge, and handle all accounting logic automatically in the background using double-entry principles.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **PDF Generation**: ReportLab

## User Personas
1. **Primary**: Small wholesale business owner in India with no accounting knowledge who needs simple invoicing and payment tracking

## Core Requirements (Static)
1. Business setup (name, currency INR, financial year April, opening cash & bank balance)
2. Customer management with ledger view
3. Invoices with line items, auto-numbering, PDF download
4. Payment recording with FIFO allocation
5. Automatic credit usage on new invoices
6. Expense tracking
7. Dashboard with key metrics
8. Reports (Outstanding, Credit, Sales, Expenses, Cash/Bank)

## What's Been Implemented (January 2026)

### Authentication
- [x] User registration with bcrypt password hashing
- [x] JWT-based authentication (7-day expiry)
- [x] Protected routes

### Business Setup
- [x] Business details (name, address, phone, email, GSTIN)
- [x] Opening cash and bank balances
- [x] Financial year configuration (April default)

### Customer Management
- [x] Add/edit customers (name, phone, address, GSTIN)
- [x] Opening balance (debit or credit)
- [x] Outstanding balance tracking
- [x] Credit/advance balance tracking
- [x] Customer ledger view in simple language

### Invoices
- [x] Create invoices with multiple line items
- [x] Auto invoice numbering (INV-00001 format)
- [x] Status tracking (unpaid, partially_paid, paid)
- [x] PDF download with professional template
- [x] Auto-apply customer credit on new invoices

### Payments
- [x] Record payments with cash/bank mode
- [x] FIFO payment allocation to oldest invoices
- [x] Excess payment stored as customer credit
- [x] Ledger entries automatically created

### Expenses
- [x] Simple expense entry with categories
- [x] Cash/bank payment mode
- [x] Auto ledger posting

### Dashboard
- [x] Cash balance
- [x] Bank balance
- [x] Total outstanding from customers
- [x] Total customer credit
- [x] Today's sales
- [x] Monthly sales
- [x] Recent invoices and payments

### Reports
- [x] Customer outstanding report
- [x] Customer credit report
- [x] Sales report with date filter
- [x] Expenses report with category breakdown
- [x] Cash and bank summary

### Double-Entry Bookkeeping
- [x] Automatic ledger entries for all transactions
- [x] Account balance calculations
- [x] FIFO payment allocation algorithm

## Prioritized Backlog

### P0 (Critical) - All Done
- All core features implemented

### P1 (Important)
- [ ] Invoice editing for draft invoices
- [ ] Customer deletion with safety checks
- [ ] Expense editing/deletion

### P2 (Nice to Have)
- [ ] Export reports to Excel/CSV
- [ ] Multiple payment methods per transaction
- [ ] Invoice email sending
- [ ] Recurring invoices
- [ ] Dashboard date range selector
- [ ] Search/filter across all lists

### P3 (Future)
- [ ] Multiple business support
- [ ] Data backup/restore
- [ ] Mobile app (React Native)
- [ ] GST calculations and filing
- [ ] Inventory management

## Next Tasks
1. Add invoice editing capability for draft invoices
2. Implement export to Excel for reports
3. Add invoice email functionality
