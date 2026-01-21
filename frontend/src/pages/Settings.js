import React, { useState, useEffect } from "react";
import {
  getS3Settings,
  saveS3Settings,
  testS3Connection,
  createBackup,
  listBackups,
  restoreBackup,
  formatDate,
} from "../lib/api";
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
} from "lucide-react";

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
  const [connectionStatus, setConnectionStatus] = useState(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const [settingsRes, backupsRes] = await Promise.all([
        getS3Settings(),
        listBackups().catch(() => ({ data: { backups: [] } })),
      ]);
      
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
        <p className="text-slate-500 mt-1">Manage backups and cloud storage</p>
      </div>

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
    </div>
  );
};

export default Settings;
