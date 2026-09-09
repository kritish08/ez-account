import React, { useState, useEffect } from "react";
import {
  getS3Settings,
  saveS3Settings,
  testS3Connection,
  createBackup,
  listBackups,
  restoreBackup,
  formatDate,
  updateModulesSettings,
  resetSystem,
  getSystemSettings,
  getOpenAISettings,
  saveOpenAISettings,
  testOpenAIKey,
  deleteOpenAIKey,
  updateSystemSettings,
  registerPasskeyBegin,
  registerPasskeyComplete,
  getPasskeys,
  deletePasskey,
  renamePasskey,
  getBackupSchedule,
  updateBackupSchedule,
} from "../lib/api";
import { WebAuthnService } from "../lib/WebAuthnService";
import { useModules } from "../context/ModulesContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import {
  Cloud,
  Shield,
  Download,
  Upload,
  RefreshCw,
  CheckCircle,
  XCircle,
  Loader2,
  AlertTriangle,
  Database,
  Lock,
  Settings as SettingsIcon,
  Mic,
  FileDown,
  FileUp,
  Package,
  Trash2,
  Fingerprint,
  Smartphone,
  Pencil,
  Info,
  Landmark,
  Sparkles,
} from "lucide-react";
import { Switch } from "../components/ui/switch";

const Settings = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [creatingBackup, setCreatingBackup] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [backups, setBackups] = useState([]);
  const [selectedBackup, setSelectedBackup] = useState(null);
  const [restoreDialogOpen, setRestoreDialogOpen] = useState(false);
  const [restorePassword, setRestorePassword] = useState("");
  const [restoreConfirmation, setRestoreConfirmation] = useState("");
  const RESTORE_PHRASE = "RESTORE AND OVERWRITE ALL DATA";
  const [s3Settings, setS3Settings] = useState({
    aws_access_key_id: "",
    aws_secret_access_key: "",
    bucket_name: "",
    region: "ap-south-1",
  });
  // AI credential. `aiKey` holds only what the user is typing right now —
  // the saved key never comes back from the server, so an empty box with a
  // configured status is the normal resting state.
  const [ai, setAi] = useState({ configured: false, source: "none", key_hint: "" });
  const [aiKey, setAiKey] = useState("");
  const [aiModel, setAiModel] = useState("");
  const [aiTesting, setAiTesting] = useState(false);
  const [aiSaving, setAiSaving] = useState(false);
  const [aiResult, setAiResult] = useState(null);
  const [systemSettings, setSystemSettings] = useState({
    company_name: "",
    company_email: "",
    company_phone: "",
    company_address: "",
    tax_id: "",
    default_currency: "₹",
  });
  const [savingCompany, setSavingCompany] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [updatingSystem, setUpdatingSystem] = useState(false);
  // Default OFF — must match VoiceAssistant.js. The previous `!== 'false'`
  // returned true when localStorage was null (fresh user), so the Settings
  // toggle showed ON while the VoiceAssistant component (which uses
  // `=== 'true'`) rendered nothing — the toggle and the actual feature
  // disagreed.
  const [voiceAssistantEnabled, setVoiceAssistantEnabled] = useState(
    () => localStorage.getItem('voiceAssistantEnabled') === 'true'
  );
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [resetPassword, setResetPassword] = useState("");
  const [resetConfirmation, setResetConfirmation] = useState("");
  const [resetting, setResetting] = useState(false);
  const RESET_PHRASE = "DELETE ALL ACCOUNTING DATA";

  // ----- Passkeys -----
  const [userPasskeys, setUserPasskeys] = useState([]);
  const [loadingPasskeys, setLoadingPasskeys] = useState(false);
  const [registeringPasskey, setRegisteringPasskey] = useState(false);
  const [renamingPk, setRenamingPk] = useState(null);
  const [newPkName, setNewPkName] = useState("");

  // ----- Backup schedule (cron) -----
  const [backupSchedule, setBackupSchedule] = useState({
    enabled: false,
    frequency: "daily",
    time: "02:00",
    timezone: "UTC",
    day_of_week: 0,
  });
  const [scheduleSaving, setScheduleSaving] = useState(false);

  useEffect(() => {
    fetchSettings();
    loadPasskeys();
    loadBackupSchedule();
  }, []);

  const loadBackupSchedule = async () => {
    try {
      const res = await getBackupSchedule();
      if (res.data) setBackupSchedule(prev => ({ ...prev, ...res.data }));
    } catch (err) {
      console.error("Failed to load backup schedule:", err);
    }
  };

  const handleSaveSchedule = async () => {
    setScheduleSaving(true);
    try {
      await updateBackupSchedule(backupSchedule);
      toast.success(
        backupSchedule.enabled
          ? `Auto-backup scheduled (${backupSchedule.frequency} at ${backupSchedule.time} ${backupSchedule.timezone})`
          : "Auto-backup disabled"
      );
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to save schedule");
    } finally {
      setScheduleSaving(false);
    }
  };

  const loadPasskeys = async () => {
    setLoadingPasskeys(true);
    try {
      const response = await getPasskeys();
      setUserPasskeys(response.data || []);
    } catch (err) {
      console.error("Failed to load passkeys:", err);
    } finally {
      setLoadingPasskeys(false);
    }
  };

  const handleRegisterPasskey = async () => {
    if (!WebAuthnService.isSupported()) {
      toast.error("Passkeys aren't supported on this browser or device.");
      return;
    }
    setRegisteringPasskey(true);
    try {
      const response = await registerPasskeyBegin();
      const credential = await WebAuthnService.register(response.data);
      await registerPasskeyComplete({ registration_data: credential });
      toast.success("Passkey registered");
      loadPasskeys();
    } catch (error) {
      console.error("Passkey registration failed:", error);
      // WebAuthn typically requires a secure context (HTTPS or localhost);
      // surface that hint when the browser refuses.
      toast.error(
        error.response?.data?.detail
          || error.message
          || "Passkey registration failed. Make sure you're on HTTPS or localhost."
      );
    } finally {
      setRegisteringPasskey(false);
    }
  };

  const handleDeletePasskey = async (id) => {
    try {
      await deletePasskey(id);
      toast.success("Passkey removed");
      loadPasskeys();
    } catch {
      toast.error("Failed to remove passkey");
    }
  };

  const handleRenamePasskey = async () => {
    if (!renamingPk || !newPkName.trim()) return;
    try {
      await renamePasskey(renamingPk.id, newPkName.trim());
      toast.success("Passkey renamed");
      setRenamingPk(null);
      setNewPkName("");
      loadPasskeys();
    } catch {
      toast.error("Failed to rename passkey");
    }
  };

  const handleVoiceToggle = (checked) => {
    setVoiceAssistantEnabled(checked);
    localStorage.setItem('voiceAssistantEnabled', String(checked));
    // Dispatch custom event so VoiceAssistant reacts immediately (same tab)
    window.dispatchEvent(new CustomEvent('voiceAssistantToggle', { detail: checked }));
    toast.success(checked ? 'Voice Assistant enabled' : 'Voice Assistant disabled');
  };

  const { modules, setModules } = useModules();
  
  const handleModuleToggle = async (key, checked) => {
    // Capture the previous value EXPLICITLY before the optimistic update.
    // The previous code did `setModules(modules)` in the catch, but by that
    // point `modules` from the closure might already reflect the optimistic
    // change (depending on render scheduling), making the rollback a no-op.
    const previous = { ...modules };
    const newSettings = { ...modules, [key]: checked };
    setModules(newSettings);
    try {
      await updateModulesSettings(newSettings);
      const MODULE_NAMES = {
        enable_credit_notes: "Returns from customers",
        enable_debit_notes: "Returns to suppliers",
        enable_advanced_ims: "Advanced IMS Features",
        enable_production: "Production Module",
        enable_gst: "GST",
      };
      const moduleName = MODULE_NAMES[key] || key;
      toast.success(`${moduleName} ${checked ? "enabled" : "disabled"}`);
    } catch (error) {
      toast.error("Failed to update module settings");
      setModules(previous);
    }
  };

  const fetchSettings = async () => {
    try {
      const [settingsRes, backupsRes, sysRes, aiRes] = await Promise.all([
        getS3Settings(),
        listBackups().catch(() => ({ data: { backups: [] } })),
        getSystemSettings().catch(() => ({ data: {} })),
        getOpenAISettings().catch(() => ({ data: null })),
      ]);

      if (sysRes.data) {
        setSystemSettings(prev => ({ ...prev, ...sysRes.data }));
      }

      if (aiRes.data) {
        setAi(aiRes.data);
        setAiModel(aiRes.data.model || "");
      }

      if (settingsRes.data && settingsRes.data.configured) {
        setS3Settings({
          aws_access_key_id: settingsRes.data.aws_access_key_id || "",
          aws_secret_access_key: "",
          bucket_name: settingsRes.data.bucket_name || "",
          region: settingsRes.data.region || "ap-south-1",
        });
        setConnectionStatus("connected");
      }

      setBackups(backupsRes.data.backups || []);
    } catch (error) {
      console.error("Failed to load settings:", error);
    } finally {
      setLoading(false);
    }
  };

  // The mask means "keep the key you already have" — sending it lets the
  // user change the model without re-pasting a key they no longer have.
  const AI_KEY_MASK = "********";
  const aiKeyToSend = () => (aiKey.trim() ? aiKey.trim() : ai.configured ? AI_KEY_MASK : "");

  const handleTestAIKey = async () => {
    const key = aiKeyToSend();
    if (!key) {
      toast.error("Paste your OpenAI API key first");
      return;
    }
    setAiTesting(true);
    setAiResult(null);
    try {
      const res = await testOpenAIKey({ api_key: key, model: aiModel || undefined });
      setAiResult(res.data);
      if (res.data.success) toast.success("Key works");
      else toast.error(res.data.message || "That key did not work");
    } catch (err) {
      const message = err.response?.data?.detail || "Could not reach OpenAI";
      setAiResult({ success: false, message });
      toast.error(message);
    } finally {
      setAiTesting(false);
    }
  };

  const handleSaveAIKey = async () => {
    const key = aiKeyToSend();
    if (!key) {
      toast.error("Paste your OpenAI API key first");
      return;
    }
    setAiSaving(true);
    try {
      await saveOpenAISettings({ api_key: key, model: aiModel || undefined });
      setAiKey("");           // never keep the plaintext key in component state
      setAiResult(null);
      await fetchSettings();
      toast.success("OpenAI key saved");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not save the key");
    } finally {
      setAiSaving(false);
    }
  };

  const handleRemoveAIKey = async () => {
    setAiSaving(true);
    try {
      const res = await deleteOpenAIKey();
      setAiKey("");
      setAiResult(null);
      await fetchSettings();
      toast.success(
        res.data?.source === "env"
          ? "Key removed — falling back to the server's OPENAI_API_KEY"
          : "Key removed. AI features are now off."
      );
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not remove the key");
    } finally {
      setAiSaving(false);
    }
  };

  const handleSaveCompany = async () => {
    setSavingCompany(true);
    try {
      await updateSystemSettings(systemSettings);
      toast.success("Company profile saved");
    } catch (err) {
      toast.error("Failed to save company profile");
    } finally {
      setSavingCompany(false);
    }
  };

  const handleTestConnection = async () => {
    if (!s3Settings.aws_access_key_id || !s3Settings.aws_secret_access_key || !s3Settings.bucket_name) {
      toast.error("Please fill in all S3 fields");
      return;
    }

    setTesting(true);
    try {
      const response = await testS3Connection(s3Settings);
      if (response.data.success) {
        setConnectionStatus("connected");
        toast.success("Connection successful!");
      } else {
        setConnectionStatus("error");
        toast.error(response.data.message || "Connection failed");
      }
    } catch (error) {
      setConnectionStatus("error");
      toast.error(error.response?.data?.detail || "Connection test failed");
    } finally {
      setTesting(false);
    }
  };

  const handleSaveSettings = async () => {
    if (!s3Settings.aws_access_key_id || !s3Settings.aws_secret_access_key || !s3Settings.bucket_name) {
      toast.error("Please fill in all S3 fields");
      return;
    }

    setSaving(true);
    try {
      await saveS3Settings(s3Settings);
      setConnectionStatus("connected");
      toast.success("S3 settings saved and validated!");
      fetchSettings();
    } catch (error) {
      setConnectionStatus("error");
      toast.error(error.response?.data?.detail || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleCreateBackup = async () => {
    setCreatingBackup(true);
    try {
      const response = await createBackup();
      toast.success(`Backup created: ${response.data.filename}`);
      fetchSettings();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Backup failed");
    } finally {
      setCreatingBackup(false);
    }
  };

  const handleRestore = async () => {
    if (!selectedBackup) return;
    if (!restorePassword) return toast.error("Password required");
    if (restoreConfirmation !== RESTORE_PHRASE) {
      return toast.error(`Confirmation phrase must be exactly: ${RESTORE_PHRASE}`);
    }

    setRestoring(true);
    try {
      await restoreBackup(selectedBackup, {
        password: restorePassword,
        confirmation: restoreConfirmation,
      });
      toast.success("Backup restored successfully!");
      setRestoreDialogOpen(false);
      setSelectedBackup(null);
      setRestorePassword("");
      setRestoreConfirmation("");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Restore failed");
    } finally {
      setRestoring(false);
    }
  };

  const handleFactoryReset = async () => {
    if (!resetPassword) return toast.error("Password required");
    if (resetConfirmation !== RESET_PHRASE) {
      return toast.error(`Confirmation phrase must be exactly: ${RESET_PHRASE}`);
    }
    setResetting(true);
    try {
      await resetSystem({ password: resetPassword, confirmation: resetConfirmation });
      toast.success("Application reset successfully");
      setResetDialogOpen(false);
      window.location.reload();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Factory reset failed");
    } finally {
      setResetting(false);
      setResetPassword("");
      setResetConfirmation("");
    }
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in max-w-3xl" data-testid="settings-page">
      <div>
        <h1 className="text-2xl font-bold font-heading text-slate-900">Settings</h1>
        <p className="text-slate-500 mt-1">Manage application features, backups and cloud storage</p>
      </div>

      {/* Application Features */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SettingsIcon className="h-5 w-5 text-brand-600" />
            Application Features
          </CardTitle>
          <CardDescription>Enable or disable application features</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-4 border rounded-lg bg-slate-50/50">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-brand-50 flex items-center justify-center">
                <Mic className="h-4 w-4 text-brand-600" />
              </div>
              <div className="space-y-0.5">
                <Label className="text-base font-medium cursor-pointer">Voice Assistant</Label>
                <p className="text-sm text-slate-500">
                  Floating mic button for voice-powered invoice creation
                </p>
              </div>
            </div>
            <Switch
              checked={voiceAssistantEnabled}
              onCheckedChange={handleVoiceToggle}
              data-testid="voice-assistant-toggle"
            />
          </div>

          <div className="flex items-center justify-between p-4 border rounded-lg bg-slate-50/50">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-brand-50 flex items-center justify-center">
                <FileDown className="h-4 w-4 text-brand-600" />
              </div>
              <div className="space-y-0.5">
                <Label className="text-base font-medium cursor-pointer">Credit Notes</Label>
                <p className="text-sm text-slate-500">
                  Enable tracking of Sales Returns via Credit Notes 
                </p>
              </div>
            </div>
            <Switch
              checked={modules?.enable_credit_notes ?? true}
              onCheckedChange={(checked) => handleModuleToggle("enable_credit_notes", checked)}
              data-testid="credit-notes-toggle"
            />
          </div>

          <div className="flex items-center justify-between p-4 border rounded-lg bg-slate-50/50">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-brand-50 flex items-center justify-center">
                <FileUp className="h-4 w-4 text-brand-600" />
              </div>
              <div className="space-y-0.5">
                <Label className="text-base font-medium cursor-pointer">Debit Notes</Label>
                <p className="text-sm text-slate-500">
                  Enable tracking of Purchase Returns via Debit Notes 
                </p>
              </div>
            </div>
            <Switch
              checked={modules?.enable_debit_notes ?? true}
              onCheckedChange={(checked) => handleModuleToggle("enable_debit_notes", checked)}
              data-testid="debit-notes-toggle"
            />
          </div>

          <div className="flex items-center justify-between p-4 border rounded-lg bg-emerald-50/50 border-emerald-100">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-emerald-100 flex items-center justify-center">
                <Package className="h-4 w-4 text-emerald-600" />
              </div>
              <div className="space-y-0.5">
                <Label className="text-base font-medium cursor-pointer text-emerald-900">Advanced IMS Features</Label>
                <p className="text-sm text-emerald-700/80">
                  Enable Serial Numbers, Batches, and Detailed Stock History
                </p>
              </div>
            </div>
            <Switch
              checked={modules?.enable_advanced_ims ?? false}
              onCheckedChange={(checked) => handleModuleToggle("enable_advanced_ims", checked)}
              data-testid="advanced-ims-toggle"
            />
          </div>

          {/* Production Module Toggle */}
          <div className="flex items-center justify-between rounded-lg border border-violet-200 bg-violet-50 p-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-violet-100 flex items-center justify-center">
                <Package className="h-4 w-4 text-violet-600" />
              </div>
              <div className="space-y-0.5">
                <Label className="text-base font-medium cursor-pointer text-violet-900">Production Module</Label>
                <p className="text-sm text-violet-700/80">
                  Bill of Materials, Work Orders, Raw Material tracking &amp; WIP
                </p>
              </div>
            </div>
            <Switch
              checked={modules?.enable_production ?? false}
              onCheckedChange={(checked) => handleModuleToggle("enable_production", checked)}
              data-testid="production-module-toggle"
            />
          </div>

          {/* GST Module Toggle */}
          <div className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 p-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-emerald-100 flex items-center justify-center">
                <Landmark className="h-4 w-4 text-emerald-600" />
              </div>
              <div className="space-y-0.5">
                <Label className="text-base font-medium cursor-pointer text-emerald-900">GST</Label>
                <p className="text-sm text-emerald-700/80">
                  Charge CGST/SGST or IGST on invoices, show the tax breakup on
                  the PDF, and track tax collected separately from revenue.
                  Leave off if you are not GST-registered.
                </p>
                {modules?.enable_gst && (
                  <p className="text-xs text-emerald-700/70 pt-1">
                    Set your GSTIN in Business Setup and a GST rate on each
                    product. Invoices already issued are not changed.
                  </p>
                )}
              </div>
            </div>
            <Switch
              checked={modules?.enable_gst ?? false}
              onCheckedChange={(checked) => handleModuleToggle("enable_gst", checked)}
              data-testid="gst-module-toggle"
            />
          </div>

        </CardContent>
      </Card>

      {/* Security & Passkeys */}
      <Card className="border-brand-200 bg-brand-50/20 shadow-sm overflow-hidden">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-brand-600" />
            Security & Passkeys
          </CardTitle>
          <CardDescription>Biometric / hardware-key login. Replaces passwords with a private key that never leaves your device.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 border rounded-lg bg-white shadow-sm gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-brand-100 flex items-center justify-center">
                <Fingerprint className="h-5 w-5 text-brand-600" />
              </div>
              <div>
                <p className="font-semibold text-slate-900">Add this device</p>
                <p className="text-sm text-slate-500">Use Face ID, Touch ID, Windows Hello, or a hardware security key</p>
              </div>
            </div>
            <Button
              onClick={handleRegisterPasskey}
              disabled={registeringPasskey}
              className="bg-brand-600 hover:bg-brand-700 whitespace-nowrap shadow-sm"
              data-testid="passkey-register-btn"
            >
              {registeringPasskey ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Initialising...</>
              ) : (
                "Register This Device"
              )}
            </Button>
          </div>

          {userPasskeys.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-slate-700 px-1">Registered devices</h4>
              <div className="border rounded-lg bg-white divide-y shadow-sm">
                {userPasskeys.map((pk) => (
                  <div key={pk.id} className="flex items-center justify-between p-3.5 group hover:bg-slate-50 transition-colors">
                    <div className="flex items-center gap-3">
                      <Smartphone className="h-5 w-5 text-slate-400 group-hover:text-brand-500 transition-colors" />
                      <div>
                        <p className="text-sm font-medium text-slate-900">{pk.name || "Biometric Device"}</p>
                        <p className="text-xs text-slate-500">
                          Added {pk.created_at ? new Date(pk.created_at).toLocaleDateString() : "—"}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => { setRenamingPk(pk); setNewPkName(pk.name || ""); }}
                        className="text-slate-400 hover:text-brand-600 h-8 w-8"
                        title="Rename"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeletePasskey(pk.id)}
                        className="text-slate-400 hover:text-red-600 hover:bg-red-50 h-8 w-8"
                        title="Remove"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {loadingPasskeys && userPasskeys.length === 0 && (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          )}

          <div className="flex items-start gap-2 text-xs text-slate-500 bg-brand-50/50 p-3 rounded-lg border border-brand-100">
            <Info className="h-4 w-4 text-brand-500 mt-0.5 flex-shrink-0" />
            <p>
              Passkeys replace passwords with a cryptographic key. Even if the server is breached,
              your private key never leaves this device. Requires HTTPS (or localhost) and a browser
              with WebAuthn support.
            </p>
          </div>
        </CardContent>
      </Card>

      <Dialog open={!!renamingPk} onOpenChange={(v) => !v && setRenamingPk(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename Passkey</DialogTitle>
            <DialogDescription>Give this passkey a friendly name to identify which device it lives on.</DialogDescription>
          </DialogHeader>
          <Input
            value={newPkName}
            onChange={(e) => setNewPkName(e.target.value)}
            placeholder="e.g. My MacBook"
            onKeyDown={(e) => e.key === "Enter" && handleRenamePasskey()}
            autoFocus
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenamingPk(null)}>Cancel</Button>
            <Button onClick={handleRenamePasskey} className="bg-brand-600 hover:bg-brand-700">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* AI credential — bring your own OpenAI key */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-brand-600" />
            AI features
          </CardTitle>
          <CardDescription>
            Bill scanning and the voice assistant run on your own OpenAI account.
            Usage is billed to that account.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
              ai.configured ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"
            }`}
            data-testid="ai-status"
          >
            {ai.configured ? (
              <>
                <CheckCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <span>
                  {ai.source === "settings" ? (
                    <>Key saved here, ending <span className="font-mono">{ai.key_hint}</span>.</>
                  ) : (
                    <>Using the server's <span className="font-mono">OPENAI_API_KEY</span>, ending{" "}
                      <span className="font-mono">{ai.key_hint}</span>. Saving a key below overrides it.</>
                  )}
                  {ai.model ? <> Model <span className="font-mono">{ai.model}</span>.</> : null}
                </span>
              </>
            ) : (
              <>
                <XCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <span>
                  No key configured — bill scanning and the voice assistant are off.
                  The rest of the app is unaffected.
                </span>
              </>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="openai_api_key">OpenAI API key</Label>
              <Input
                id="openai_api_key"
                type="password"
                autoComplete="off"
                inputMode="text"
                value={aiKey}
                onChange={(e) => setAiKey(e.target.value)}
                placeholder={ai.configured ? "Leave blank to keep the saved key" : "sk-..."}
                data-testid="openai-key-input"
              />
              <p className="text-xs text-slate-500">
                Create one at platform.openai.com → API keys. It is encrypted before
                it is stored and never shown again.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="openai_model">Model</Label>
              <Input
                id="openai_model"
                value={aiModel}
                onChange={(e) => setAiModel(e.target.value)}
                placeholder="gpt-5.6"
                data-testid="openai-model-input"
              />
              <p className="text-xs text-slate-500">
                Leave blank for the default. Test the key to see what your account can use.
              </p>
            </div>
          </div>

          {aiResult && (
            <div
              className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
                aiResult.success ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
              }`}
              data-testid="ai-test-result"
            >
              {aiResult.success ? (
                <CheckCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
              ) : (
                <XCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
              )}
              <span>
                {aiResult.message}
                {aiResult.requested_model_available === false && (
                  <> That model is not available to this account.</>
                )}
              </span>
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            <Button variant="outline" onClick={handleTestAIKey} disabled={aiTesting} data-testid="test-openai-btn">
              {aiTesting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Testing...</> : <><RefreshCw className="mr-2 h-4 w-4" />Test key</>}
            </Button>
            <Button onClick={handleSaveAIKey} disabled={aiSaving} className="bg-brand-600 hover:bg-brand-700" data-testid="save-openai-btn">
              {aiSaving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</> : "Save key"}
            </Button>
            {ai.saved_in_settings && (
              <Button variant="outline" onClick={handleRemoveAIKey} disabled={aiSaving} data-testid="remove-openai-btn">
                Remove key
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* S3 Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cloud className="h-5 w-5 text-brand-600" />
            Cloud Backup (Amazon S3)
          </CardTitle>
          <CardDescription>Configure S3 for encrypted database backups</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="aws_access_key_id">AWS Access Key ID</Label>
              <Input
                id="aws_access_key_id"
                value={s3Settings.aws_access_key_id}
                onChange={(e) => setS3Settings((prev) => ({ ...prev, aws_access_key_id: e.target.value }))}
                placeholder="AKIA..."
                data-testid="s3-access-key-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="aws_secret_access_key">AWS Secret Access Key</Label>
              <Input
                id="aws_secret_access_key"
                type="password"
                value={s3Settings.aws_secret_access_key}
                onChange={(e) => setS3Settings((prev) => ({ ...prev, aws_secret_access_key: e.target.value }))}
                placeholder="Enter secret key"
                data-testid="s3-secret-key-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="bucket_name">S3 Bucket Name</Label>
              <Input
                id="bucket_name"
                value={s3Settings.bucket_name}
                onChange={(e) => setS3Settings((prev) => ({ ...prev, bucket_name: e.target.value }))}
                placeholder="my-backup-bucket"
                data-testid="s3-bucket-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="region">AWS Region</Label>
              <Input
                id="region"
                value={s3Settings.region}
                onChange={(e) => setS3Settings((prev) => ({ ...prev, region: e.target.value }))}
                placeholder="ap-south-1"
                data-testid="s3-region-input"
              />
            </div>
          </div>

          {/* Connection Status */}
          {connectionStatus && (
            <div className={`flex items-center gap-2 p-3 rounded-lg ${connectionStatus === "connected" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
              {connectionStatus === "connected" ? (
                <><CheckCircle className="h-4 w-4" /><span>Connected to S3</span></>
              ) : (
                <><XCircle className="h-4 w-4" /><span>Connection error</span></>
              )}
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="outline" onClick={handleTestConnection} disabled={testing} data-testid="test-s3-btn">
              {testing ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Testing...</> : <><RefreshCw className="mr-2 h-4 w-4" />Test Connection</>}
            </Button>
            <Button onClick={handleSaveSettings} disabled={saving} className="bg-brand-600 hover:bg-brand-700" data-testid="save-s3-btn">
              {saving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</> : "Save Settings"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Backup Management */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-brand-600" />
            Backup Management
          </CardTitle>
          <CardDescription>Create and restore encrypted backups</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3 p-4 bg-blue-50 rounded-lg text-blue-700 text-sm">
            <Database className="h-5 w-5 flex-shrink-0" />
            <div>
              <p className="font-medium">Encryption enabled</p>
              <p className="text-blue-600">All backups are encrypted using AES-256-GCM with envelope encryption</p>
            </div>
          </div>

          <Button onClick={handleCreateBackup} disabled={creatingBackup || connectionStatus !== "connected"} className="bg-brand-600 hover:bg-brand-700" data-testid="create-backup-btn">
            {creatingBackup ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Creating backup...</>
            ) : (
              <><Upload className="mr-2 h-4 w-4" />Create Backup Now</>
            )}
          </Button>

          {/* Backup List */}
          {backups.length > 0 ? (
            <div className="border rounded-lg divide-y">
              {backups.map((backup) => (
                <div key={backup.filename} className="flex items-center justify-between p-4">
                  <div>
                    <p className="font-medium text-slate-900">{backup.filename}</p>
                    <p className="text-sm text-slate-500">
                      {formatDate(backup.last_modified)} • {formatBytes(backup.size_bytes)}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => { setSelectedBackup(backup.filename); setRestoreDialogOpen(true); }}
                    data-testid={`restore-backup-${backup.filename}`}
                  >
                    <Download className="h-4 w-4 mr-1" />
                    Restore
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500 text-sm text-center py-8">
              {connectionStatus === "connected" ? "No backups found. Create your first backup above." : "Configure S3 to enable backups"}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Restore Confirmation Dialog */}
      <AlertDialog open={restoreDialogOpen} onOpenChange={setRestoreDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              Restore Backup
            </AlertDialogTitle>
            <AlertDialogDescription>
              This will replace all current data with data from the backup "{selectedBackup}".
              This action cannot be undone. Make sure to create a new backup first if you want to preserve current data.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="restore-password">Confirm your password</Label>
              <Input
                id="restore-password"
                type="password"
                value={restorePassword}
                onChange={(e) => setRestorePassword(e.target.value)}
                placeholder="Your account password"
                autoComplete="current-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="restore-confirmation">
                Confirmation phrase — type <code className="font-mono text-xs">{RESTORE_PHRASE}</code>
              </Label>
              <Input
                id="restore-confirmation"
                value={restoreConfirmation}
                onChange={(e) => setRestoreConfirmation(e.target.value)}
                placeholder={RESTORE_PHRASE}
              />
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRestore}
              disabled={!restorePassword || restoreConfirmation !== RESTORE_PHRASE || restoring}
              className="bg-amber-600 hover:bg-amber-700"
            >
              {restoring ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Restoring...</> : "Restore Backup"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Scheduled Backup */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cloud className="h-5 w-5 text-brand-600" />
            Automatic Backup Schedule
          </CardTitle>
          <CardDescription>
            Run the encrypted S3 backup on a cron schedule. Requires S3 configured above and <code>MASTER_ENCRYPTION_KEY</code> set on the server.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-3 border rounded-lg bg-white">
            <div>
              <p className="font-medium text-slate-900">Enabled</p>
              <p className="text-sm text-slate-500">When off, no automatic backups will run.</p>
            </div>
            <Switch
              checked={backupSchedule.enabled}
              onCheckedChange={(checked) => setBackupSchedule(s => ({ ...s, enabled: checked }))}
              data-testid="backup-schedule-toggle"
            />
          </div>

          {backupSchedule.enabled && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Frequency</Label>
                <select
                  className="w-full h-10 border rounded-md px-3 bg-white text-sm"
                  value={backupSchedule.frequency}
                  onChange={(e) => setBackupSchedule(s => ({ ...s, frequency: e.target.value }))}
                >
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                </select>
              </div>
              {backupSchedule.frequency === "weekly" && (
                <div className="space-y-2">
                  <Label>Day of week</Label>
                  <select
                    className="w-full h-10 border rounded-md px-3 bg-white text-sm"
                    value={backupSchedule.day_of_week}
                    onChange={(e) => setBackupSchedule(s => ({ ...s, day_of_week: parseInt(e.target.value, 10) }))}
                  >
                    <option value={0}>Monday</option>
                    <option value={1}>Tuesday</option>
                    <option value={2}>Wednesday</option>
                    <option value={3}>Thursday</option>
                    <option value={4}>Friday</option>
                    <option value={5}>Saturday</option>
                    <option value={6}>Sunday</option>
                  </select>
                </div>
              )}
              <div className="space-y-2">
                <Label>Time (HH:MM, 24h)</Label>
                <Input
                  type="time"
                  value={backupSchedule.time}
                  onChange={(e) => setBackupSchedule(s => ({ ...s, time: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>Timezone</Label>
                <Input
                  placeholder="UTC, Asia/Kolkata, America/Los_Angeles, ..."
                  value={backupSchedule.timezone}
                  onChange={(e) => setBackupSchedule(s => ({ ...s, timezone: e.target.value }))}
                />
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <Button
              onClick={handleSaveSchedule}
              disabled={scheduleSaving}
              className="bg-brand-600 hover:bg-brand-700"
              data-testid="backup-schedule-save-btn"
            >
              {scheduleSaving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</> : "Save Schedule"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Danger Zone */}
      <Card className="border-red-200 border-dashed bg-red-50/30 mt-8">
        <CardHeader>
          <CardTitle className="text-red-700 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Danger Zone
          </CardTitle>
          <CardDescription className="text-red-600/80">
            Irreversible destructive actions for your environment.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between border border-red-100 bg-white p-4 rounded-lg">
            <div>
              <h4 className="text-sm font-bold text-slate-900">Factory Reset Application</h4>
              <p className="text-sm text-slate-500 mt-1">
                Permanently wipe all invoices, customers, inventory, and accounting ledgers.
              </p>
            </div>
            <Button variant="destructive" onClick={() => setResetDialogOpen(true)}>
              <Trash2 className="h-4 w-4 mr-2" /> Replace & Reset
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog open={resetDialogOpen} onOpenChange={setResetDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle className="text-red-600 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Confirm Factory Reset
            </DialogTitle>
            <DialogDescription>
              This action cannot be undone. All financial data will be permanently wiped.
              Verify your password and type the confirmation phrase exactly to continue.
              Rate-limited to one reset per hour per user.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="password">Administrator Password</Label>
              <Input
                id="password"
                type="password"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
                placeholder="Enter password..."
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmation">
                Confirmation phrase — type <code className="font-mono">{RESET_PHRASE}</code>
              </Label>
              <Input
                id="confirmation"
                type="text"
                value={resetConfirmation}
                onChange={(e) => setResetConfirmation(e.target.value)}
                placeholder={RESET_PHRASE}
                autoComplete="off"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setResetDialogOpen(false); setResetPassword(""); setResetConfirmation(""); }}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleFactoryReset}
              disabled={!resetPassword || resetConfirmation !== RESET_PHRASE || resetting}
            >
              {resetting ? "Erasing..." : "Permanently Erase Database"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Settings;
