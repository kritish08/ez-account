import React, { useRef, useState, useEffect } from 'react';
import { Camera, X, Loader2, RefreshCw } from 'lucide-react';
import { Button } from './ui/button';
import { toast } from 'sonner';

export default function LiveCamera({ onCapture, onClose }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const fileInputRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [useNativeFallback, setUseNativeFallback] = useState(false);

  const startCamera = async () => {
    setLoading(true);
    setError(null);
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("Camera API not supported in this browser");
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } }
      });
      streamRef.current = mediaStream;
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }
    } catch (err) {
      console.error("Camera access error:", err);
      setError("Inline camera access failed. This usually happens on non-HTTPS connections or if permissions are denied.");
      setUseNativeFallback(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    startCamera();
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  const handleCapture = () => {
    if (!videoRef.current || !canvasRef.current) return;
    
    const video = videoRef.current;
    const canvas = canvasRef.current;
    
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    // Convert to file
    canvas.toBlob((blob) => {
      if (!blob) {
        toast.error("Failed to capture image");
        return;
      }
      const file = new File([blob], `capture_${Date.now()}.jpg`, { type: 'image/jpeg' });
      onCapture(file);
      onClose(); // Automatically close after capture
    }, 'image/jpeg', 0.9);
  };

  const handleNativeCapture = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      onCapture(file);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-[100] bg-black bg-opacity-95 flex flex-col items-center justify-center">
      {/* Hidden Native Input */}
      <input 
        type="file" 
        accept="image/*" 
        capture="environment" 
        ref={fileInputRef} 
        onChange={handleNativeCapture}
        className="hidden"
      />

      {/* Header Controls */}
      <div className="absolute top-4 left-4 right-4 flex justify-between items-center z-10">
        <Button variant="ghost" size="icon" onClick={startCamera} className="text-white hover:bg-white/20">
          <RefreshCw className="h-6 w-6" />
        </Button>
        <Button variant="ghost" size="icon" onClick={onClose} className="text-white hover:bg-white/20">
          <X className="h-6 w-6" />
        </Button>
      </div>

      {/* Video Feed */}
      <div className="relative w-full max-w-lg aspect-[3/4] sm:aspect-[4/3] bg-slate-900 rounded-lg overflow-hidden flex flex-col items-center justify-center shadow-2xl border border-slate-800">
        {loading && <Loader2 className="h-8 w-8 text-brand-500 animate-spin absolute" />}
        
        {!useNativeFallback ? (
          <video 
            ref={videoRef}
            autoPlay 
            playsInline 
            muted 
            className={`w-full h-full object-cover transition-opacity duration-300 ${loading || error ? 'opacity-0' : 'opacity-100'}`}
          />
        ) : (
          <div className="text-center p-6 space-y-4">
            <Camera className="h-16 w-16 text-slate-700 mx-auto" />
            <div className="space-y-1">
              <p className="text-white font-medium">Browser camera stream unavailable</p>
              <p className="text-slate-400 text-sm px-4">
                This often happens on non-HTTPS connections or if permissions are blocked.
              </p>
            </div>
            <Button 
              onClick={() => fileInputRef.current?.click()}
              className="bg-brand-600 hover:bg-brand-700 text-white mt-4"
            >
              Use System Camera
            </Button>
          </div>
        )}
        
        {error && !useNativeFallback && <div className="text-red-400 text-center px-4 absolute bg-red-900/50 p-3 rounded">{error}</div>}
        <canvas ref={canvasRef} className="hidden" />
      </div>

      {/* Footer Controls */}
      <div className="absolute bottom-10 left-0 right-0 flex flex-col items-center gap-6 z-10">
        {!useNativeFallback && (
          <>
            <button 
              onClick={handleCapture}
              disabled={loading || error}
              className="w-20 h-20 rounded-full bg-white border-[8px] border-slate-300 flex items-center justify-center disabled:opacity-50 hover:bg-slate-100 active:scale-95 transition-all shadow-lg"
            >
              <Camera className="h-8 w-8 text-slate-800" />
            </button>
            <Button 
              variant="outline" 
              onClick={() => fileInputRef.current?.click()}
              className="text-white border-white/20 hover:bg-white/10"
            >
              Switch to System Camera
            </Button>
          </>
        )}
      </div>
      
      {!useNativeFallback && (
        <div className="absolute bottom-4 text-center w-full text-slate-400 text-xs tracking-wide">
          Align bill inside frame and capture
        </div>
      )}
    </div>
  );
}
