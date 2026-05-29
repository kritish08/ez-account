"""
Function Executor for Voice Assistant

Executes grounded functions based on GPT-5.5 function calls.
All functions are based on actual database schema and API capabilities.
"""

from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from datetime import datetime, timezone
import uuid

from app.services.ledger import create_ledger_entry
from app.services.stock import create_stock_movement

from .voice_session import VoiceSession, SessionState


async def _next_seq(db: AsyncIOMotorDatabase, name: str) -> int:
    """Atomic counter — shares the `counters` collection with the canonical
    `_next_seq` in server.py. Both paths produce strictly unique values, so
    the voice executor can't generate a duplicate INV/PUR number even under
    concurrent traffic with REST callers."""
    doc = await db.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]


class FunctionExecutor:
    """
    Executes voice assistant functions.
    
    All functions are grounded in actual codebase capabilities.
    No hallucinations - only uses real database schema and validation logic.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, session: VoiceSession):
        self.db = db
        self.session = session
    
    # ==================== INVOICE FUNCTIONS ====================
    
    async def start_invoice_draft(self, customer_name: str) -> Dict[str, Any]:
        """
        Initialize a new invoice draft session.
        
        Args:
            customer_name: Customer name (fuzzy search)
        
        Returns:
            Success status, customer info, or error
        """
        # Search for customer (case-insensitive fuzzy search)
        customer = await self.db.customers.find_one(
            {"name": {"$regex": customer_name, "$options": "i"}},
            {"_id": 0}
        )
        
        if not customer:
            return {
                "success": False,
                "error": "customer_not_found",
                "message": f"Customer '{customer_name}' nahi mila. Kya naya customer banana hai?"
            }
        
        # Initialize invoice draft
        self.session.current_draft = {
            "type": "invoice",
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "items": [],
            "notes": None,
            "total": 0,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        }
        self.session.state = SessionState.INVOICE_DRAFT
        
        return {
            "success": True,
            "customer_name": customer["name"],
            "outstanding_balance": customer.get("balance", 0),
            "message": f"{customer['name']} selected ✓. Items batao?"
        }
    
    async def add_invoice_item(
        self,
        description: str,
        quantity: float,
        rate: float,
        product_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add a line item to current invoice draft.
        
        Args:
            description: Product description
            quantity: Quantity (must be > 0)
            rate: Unit price (must be > 0)
            product_id: Optional product ID if it exists in inventory
        
        Returns:
            Success status and updated total
        """
        # Validate session state
        if self.session.state != SessionState.INVOICE_DRAFT:
            return {
                "success": False,
                "error": "no_active_draft",
                "message": "Pehle invoice start karo"
            }
        
        # Validation
        if quantity <= 0:
            return {
                "success": False,
                "error": "invalid_quantity",
                "message": "Quantity 0 se zyada honi chahiye"
            }
        
        if rate <= 0:
            return {
                "success": False,
                "error": "invalid_rate",
                "message": "Rate 0 se zyada hona chahiye"
            }
        
        if not description.strip():
            return {
                "success": False,
                "error": "missing_description",
                "message": "Item description zaruri hai"
            }
        
        # If product_id provided, verify it exists
        if product_id:
            product = await self.db.products.find_one({"id": product_id}, {"_id": 0})
            if not product:
                product_id = None  # Ignore invalid product_id
        
        # Create item
        item = {
            "product_id": product_id,
            "description": description,
            "quantity": quantity,
            "rate": rate,
            "amount": quantity * rate
        }
        
        # Add to draft
        self.session.current_draft["items"].append(item)
        
        # Recalculate total
        self.session.current_draft["total"] = sum(
            i["amount"] for i in self.session.current_draft["items"]
        )
        
        return {
            "success": True,
            "item_added": f"{quantity} {description} @ ₹{rate}",
            "item_total": item["amount"],
            "invoice_total": self.session.current_draft["total"],
            "message": f"{quantity} {description} @ ₹{rate} = ₹{item['amount']} ✓"
        }
    
    async def remove_invoice_item(
        self,
        item_index: Optional[int] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Remove an item from invoice draft.
        
        Args:
            item_index: 0-based index of item to remove
            description: Description to match (if index not provided)
        
        Returns:
            Success status and updated total
        """
        if self.session.state != SessionState.INVOICE_DRAFT:
            return {
                "success": False,
                "error": "no_active_draft",
                "message": "Koi active draft nahi hai"
            }
        
        items = self.session.current_draft["items"]
        
        if not items:
            return {
                "success": False,
                "error": "no_items",
                "message": "Koi item nahi hai"
            }
        
        # Find item to remove
        if item_index is not None:
            if 0 <= item_index < len(items):
                removed_item = items.pop(item_index)
            else:
                return {
                    "success": False,
                    "error": "invalid_index",
                    "message": f"Item #{item_index + 1} nahi mila"
                }
        elif description:
            # Find by description (case-insensitive)
            found = False
            for i, item in enumerate(items):
                if description.lower() in item["description"].lower():
                    removed_item = items.pop(i)
                    found = True
                    break
            
            if not found:
                return {
                    "success": False,
                    "error": "item_not_found",
                    "message": f"'{description}' nahi mila"
                }
        else:
            # Remove last item if no criteria provided
            removed_item = items.pop()
        
        # Recalculate total
        self.session.current_draft["total"] = sum(
            i["amount"] for i in self.session.current_draft["items"]
        )
        
        return {
            "success": True,
            "item_removed": removed_item["description"],
            "updated_total": self.session.current_draft["total"],
            "message": f"{removed_item['description']} removed ✓. Total: ₹{self.session.current_draft['total']}"
        }
    
    async def update_invoice_notes(self, notes: str) -> Dict[str, Any]:
        """Add or update notes on the invoice."""
        if self.session.state != SessionState.INVOICE_DRAFT:
            return {
                "success": False,
                "error": "no_active_draft",
                "message": "Koi active draft nahi hai"
            }
        
        self.session.current_draft["notes"] = notes
        
        return {
            "success": True,
            "message": "Notes added ✓"
        }
    
    async def save_invoice(
        self,
        as_draft: bool = False,
        payment_received: float = 0
    ) -> Dict[str, Any]:
        """
        Save the invoice to database.
        
        Args:
            as_draft: Save as draft (true) or publish (false)
            payment_received: Amount of payment received (if any)
        
        Returns:
            Invoice number, total, and balance
        """
        if self.session.state != SessionState.INVOICE_DRAFT:
            return {
                "success": False,
                "error": "no_active_draft",
                "message": "Koi active draft nahi hai"
            }
        
        if not self.session.current_draft["items"]:
            return {
                "success": False,
                "error": "no_items",
                "message": "Invoice mein koi items nahi hain. Pehle items add karo"
            }
        
        # Atomic invoice number (shared counters collection with the REST path).
        invoice_number = f"INV-{await _next_seq(self.db, 'invoice'):05d}"
        
        # Calculate amounts
        total = self.session.current_draft["total"]
        paid_amount = min(payment_received, total)  # Can't pay more than total
        balance = total - paid_amount
        
        # Create invoice document
        invoice_doc = {
            "id": str(uuid.uuid4()),
            "invoice_number": invoice_number,
            "customer_id": self.session.current_draft["customer_id"],
            "items": self.session.current_draft["items"],
            "total": total,
            "paid_amount": paid_amount,
            "balance": balance,
            "date": self.session.current_draft["date"],
            "notes": self.session.current_draft.get("notes"),
            "is_draft": as_draft,
            "status": "draft" if as_draft else "unpaid" if balance > 0 else "paid",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": self.session.user_id
        }
        
        # Save to database
        await self.db.invoices.insert_one(invoice_doc)

        # Ledger + stock side-effects for non-draft invoices — same pattern
        # as app/routers/invoices.py::create_invoice. Drafts intentionally
        # skip these so they can be edited without churning ledger state.
        if not as_draft:
            invoice_date = invoice_doc["date"]
            invoice_id = invoice_doc["id"]
            await create_ledger_entry(
                account=f"customer:{invoice_doc['customer_id']}",
                debit=total,
                credit=0,
                narration=f"Invoice {invoice_number}",
                ref_type="invoice",
                ref_id=invoice_id,
                date=invoice_date,
            )
            await create_ledger_entry(
                account="sales",
                debit=0,
                credit=total,
                narration=f"Invoice {invoice_number}",
                ref_type="invoice",
                ref_id=invoice_id,
                date=invoice_date,
            )
            for item in invoice_doc["items"]:
                if item.get("product_id"):
                    await create_stock_movement(
                        item["product_id"],
                        0,
                        item["quantity"],
                        "invoice",
                        invoice_id,
                        invoice_date,
                    )

        # Reset session
        self.session.reset_draft()

        return {
            "success": True,
            "invoice_number": invoice_number,
            "total": total,
            "paid_amount": paid_amount,
            "balance": balance,
            "message": f"Invoice {invoice_number} saved! Total: ₹{total}, Balance: ₹{balance} ✓"
        }
    
    # ==================== PURCHASE FUNCTIONS ====================
    
    async def start_purchase_draft(self, supplier_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Initialize a new purchase draft session.
        
        Args:
            supplier_name: Supplier name (optional - can be cash purchase)
        
        Returns:
            Success status and supplier info
        """
        supplier_id = None
        supplier_display_name = "Cash Purchase"
        
        if supplier_name:
            # Search for supplier
            supplier = await self.db.suppliers.find_one(
                {"name": {"$regex": supplier_name, "$options": "i"}},
                {"_id": 0}
            )
            
            if not supplier:
                return {
                    "success": False,
                    "error": "supplier_not_found",
                    "message": f"Supplier '{supplier_name}' nahi mila. Cash purchase banana hai?"
                }
            
            supplier_id = supplier["id"]
            supplier_display_name = supplier["name"]
        
        # Initialize purchase draft
        self.session.current_draft = {
            "type": "purchase",
            "supplier_id": supplier_id,
            "supplier_name": supplier_display_name,
            "items": [],
            "payment_status": "unpaid",
            "notes": None,
            "total": 0,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        }
        self.session.state = SessionState.PURCHASE_DRAFT
        
        return {
            "success": True,
            "supplier_name": supplier_display_name,
            "message": f"{supplier_display_name} selected ✓. Items batao?"
        }
    
    async def add_purchase_item(
        self,
        product_name: str,
        quantity: float,
        cost_price: float
    ) -> Dict[str, Any]:
        """
        Add item to purchase draft.
        
        NOTE: Unlike invoices, purchase items MUST be existing products.
        Cannot add free-text items to purchases.
        
        Args:
            product_name: Product name (must exist in products collection)
            quantity: Quantity (must be > 0)
            cost_price: Purchase cost per unit (must be > 0)
        
        Returns:
            Success status and updated total
        """
        if self.session.state != SessionState.PURCHASE_DRAFT:
            return {
                "success": False,
                "error": "no_active_draft",
                "message": "Pehle purchase start karo"
            }
        
        # Validation
        if quantity <= 0:
            return {
                "success": False,
                "error": "invalid_quantity",
                "message": "Quantity 0 se zyada honi chahiye"
            }
        
        if cost_price <= 0:
            return {
                "success": False,
                "error": "invalid_cost_price",
                "message": "Cost price 0 se zyada hona chahiye"
            }
        
        # Find product (REQUIRED for purchases)
        product = await self.db.products.find_one(
            {"name": {"$regex": product_name, "$options": "i"}},
            {"_id": 0}
        )
        
        if not product:
            return {
                "success": False,
                "error": "product_not_found",
                "message": f"Product '{product_name}' inventory mein nahi hai. Pehle product add karo"
            }
        
        # Create item
        item = {
            "product_id": product["id"],
            "product_name": product["name"],
            "quantity": quantity,
            "cost_price": cost_price,
            "amount": quantity * cost_price
        }
        
        # Add to draft
        self.session.current_draft["items"].append(item)
        
        # Recalculate total
        self.session.current_draft["total"] = sum(
            i["amount"] for i in self.session.current_draft["items"]
        )
        
        return {
            "success": True,
            "item_added": f"{quantity} {product['name']} @ ₹{cost_price}",
            "item_total": item["amount"],
            "purchase_total": self.session.current_draft["total"],
            "message": f"{quantity} {product['name']} @ ₹{cost_price} = ₹{item['amount']} ✓"
        }
    
    async def remove_purchase_item(
        self,
        item_index: Optional[int] = None,
        product_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Remove item from purchase draft."""
        if self.session.state != SessionState.PURCHASE_DRAFT:
            return {
                "success": False,
                "error": "no_active_draft",
                "message": "Koi active draft nahi hai"
            }
        
        items = self.session.current_draft["items"]
        
        if not items:
            return {
                "success": False,
                "error": "no_items",
                "message": "Koi item nahi hai"
            }
        
        # Find item to remove (same logic as invoice)
        if item_index is not None:
            if 0 <= item_index < len(items):
                removed_item = items.pop(item_index)
            else:
                return {
                    "success": False,
                    "error": "invalid_index",
                    "message": f"Item #{item_index + 1} nahi mila"
                }
        elif product_name:
            found = False
            for i, item in enumerate(items):
                if product_name.lower() in item["product_name"].lower():
                    removed_item = items.pop(i)
                    found = True
                    break
            
            if not found:
                return {
                    "success": False,
                    "error": "item_not_found",
                    "message": f"'{product_name}' nahi mila"
                }
        else:
            removed_item = items.pop()
        
        # Recalculate total
        self.session.current_draft["total"] = sum(
            i["amount"] for i in self.session.current_draft["items"]
        )
        
        return {
            "success": True,
            "item_removed": removed_item["product_name"],
            "updated_total": self.session.current_draft["total"],
            "message": f"{removed_item['product_name']} removed ✓. Total: ₹{self.session.current_draft['total']}"
        }
    
    async def set_purchase_payment(self, payment_status: str) -> Dict[str, Any]:
        """
        Set payment status for purchase.
        
        Args:
            payment_status: "cash", "bank", or "unpaid"
        
        Returns:
            Success status
        """
        if self.session.state != SessionState.PURCHASE_DRAFT:
            return {
                "success": False,
                "error": "no_active_draft",
                "message": "Koi active draft nahi hai"
            }
        
        valid_statuses = ["cash", "bank", "unpaid"]
        if payment_status not in valid_statuses:
            return {
                "success": False,
                "error": "invalid_payment_status",
                "message": f"Payment status 'cash', 'bank', ya 'unpaid' hona chahiye"
            }
        
        self.session.current_draft["payment_status"] = payment_status
        
        return {
            "success": True,
            "payment_status": payment_status,
            "message": f"Payment: {payment_status} ✓"
        }
    
    async def save_purchase(self) -> Dict[str, Any]:
        """Save the purchase to database."""
        if self.session.state != SessionState.PURCHASE_DRAFT:
            return {
                "success": False,
                "error": "no_active_draft",
                "message": "Koi active draft nahi hai"
            }
        
        if not self.session.current_draft["items"]:
            return {
                "success": False,
                "error": "no_items",
                "message": "Purchase mein koi items nahi hain. Pehle items add karo"
            }
        
        # Atomic purchase number (shared counters collection with REST path).
        purchase_number = f"PUR-{await _next_seq(self.db, 'purchase'):05d}"
        
        # Create purchase document
        purchase_doc = {
            "id": str(uuid.uuid4()),
            "purchase_number": purchase_number,
            "supplier_id": self.session.current_draft["supplier_id"],
            "items": [
                {
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "cost_price": item["cost_price"]
                }
                for item in self.session.current_draft["items"]
            ],
            "total": self.session.current_draft["total"],
            "payment_status": self.session.current_draft["payment_status"],
            "date": self.session.current_draft["date"],
            "notes": self.session.current_draft.get("notes"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": self.session.user_id
        }
        
        # Save to database
        await self.db.purchases.insert_one(purchase_doc)

        # Ledger + stock side-effects — same pattern as
        # app/routers/purchases.py::create_purchase.
        purchase_id = purchase_doc["id"]
        purchase_date = purchase_doc["date"]
        payment_status = purchase_doc["payment_status"]
        supplier_id = purchase_doc.get("supplier_id")
        total = self.session.current_draft["total"]
        narration = f"Purchase {purchase_number}"

        if payment_status == "cash":
            await create_ledger_entry("cash", 0, total, narration, "purchase", purchase_id, purchase_date)
        elif payment_status == "bank":
            await create_ledger_entry("bank", 0, total, narration, "purchase", purchase_id, purchase_date)
        elif payment_status == "unpaid" and supplier_id:
            await create_ledger_entry(f"supplier:{supplier_id}", 0, total, narration, "purchase", purchase_id, purchase_date)

        # Debit inventory_asset (accrual, mirrors REST flow).
        await create_ledger_entry("inventory_asset", total, 0, narration, "purchase", purchase_id, purchase_date)

        # Update product cost_price + post stock-in movement per line item.
        for item in purchase_doc["items"]:
            if item.get("product_id"):
                await self.db.products.update_one(
                    {"id": item["product_id"]},
                    {"$set": {"cost_price": item["cost_price"]}},
                )
                await create_stock_movement(
                    item["product_id"],
                    item["quantity"],
                    0,
                    "purchase",
                    purchase_id,
                    purchase_date,
                )

        # Reset session
        self.session.reset_draft()

        return {
            "success": True,
            "purchase_number": purchase_number,
            "total": total,
            "message": f"Purchase {purchase_number} saved! Total: ₹{total} ✓"
        }
    
    # ==================== LOOKUP FUNCTIONS ====================
    
    async def search_customer(self, name: str) -> Dict[str, Any]:
        """Search for customer by name."""
        customer = await self.db.customers.find_one(
            {"name": {"$regex": name, "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1, "balance": 1}
        )
        
        if not customer:
            return {
                "found": False,
                "message": f"Customer '{name}' nahi mila"
            }
        
        return {
            "found": True,
            "customer": {
                "id": customer["id"],
                "name": customer["name"],
                "outstanding": customer.get("balance", 0)
            }
        }
    
    async def search_supplier(self, name: str) -> Dict[str, Any]:
        """Search for supplier by name."""
        supplier = await self.db.suppliers.find_one(
            {"name": {"$regex": name, "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1}
        )
        
        if not supplier:
            return {
                "found": False,
                "message": f"Supplier '{name}' nahi mila"
            }
        
        return {
            "found": True,
            "supplier": {
                "id": supplier["id"],
                "name": supplier["name"]
            }
        }
    
    async def search_product(self, query: str) -> Dict[str, Any]:
        """Search for product by name or SKU."""
        product = await self.db.products.find_one(
            {
                "$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"sku": {"$regex": query, "$options": "i"}}
                ]
            },
            {"_id": 0}
        )
        
        if not product:
            return {
                "found": False,
                "message": f"Product '{query}' nahi mila"
            }
        
        # Calculate current stock
        stock_result = await self.db.stock_movements.aggregate([
            {"$match": {"product_id": product["id"]}},
            {"$group": {
                "_id": None,
                "stock": {"$sum": "$quantity"}
            }}
        ]).to_list(1)
        
        current_stock = stock_result[0]["stock"] if stock_result else product.get("opening_stock", 0)
        
        return {
            "found": True,
            "product": {
                "id": product["id"],
                "name": product["name"],
                "sku": product.get("sku"),
                "selling_price": product["selling_price"],
                "cost_price": product.get("cost_price", 0),
                "current_stock": current_stock
            }
        }
    
    async def get_customer_outstanding(self, customer_name: str) -> Dict[str, Any]:
        """Get outstanding balance for a customer."""
        customer = await self.db.customers.find_one(
            {"name": {"$regex": customer_name, "$options": "i"}},
            {"_id": 0, "name": 1, "balance": 1}
        )
        
        if not customer:
            return {
                "found": False,
                "message": f"Customer '{customer_name}' nahi mila"
            }
        
        return {
            "found": True,
            "customer": customer["name"],
            "outstanding": customer.get("balance", 0),
            "message": f"{customer['name']} ka ₹{customer.get('balance', 0)} outstanding hai"
        }
    
    # ==================== SESSION MANAGEMENT ====================
    
    async def end_session(self) -> Dict[str, Any]:
        """End the voice session."""
        had_draft = self.session.current_draft is not None
        draft_type = self.session.current_draft.get("type") if had_draft else None
        
        self.session.reset_draft()
        
        return {
            "success": True,
            "session_ended": True,
            "had_unsaved_draft": had_draft,
            "draft_type": draft_type,
            "message": "Session ended. Namaste! 🙏"
        }
