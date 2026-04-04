"""
Voice Session Manager

Manages user voice sessions for interactive invoice/purchase creation.
Maintains session state, draft data, and conversation history.
"""

import uuid
from typing import Optional, Dict, List, Any
from datetime import datetime
from enum import Enum


class SessionState(str, Enum):
    IDLE = "idle"
    INVOICE_DRAFT = "invoice_draft"
    PURCHASE_DRAFT = "purchase_draft"


class VoiceSession:
    """
    Manages a single user's voice assistant session.
    
    Tracks:
    - Current state (idle, drafting invoice, drafting purchase)
    - Draft data (invoice or purchase being created)
    - Conversation history (for context)
    """
    
    def __init__(self, user_id: str, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id
        self.state = SessionState.IDLE
        self.current_draft: Optional[Dict[str, Any]] = None
        self.conversation_history: List[Dict[str, str]] = []
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
    
    def get_context(self) -> Dict[str, Any]:
        """
        Get current session context for AI.
        
        Returns context about what user is currently working on,
        which helps GPT-5.2 make better function calling decisions.
        """
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "has_active_draft": self.current_draft is not None,
            "draft_type": self.current_draft.get("type") if self.current_draft else None,
            "draft_summary": self._get_draft_summary()
        }
    
    def _get_draft_summary(self) -> Optional[Dict[str, Any]]:
        """Get a summary of the current draft for context."""
        if not self.current_draft:
            return None
        
        if self.current_draft["type"] == "invoice":
            return {
                "type": "invoice",
                "customer": self.current_draft.get("customer_name"),
                "items_count": len(self.current_draft.get("items", [])),
                "total": self.current_draft.get("total", 0)
            }
        elif self.current_draft["type"] == "purchase":
            return {
                "type": "purchase",
                "supplier": self.current_draft.get("supplier_name"),
                "items_count": len(self.current_draft.get("items", [])),
                "total": self.current_draft.get("total", 0)
            }
        
        return None
    
    def add_message(self, role: str, content: str):
        """Add a message to conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content
        })
        self.last_activity = datetime.utcnow()
    
    def reset_draft(self):
        """Clear current draft and return to idle state."""
        self.current_draft = None
        self.state = SessionState.IDLE
    
    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if session has been inactive for too long."""
        elapsed = (datetime.utcnow() - self.last_activity).total_seconds() / 60
        return elapsed > timeout_minutes
