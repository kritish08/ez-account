"""Settings / modules / backup-schedule / S3 / reset schemas."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class ModulesSettings(BaseModel):
    enable_credit_notes: bool = True
    enable_debit_notes: bool = True
    enable_advanced_ims: bool = False
    enable_production: bool = False
    # GST is opt-in. Off means invoices behave exactly as they did before
    # the module existed — no tax fields, no tax accounts, no change to any
    # figure. An existing business must never find tax switched on under it,
    # and a business not registered for GST should never see the machinery.
    enable_gst: bool = False


class BackupScheduleSettings(BaseModel):
    """User-configurable cron schedule for the automatic S3 backup job."""
    enabled: bool = False
    # Only these two values dispatch to a CronTrigger in apply_backup_schedule;
    # the previous `str` accepted anything and silently fell through to a
    # daily cron, ignoring the user's intent.
    frequency: Literal["daily", "weekly"] = "daily"
    # HH:MM 24h. apply_backup_schedule falls back to 00:00 on a parse error,
    # but accepting malformed input silently was a footgun for testing.
    time: str = Field(default="00:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "UTC"             # IANA tz name; validated by apply_backup_schedule
    # 0=Mon ... 6=Sun. Only consulted for frequency="weekly".
    day_of_week: Optional[int] = Field(default=0, ge=0, le=6)


class S3Settings(BaseModel):
    aws_access_key_id: str
    aws_secret_access_key: str
    bucket_name: str
    region: str = "us-east-1"


class SystemSettings(BaseModel):
    registration_enabled: bool = False
    company_name: Optional[str] = None
    company_email: Optional[str] = None
    company_phone: Optional[str] = None
    company_address: Optional[str] = None
    tax_id: Optional[str] = None
    default_currency: Optional[str] = "₹"


class SystemResetRequest(BaseModel):
    password: str
    confirmation: str  # must equal RESET_CONFIRMATION_PHRASE (typed deliberately)


class BackupRestoreRequest(BaseModel):
    """Restore overwrites every collection in the archive — same blast
    radius as a factory reset, so it takes the same two extra factors."""
    password: str
    confirmation: str  # must equal RESTORE_CONFIRMATION_PHRASE (typed deliberately)
