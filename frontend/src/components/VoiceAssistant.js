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

        const wsUrl = `ws://localhost:8000/ws/voice?token=${token}`;
        ws.current = new WebSocket(wsUrl);

        ws.current.onopen = () => {
            console.log('✅ WebSocket connected');
            setIsConnected(true);
        };

        ws.current.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('📨 Received:', data);

            if (data.type === 'connected') {
                setMessages([{
                    role: 'assistant',
                    content: data.message,
                    timestamp: new Date()
                }]);
            } else if (data.type === 'response') {
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
                const audioBlob = new Blob(audioChunks.current, { type: 'audio/webm' });

                // Convert to base64 for sending (simplified for now)
                const reader = new FileReader();
                reader.onloadend = () => {
                    // For now, we'll just show a placeholder message
                    // In production, you'd send this to backend for transcription
                    setMessages(prev => [
                        ...prev,
                        {
                            role: 'user',
                            content: '[Voice Message - Transcribing...]',
                            timestamp: new Date()
                        }
                    ]);

                    setIsProcessing(true);

                    // TODO: Send audio to backend for transcription
                    // For demo, simulate with a timeout
                    setTimeout(() => {
                        ws.current.send(JSON.stringify({
                            type: 'text',
                            text: 'Nayi invoice banao' // Demo text
                        }));
                    }, 500);
                };
                reader.readAsDataURL(audioBlob);

                // Stop visualization
                if (animationFrame.current) {
                    cancelAnimationFrame(animationFrame.current);
                }
                setAudioLevel(0);

                // Stop all tracks
                stream.getTracks().forEach(track => track.stop());
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
    const [isEnabled, setIsEnabled] = useState(
        () => localStorage.getItem('voiceAssistantEnabled') !== 'false'
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
