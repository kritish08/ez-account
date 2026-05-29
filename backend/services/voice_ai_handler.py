"""
Voice AI Handler

Integrates GPT-5.5 with function calling for the voice assistant.
Handles audio transcription, intent recognition, and natural response generation.
"""

import asyncio
import io
import json
import os
from typing import Dict, Any, List, Optional

from openai import OpenAI

from .voice_session import VoiceSession
from .function_executor import FunctionExecutor


# GPT-5.5 Function Definitions (grounded in actual capabilities)
VOICE_ASSISTANT_FUNCTIONS = [
    {
        "name": "start_invoice_draft",
        "description": "Start creating a new invoice for a customer. Call this when user wants to create/start/banao a new invoice.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Customer name (will fuzzy search)"
                }
            },
            "required": ["customer_name"]
        }
    },
    {
        "name": "add_invoice_item",
        "description": "Add a line item to the current invoice draft. Call when user mentions items with quantity and price.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Product/item description"
                },
                "quantity": {
                    "type": "number",
                    "description": "Quantity (must be positive)"
                },
                "rate": {
                    "type": "number",
                    "description": "Unit price/rate (must be positive)"
                },
                "product_id": {
                    "type": "string",
                    "description": "Product ID if exists in inventory (optional)"
                }
            },
            "required": ["description", "quantity", "rate"]
        }
    },
    {
        "name": "remove_invoice_item",
        "description": "Remove an item from the invoice draft. Call when user says 'remove', 'delete', 'hata do'.",
        "parameters": {
            "type": "object",
            "properties": {
                "item_index": {
                    "type": "integer",
                    "description": "0-based index of item to remove (optional)"
                },
                "description": {
                    "type": "string",
                    "description": "Description to match for removal (optional)"
                }
            }
        }
    },
    {
        "name": "update_invoice_notes",
        "description": "Add or update notes on the invoice",
        "parameters": {
            "type": "object",
            "properties": {
                "notes": {
                    "type": "string",
                    "description": "Notes text"
                }
            },
            "required": ["notes"]
        }
    },
    {
        "name": "save_invoice",
        "description": "Save/complete the invoice. Call when user says 'save', 'done', 'ho gaya', 'complete'.",
        "parameters": {
            "type": "object",
            "properties": {
                "as_draft": {
                    "type": "boolean",
                    "description": "Save as draft (true) or publish immediately (false)",
                    "default": False
                },
                "payment_received": {
                    "type": "number",
                    "description": "Amount of payment received (if any)",
                    "default": 0
                }
            }
        }
    },
    {
        "name": "start_purchase_draft",
        "description": "Start creating a new purchase. Call when user wants to create/entry/banao a purchase or bill.",
        "parameters": {
            "type": "object",
            "properties": {
                "supplier_name": {
                    "type": "string",
                    "description": "Supplier name (optional - null for cash purchase)"
                }
            }
        }
    },
    {
        "name": "add_purchase_item",
        "description": "Add an item to purchase draft. NOTE: Product MUST exist in inventory.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Product name (must exist in inventory)"
                },
                "quantity": {
                    "type": "number",
                    "description": "Quantity purchased (must be positive)"
                },
                "cost_price": {
                    "type": "number",
                    "description": "Purchase cost per unit (must be positive)"
                }
            },
            "required": ["product_name", "quantity", "cost_price"]
        }
    },
    {
        "name": "remove_purchase_item",
        "description": "Remove item from purchase draft",
        "parameters": {
            "type": "object",
            "properties": {
                "item_index": {
                    "type": "integer",
                    "description": "0-based index (optional)"
                },
                "product_name": {
                    "type": "string",
                    "description": "Product name to match (optional)"
                }
            }
        }
    },
    {
        "name": "set_purchase_payment",
        "description": "Set payment status for the purchase. Call when user mentions payment method.",
        "parameters": {
            "type": "object",
            "properties": {
                "payment_status": {
                    "type": "string",
                    "enum": ["cash", "bank", "unpaid"],
                    "description": "Payment status"
                }
            },
            "required": ["payment_status"]
        }
    },
    {
        "name": "save_purchase",
        "description": "Save/complete the purchase. Call when user says 'save', 'done', 'ho gaya'.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "search_customer",
        "description": "Search for a customer by name. Use this to find customer details.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Customer name to search"
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "search_product",
        "description": "Search for a product by name or SKU. Use this to get product details.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product name or SKU to search"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_customer_outstanding",
        "description": "Get outstanding balance for a customer. Call when user asks 'kitna outstanding hai'.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Customer name"
                }
            },
            "required": ["customer_name"]
        }
    },
    {
        "name": "end_session",
        "description": "End the voice session. Call when user says 'bye', 'band karo', 'quit', 'exit'.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]


# System prompt (grounded in capabilities)
SYSTEM_PROMPT = """You are an AI assistant for EZ Account, a Hindi-English accounting software for Indian businesses.

**Your Role:**
Help users CREATE invoices and purchases through natural voice commands in Hinglish (mix of Hindi and English).

**Available Capabilities:**
1. Create Invoice Drafts
   - Add, remove, update line items
   - Set customer
   - Add notes
   - Save as draft or publish

2. Create Purchase Drafts
   - Add, remove items from existing products
   - Set supplier (optional - can be cash purchase)
   - Set payment status (cash/bank/unpaid)
   - Save purchase

3. Lookup Queries
   - Search customers, suppliers, products
   - Get customer outstanding balance

**Important Constraints:**
- Invoices REQUIRE a valid customer (must exist or be created first)
- Purchase items MUST be existing products (cannot add free-text items to purchases)
- All amounts must be positive numbers
- Dates default to today if not specified

**Out-of-Scope (Politely Decline):**
- Financial reports/analytics (profit, sales analysis)
- Historical data queries
- Editing existing invoices/purchases
- Creating customers/suppliers/products
- Payment recording (except during invoice/purchase creation)

**Response Style:**
- Speak in natural Hinglish
- Be concise and action-oriented
- Confirm actions: "10 notebooks added ✓"
- Use rupee symbol: ₹
- For errors: suggest solutions
- If unclear: ask clarifying questions

**Example Interactions:**
USER: "Nayi invoice banao"
YOU: Call start_invoice_draft() → "Customer ka naam?"

USER: "Ramesh Traders"  
YOU: Call start_invoice_draft(customer_name="Ramesh Traders") → "Ramesh Traders selected ✓. Outstanding: ₹5000. Items batao?"

USER: "10 notebooks @ 50 rupees"
YOU: Call add_invoice_item(description="notebooks", quantity=10, rate=50) → "10 notebooks @ ₹50 = ₹500 added ✓. Aur kuch?"

USER: "Pens hata do"
YOU: Call remove_invoice_item(description="pens") → "Pens removed ✓"

USER: "Save kar do"
YOU: Call save_invoice() → "Invoice INV-00123 saved! Total: ₹500 ✓"

**Error Handling:**
If something is unclear:
- Ask: "Quantity kitni hai?"
- Don't assume values
- Provide options when possible

For out-of-scope requests:
"Maaf kijiye, main abhi sirf invoice aur purchase banane mein madad kar sakta hoon. Kya aapko invoice ya purchase mein help chahiye?"

**Function Calling:**
You have access to functions. Use them appropriately based on user intent.
Always call functions when user requests actions - don't just acknowledge, actually execute!
"""


class VoiceAIHandler:
    """
    Handles GPT-5.5 integration for voice assistant.
    
    Manages:
    - Audio transcription
    - Intent recognition via function calling
    - Natural response generation
    """
    
    def __init__(self):
        # Get OpenAI client from environment
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_KEY")
        # Prefer the current GPT-5.5 deployment; keep the legacy GPT-5.2 var
        # name as a fallback so an older .env keeps working.
        deployment = (
            os.getenv("DEPLOYMENT_NAME_GPT55")
            or os.getenv("DEPLOYMENT_NAME_GPT52")
            or "gpt-5.5-one"
        )
        # Separate Whisper deployment for STT. Falls back to the GPT
        # deployment name only as a last resort — Azure will 404 if the
        # named deployment isn't actually a Whisper model.
        self.whisper_deployment = os.getenv("DEPLOYMENT_NAME_WHISPER", "whisper")

        if not endpoint or not api_key:
            raise ValueError("Azure OpenAI credentials missing in .env")

        # Use standard OpenAI client (as per working ref files)
        self.client = OpenAI(
            base_url=endpoint,
            api_key=api_key
        )
        self.deployment = deployment

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
    ) -> str:
        """
        Transcribe audio to text via Azure OpenAI Whisper.

        Args:
            audio_bytes: Raw audio payload (webm/opus from MediaRecorder,
                or any format Whisper accepts: mp3, mp4, m4a, wav, ogg…).
            mime_type: MIME hint; only used to pick a filename extension
                so Whisper sniffs the format correctly.

        Returns:
            Transcribed text. Empty string when audio is empty or the
            model produces no text — caller decides how to surface that.

        Raises:
            Propagates the underlying openai exception when the API call
            itself fails (auth/network/quota). The WS handler converts
            these to a `transcription_failed` frame so the UI can react.
        """
        if not audio_bytes:
            return ""

        # Whisper sniffs by filename extension. Keep this aligned with
        # what the frontend MediaRecorder produces (default webm/opus on
        # Chrome/Edge; Safari can emit mp4 — both are accepted).
        ext = "webm"
        if mime_type:
            if "mp4" in mime_type or "m4a" in mime_type:
                ext = "m4a"
            elif "ogg" in mime_type:
                ext = "ogg"
            elif "wav" in mime_type:
                ext = "wav"
            elif "mpeg" in mime_type or "mp3" in mime_type:
                ext = "mp3"

        # The openai SDK call is synchronous; run it on a thread so the
        # event loop keeps serving other WS frames during the upload.
        def _call() -> str:
            buf = io.BytesIO(audio_bytes)
            buf.name = f"voice.{ext}"
            resp = self.client.audio.transcriptions.create(
                model=self.whisper_deployment,
                file=buf,
            )
            # openai v1 returns a pydantic object with `.text`; some
            # Azure response shapes are plain strings — handle both.
            return getattr(resp, "text", None) or (resp if isinstance(resp, str) else "")

        text = await asyncio.to_thread(_call)
        return (text or "").strip()
    
    async def process_message(
        self,
        message: str,
        session: VoiceSession,
        executor: FunctionExecutor
    ) -> Dict[str, Any]:
        """
        Process a user message (text or transcribed audio).
        
        Args:
            message: User's message
            session: Current voice session
            executor: Function executor
        
        Returns:
            AI response with function results
        """
        # Add user message to history
        session.add_message("user", message)
        
        # Prepare messages for GPT with context
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *session.conversation_history
        ]
        
        # Add context about current state
        context = session.get_context()
        if context["has_active_draft"]:
            context_msg = f"\n\nCurrent Draft Context: {json.dumps(context['draft_summary'])}"
            messages[0]["content"] += context_msg
        
        # Convert functions to tools format for GPT-5.5
        tools = [
            {
                "type": "function",
                "function": func
            }
            for func in VOICE_ASSISTANT_FUNCTIONS
        ]
        
        # Call GPT-5.5 with tools (modern format)
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            tools=tools,
            tool_choice="auto",  # Let GPT decide when to call tools
            max_completion_tokens=500,
            temperature=0.7
        )
        
        message_response = response.choices[0].message
        
        # Check if GPT wants to call a tool
        if message_response.tool_calls:
            tool_call = message_response.tool_calls[0]  # Handle first tool call
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            # Execute the function
            function_result = await self._execute_function(
                function_name,
                function_args,
                executor
            )
            
            # Add tool call to history
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": tool_call.function.arguments
                    }
                }]
            })
            
            # Add tool result to history
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(function_result)
            })
            
            # Get natural language response based on function result
            final_response = self.client.chat.completions.create(
                model=self.deployment,
                messages=messages,
                max_completion_tokens=300,
                temperature=0.7
            )
            
            ai_message = final_response.choices[0].message.content
            session.add_message("assistant", ai_message)
            
            return {
                "success": True,
                "message": ai_message,
                "function_called": function_name,
                "function_result": function_result,
                "draft": session.current_draft
            }
        
        else:
            # No tool call - just a conversational response
            ai_message = message_response.content
            session.add_message("assistant", ai_message)
            
            return {
                "success": True,
                "message": ai_message,
                "function_called": None,
                "draft": session.current_draft
            }
    
    async def _execute_function(
        self,
        function_name: str,
        args: Dict[str, Any],
        executor: FunctionExecutor
    ) -> Dict[str, Any]:
        """
        Execute a function by name.
        
        Args:
            function_name: Name of function to execute
            args: Function arguments
            executor: Function executor instance
        
        Returns:
            Function execution result
        """
        # Map function names to executor methods
        function_map = {
            "start_invoice_draft": executor.start_invoice_draft,
            "add_invoice_item": executor.add_invoice_item,
            "remove_invoice_item": executor.remove_invoice_item,
            "update_invoice_notes": executor.update_invoice_notes,
            "save_invoice": executor.save_invoice,
            "start_purchase_draft": executor.start_purchase_draft,
            "add_purchase_item": executor.add_purchase_item,
            "remove_purchase_item": executor.remove_purchase_item,
            "set_purchase_payment": executor.set_purchase_payment,
            "save_purchase": executor.save_purchase,
            "search_customer": executor.search_customer,
            "search_product": executor.search_product,
            "get_customer_outstanding": executor.get_customer_outstanding,
            "end_session": executor.end_session
        }
        
        if function_name not in function_map:
            return {
                "success": False,
                "error": "unknown_function",
                "message": f"Function '{function_name}' not implemented"
            }
        
        # Execute the function
        try:
            result = await function_map[function_name](**args)
            return result
        except Exception as e:
            return {
                "success": False,
                "error": "execution_error",
                "message": f"Error: {str(e)}"
            }
