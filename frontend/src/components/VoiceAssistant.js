import React, { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, X, Loader2 } from 'lucide-react';
import './VoiceAssistant.css';

const VoiceAssistantInner = () => {
    const [isOpen, setIsOpen] = useState(false);
    const [isRecording, setIsRecording] = useState(false);
    const [isConnected, setIsConnected] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [messages, setMessages] = useState([]);
    const [draft, setDraft] = useState(null);
    const [sessionState, setSessionState] = useState('idle');
    const [permissionGranted, setPermissionGranted] = useState(false);
    const [audioLevel, setAudioLevel] = useState(0);

    // ALL refs must be declared before any early returns (Rules of Hooks)
    const ws = useRef(null);
    const mediaRecorder = useRef(null);
    const audioChunks = useRef([]);
    const audioContext = useRef(null);
    const analyser = useRef(null);
    const animationFrame = useRef(null);
    const messagesEndRef = useRef(null);

    // Auto-scroll
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const stopRecording = () => {
        if (mediaRecorder.current && mediaRecorder.current.state === 'recording') {
            mediaRecorder.current.stop();
            setIsRecording(false);
        }
    };

    const connectWebSocket = () => {
        const token = localStorage.getItem('token');
        if (!token) {
            console.error('No token found');
            return;
        }

        // Build WS URL from the backend HTTP URL (env-driven, no hardcoded host).
        // Token is sent via the first WebSocket message, NOT as a URL query
        // param, so it doesn't leak into proxy access logs / browser history.
        const httpBase = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';
        const wsUrl = httpBase.replace(/^http/, 'ws') + '/ws/voice';
        ws.current = new WebSocket(wsUrl);

        ws.current.onopen = () => {
            console.log('✅ WebSocket open — sending auth');
            ws.current.send(JSON.stringify({ type: 'auth', token }));
        };

        ws.current.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('📨 Received:', data);

            if (data.type === 'auth_required') {
                // Server prompted for auth — already sent in onopen; nothing to do.
                return;
            } else if (data.type === 'auth_failed') {
                console.error('Voice auth failed:', data.message);
                setIsConnected(false);
                ws.current?.close();
                return;
            } else if (data.type === 'connected') {
                setIsConnected(true);
                setMessages([{
                    role: 'assistant',
                    content: data.message,
                    timestamp: new Date()
                }]);
            } else if (data.type === 'response') {
                // Show what the model heard back (only for voice turns —
                // text turns send their own message via the input box, so
                // echoing the transcript there would double up).
                if (data.transcript) {
                    setMessages(prev => [
                        ...prev,
                        {
                            role: 'user',
                            content: data.transcript,
                            timestamp: new Date()
                        }
                    ]);
                }
                setMessages(prev => [
                    ...prev,
                    {
                        role: 'assistant',
                        content: data.response,
                        functionCalled: data.function_called,
                        timestamp: new Date()
                    }
                ]);

                if (data.draft) {
                    setDraft(data.draft);
                }
                setSessionState(data.state);
                setIsProcessing(false);
            } else if (data.type === 'transcription_failed') {
                setMessages(prev => [
                    ...prev,
                    {
                        role: 'error',
                        content: data.message || 'Could not transcribe audio. Try again.',
                        timestamp: new Date()
                    }
                ]);
                setIsProcessing(false);
            } else if (data.type === 'error') {
                setMessages(prev => [
                    ...prev,
                    {
                        role: 'error',
                        content: data.message,
                        timestamp: new Date()
                    }
                ]);
                setIsProcessing(false);
            }
        };

        ws.current.onerror = (error) => {
            console.error('❌ WebSocket error:', error);
            setIsConnected(false);
            setIsProcessing(false);
        };

        ws.current.onclose = () => {
            console.log('🔌 WebSocket closed');
            setIsConnected(false);
            setIsProcessing(false);
        };
    };

    // Connect WebSocket when panel opens
    useEffect(() => {
        if (isOpen && !isConnected) {
            connectWebSocket();
        }

        return () => {
            if (ws.current) {
                ws.current.close();
            }
            stopRecording();
        };
    }, [isOpen]);

    const requestMicrophonePermission = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            setPermissionGranted(true);

            // Stop the test stream
            stream.getTracks().forEach(track => track.stop());

            return true;
        } catch (error) {
            console.error('Microphone permission denied:', error);
            alert('🎤 Microphone permission required for voice assistant. Please allow microphone access.');
            return false;
        }
    };

    const visualizeAudio = () => {
        if (!analyser.current) return;

        const bufferLength = analyser.current.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const updateLevel = () => {
            analyser.current.getByteFrequencyData(dataArray);

            // Calculate average
            const average = dataArray.reduce((a, b) => a + b) / bufferLength;
            setAudioLevel(Math.min(average / 128, 1)); // Normalize to 0-1

            animationFrame.current = requestAnimationFrame(updateLevel);
        };

        updateLevel();
    };

    const startRecording = async () => {
        if (!permissionGranted) {
            const granted = await requestMicrophonePermission();
            if (!granted) return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            // Setup audio visualization
            audioContext.current = new (window.AudioContext || window.webkitAudioContext)();
            analyser.current = audioContext.current.createAnalyser();
            const source = audioContext.current.createMediaStreamSource(stream);
            source.connect(analyser.current);
            analyser.current.fftSize = 256;

            // Start visualization
            visualizeAudio();

            // Setup MediaRecorder
            mediaRecorder.current = new MediaRecorder(stream, {
                mimeType: 'audio/webm'
            });

            audioChunks.current = [];

            mediaRecorder.current.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.current.push(event.data);
                }
            };

            mediaRecorder.current.onstop = async () => {
                // Stop visualization + release the mic before any network work.
                if (animationFrame.current) {
                    cancelAnimationFrame(animationFrame.current);
                }
                setAudioLevel(0);
                stream.getTracks().forEach(track => track.stop());

                const chunks = audioChunks.current;
                audioChunks.current = [];
                if (!chunks.length) {
                    return;
                }

                if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
                    setMessages(prev => [
                        ...prev,
                        {
                            role: 'error',
                            content: 'Voice connection lost. Please reopen the assistant.',
                            timestamp: new Date()
                        }
                    ]);
                    return;
                }

                try {
                    setIsProcessing(true);
                    const blob = new Blob(chunks, { type: 'audio/webm' });
                    // FileReader → data URL → strip the `data:...;base64,` prefix.
                    // Smaller code than rolling our own ArrayBuffer→base64 loop.
                    const dataUrl = await new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onloadend = () => resolve(reader.result);
                        reader.onerror = reject;
                        reader.readAsDataURL(blob);
                    });
                    const b64 = String(dataUrl).split(',')[1] || '';
                    ws.current.send(JSON.stringify({
                        type: 'audio',
                        audio: b64,
                        mime: 'audio/webm'
                    }));
                } catch (err) {
                    console.error('Failed to send audio:', err);
                    setIsProcessing(false);
                    setMessages(prev => [
                        ...prev,
                        {
                            role: 'error',
                            content: 'Failed to send audio. Please try again.',
                            timestamp: new Date()
                        }
                    ]);
                }
            };

            mediaRecorder.current.start();
            setIsRecording(true);
        } catch (error) {
            console.error('Failed to start recording:', error);
            alert('Failed to start recording. Please check microphone permissions.');
        }
    };

    const togglePanel = async () => {
        if (!isOpen && !permissionGranted) {
            const granted = await requestMicrophonePermission();
            if (!granted) return;
        }
        setIsOpen(!isOpen);
    };

    const formatCurrency = (amount) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            minimumFractionDigits: 0
        }).format(amount);
    };

    return (
        <>
            {/* Floating Mic Button - Matches App Theme */}
            <button
                className={`voice-fab ${isOpen ? 'open' : ''} ${isRecording ? 'recording' : ''}`}
                onClick={togglePanel}
                title="Voice Assistant"
            >
                {isOpen ? (
                    <X className="h-6 w-6" />
                ) : (
                    <Mic className="h-6 w-6" />
                )}
                {isConnected && !isOpen && <span className="status-dot"></span>}
            </button>

            {/* Voice Panel */}
            {isOpen && (
                <div className="voice-panel">
                    {/* Header */}
                    <div className="voice-header">
                        <div className="flex items-center gap-2">
                            <Mic className="h-5 w-5" />
                            <h3 className="text-lg font-semibold">Voice Assistant</h3>
                        </div>
                        <span className={`status-badge ${isConnected ? 'connected' : 'disconnected'}`}>
                            {isConnected ? '● Connected' : '○ Connecting...'}
                        </span>
                    </div>

                    {/* Draft Preview */}
                    {draft && (
                        <div className="draft-card">
                            <div className="draft-card-header">
                                <span className="draft-type">
                                    {draft.type === 'invoice' ? '📄 Invoice' : '📦 Purchase'}
                                </span>
                                <span className="draft-badge">{sessionState.replace('_', ' ')}</span>
                            </div>

                            {draft.type === 'invoice' && (
                                <div className="draft-info">
                                    <div className="draft-row">
                                        <span>Customer:</span>
                                        <strong>{draft.customer_name}</strong>
                                    </div>
                                    <div className="draft-row">
                                        <span>Items:</span>
                                        <strong>{draft.items?.length || 0}</strong>
                                    </div>
                                    <div className="draft-row">
                                        <span>Total:</span>
                                        <strong className="text-brand-600">{formatCurrency(draft.total || 0)}</strong>
                                    </div>
                                </div>
                            )}

                            {draft.type === 'purchase' && (
                                <div className="draft-info">
                                    <div className="draft-row">
                                        <span>Supplier:</span>
                                        <strong>{draft.supplier_name}</strong>
                                    </div>
                                    <div className="draft-row">
                                        <span>Items:</span>
                                        <strong>{draft.items?.length || 0}</strong>
                                    </div>
                                    <div className="draft-row">
                                        <span>Total:</span>
                                        <strong className="text-brand-600">{formatCurrency(draft.total || 0)}</strong>
                                    </div>
                                    <div className="draft-row">
                                        <span>Payment:</span>
                                        <strong>{draft.payment_status}</strong>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Conversation */}
                    <div className="conversation">
                        {messages.map((msg, idx) => (
                            <div key={idx} className={`msg msg-${msg.role}`}>
                                <div className="msg-bubble">
                                    {msg.content}
                                    {msg.functionCalled && (
                                        <div className="function-tag">⚡ {msg.functionCalled}</div>
                                    )}
                                </div>
                                <div className="msg-time">
                                    {msg.timestamp.toLocaleTimeString('en-IN', {
                                        hour: '2-digit',
                                        minute: '2-digit'
                                    })}
                                </div>
                            </div>
                        ))}
                        {isProcessing && (
                            <div className="msg msg-assistant">
                                <div className="msg-bubble">
                                    <Loader2 className="h-4 w-4 animate-spin inline mr-2" />
                                    Processing...
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Voice Control */}
                    <div className="voice-control">
                        <button
                            className={`mic-button ${isRecording ? 'recording' : ''}`}
                            onMouseDown={startRecording}
                            onMouseUp={stopRecording}
                            onTouchStart={startRecording}
                            onTouchEnd={stopRecording}
                            disabled={!isConnected || isProcessing}
                        >
                            {isRecording ? (
                                <>
                                    <div className="pulse-ring"></div>
                                    <MicOff className="h-8 w-8" />
                                </>
                            ) : (
                                <Mic className="h-8 w-8" />
                            )}
                        </button>

                        {/* Audio Level Indicator */}
                        {isRecording && (
                            <div className="audio-bars">
                                {[...Array(5)].map((_, i) => (
                                    <div
                                        key={i}
                                        className="bar"
                                        style={{
                                            height: `${Math.max(20, audioLevel * 100 * (1 + Math.sin(Date.now() / 100 + i)))}%`
                                        }}
                                    />
                                ))}
                            </div>
                        )}

                        <p className="mic-hint">
                            {isRecording ? 'Release to send' : 'Hold to speak'}
                        </p>
                    </div>
                </div>
            )}
        </>
    );
};

const VoiceAssistant = () => {
    // Gated behind a Settings toggle (`voiceAssistantEnabled` in localStorage,
    // mirrors the `enable_voice` flag in /settings/modules). Default off so
    // tenants without configured Azure creds don't see a broken mic button.
    const [isEnabled, setIsEnabled] = useState(
        () => localStorage.getItem('voiceAssistantEnabled') === 'true'
    );

    // Listen for settings changes from the Settings page
    useEffect(() => {
        const handleStorage = (e) => {
            if (e.key === 'voiceAssistantEnabled') {
                setIsEnabled(e.newValue !== 'false');
            }
        };
        window.addEventListener('storage', handleStorage);
        // Also listen for same-tab custom events
        const handleCustom = (e) => setIsEnabled(e.detail !== false);
        window.addEventListener('voiceAssistantToggle', handleCustom);
        return () => {
            window.removeEventListener('storage', handleStorage);
            window.removeEventListener('voiceAssistantToggle', handleCustom);
        };
    }, []);

    if (!isEnabled) return null;

    return <VoiceAssistantInner />;
};

export default VoiceAssistant;
