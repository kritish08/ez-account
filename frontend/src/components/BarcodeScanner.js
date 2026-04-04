import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Html5Qrcode } from 'html5-qrcode';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Button } from './ui/button';
import { AlertTriangle, ScanLine, Camera } from 'lucide-react';

const SCANNER_ID = "ez-qr-scanner-container";

const BarcodeScanner = ({ open, onScan, onClose }) => {
  const html5QrcodeRef = useRef(null);
  const [error, setError] = useState("");
  const [started, setStarted] = useState(false);
  const mounted = useRef(false);

  const stopScanner = useCallback(async () => {
    if (html5QrcodeRef.current) {
      try {
        const state = html5QrcodeRef.current.getState();
        // State 2 = SCANNING, State 3 = PAUSED
        if (state === 2 || state === 3) {
          await html5QrcodeRef.current.stop();
        }
        html5QrcodeRef.current.clear();
      } catch (e) {
        // Ignore stop errors
      }
      html5QrcodeRef.current = null;
    }
    setStarted(false);
  }, []);

  const startScanner = useCallback(async () => {
    // Wait for DOM element to be available
    const container = document.getElementById(SCANNER_ID);
    if (!container || html5QrcodeRef.current) return;

    try {
      const html5Qrcode = new Html5Qrcode(SCANNER_ID);
      html5QrcodeRef.current = html5Qrcode;

      const cameras = await Html5Qrcode.getCameras();
      if (!cameras || cameras.length === 0) {
        throw new Error("No camera found. Please grant camera permission and try again.");
      }

      // Prefer back camera if available
      const camera = cameras.find(c => /back|rear|environment/i.test(c.label)) || cameras[0];

      await html5Qrcode.start(
        { deviceId: { exact: camera.id } },
        {
          fps: 10,
          qrbox: { width: 250, height: 250 },
          aspectRatio: 1.0,
        },
        (decodedText) => {
          if (mounted.current) {
            stopScanner().then(() => onScan(decodedText));
          }
        },
        () => {
          // Per-frame error - ignore
        }
      );
      if (mounted.current) setStarted(true);
    } catch (err) {
      console.error(err);
      if (mounted.current) {
        const msg = err?.message || "";
        if (msg.includes("Permission") || msg.includes("permission") || msg.includes("NotAllowed")) {
          setError("Camera permission denied. Please allow camera access in your browser settings.");
        } else if (msg.includes("No camera")) {
          setError(msg);
        } else {
          setError("Could not start camera. Please check permissions and try again.");
        }
      }
      html5QrcodeRef.current = null;
    }
  }, [onScan, stopScanner]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (open) {
      setError("");
      setStarted(false);
      // Wait for Dialog animation to finish so the div is visible
      const t = setTimeout(() => {
        if (mounted.current) startScanner();
      }, 300);
      return () => {
        clearTimeout(t);
        stopScanner();
      };
    } else {
      stopScanner();
    }
  }, [open, startScanner, stopScanner]);

  const handleClose = async () => {
    await stopScanner();
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) handleClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ScanLine className="h-5 w-5 text-brand-600" />
            Scan Barcode / QR Code
          </DialogTitle>
          <DialogDescription>
            Point your camera at an EZ-Account QR code to auto-fill the item.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col items-center justify-center gap-4 p-2">
          {error ? (
            <div className="flex flex-col items-center gap-3 py-6 w-full">
              <div className="h-12 w-12 bg-rose-100 rounded-full flex items-center justify-center">
                <AlertTriangle className="h-6 w-6 text-rose-600" />
              </div>
              <p className="text-sm text-rose-700 text-center font-medium">{error}</p>
              <Button variant="outline" size="sm" onClick={startScanner}>
                <Camera className="h-4 w-4 mr-2" />
                Try Again
              </Button>
            </div>
          ) : !started ? (
            <div className="flex flex-col items-center gap-2 py-6 text-slate-500 text-sm">
              <Camera className="h-8 w-8 animate-pulse" />
              <p>Starting camera…</p>
            </div>
          ) : null}

          {/* The div MUST always be in the DOM while open so html5-qrcode can attach */}
          <div
            id={SCANNER_ID}
            className="w-full max-w-sm rounded-xl overflow-hidden border-2 border-slate-200 bg-black"
            style={{ display: error ? 'none' : 'block', minHeight: started ? 'auto' : '0px' }}
          />

          <Button variant="outline" className="w-full" onClick={handleClose}>
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default BarcodeScanner;
