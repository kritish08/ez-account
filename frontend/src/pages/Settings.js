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
  updateSystemSettings,
} from "../lib/api";
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
  const [s3Settings, setS3Settings] = useState({
    aws_access_key_id: "",
    aws_secret_access_key: "",
    bucket_name: "",
    region: "ap-south-1",
  });
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
  const [voiceAssistantEnabled, setVoiceAssistantEnabled] = useState(
    () => localStorage.getItem('voiceAssistantEnabled') !== 'false'
  );
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [resetPassword, setResetPassword] = useState("");
  const [resetConfirmation, setResetConfirmation] = useState("");
  const [resetting, setResetting] = useState(false);
  const RESET_PHRASE = "DELETE ALL ACCOUNTING DATA";

  useEffect(() => {
    fetchSettings();
  }, []);

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
      const moduleName = key === "enable_credit_notes" ? "Credit Notes" : key === "enable_debit_notes" ? "Debit Notes" : "Advanced IMS Features";
      toast.success(`${moduleName} ${checked ? "enabled" : "disabled"}`);
    } catch (error) {
      toast.error("Failed to update module settings");
      setModules(previous);
    }
  };

  const fetchSettings = async () => {
    try {
      const [settingsRes, backupsRes, sysRes] = await Promise.all([
        getS3Settings(),
        listBackups().catch(() => ({ data: { backups: [] } })),
        getSystemSettings().catch(() => ({ data: {} }))
      ]);

      if (sysRes.data) {
        setSystemSettings(prev => ({ ...prev, ...sysRes.data }));
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

    setRestoring(true);
    try {
      await restoreBackup(selectedBackup);
      toast.success("Backup restored successfully!");
      setRestoreDialogOpen(false);
      setSelectedBackup(null);
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
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleRestore} disabled={restoring} className="bg-amber-600 hover:bg-amber-700">
              {restoring ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Restoring...</> : "Restore Backup"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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
