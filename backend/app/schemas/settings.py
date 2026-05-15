"""Settings / modules / backup-schedule / S3 / reset schemas."""

from typing import Optional
from pydantic import BaseModel


class ModulesSettings(BaseModel):
    enable_credit_notes: bool = True
    enable_debit_notes: bool = True
    enable_advanced_ims: bool = False
    enable_production: bool = False


class BackupScheduleSettings(BaseModel):
    """User-configurable cron schedule for the automatic S3 backup job."""
    enabled: bool = False
    frequency: str = "daily"          # "daily" | "weekly"
    time: str = "00:00"               # HH:MM 24h
    timezone: str = "UTC"             # IANA tz name
    day_of_week: Optional[int] = 0    # 0=Mon ... 6=Sun (only for weekly)


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
