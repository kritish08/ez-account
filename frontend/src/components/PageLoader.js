import React from "react";

const PageLoader = () => {
    return (
        <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50/30 to-slate-100">
            {/* Animated Logo Mark */}
            <div className="relative flex items-center justify-center mb-8">
                {/* Outer spinning ring */}
                <div
                    className="absolute w-20 h-20 rounded-full border-4 border-transparent"
                    style={{
                        borderTopColor: "hsl(243, 75%, 51%)",
                        borderRightColor: "hsl(243, 75%, 51%, 0.3)",
                        animation: "spin 1s linear infinite",
                    }}
                />
                {/* Inner pulsing ring */}
                <div
                    className="absolute w-14 h-14 rounded-full border-2 border-transparent"
                    style={{
                        borderTopColor: "hsl(243, 75%, 51%, 0.5)",
                        borderLeftColor: "hsl(243, 75%, 51%, 0.5)",
                        animation: "spin 1.5s linear infinite reverse",
                    }}
                />
                {/* Center logo mark */}
                <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-lg shadow-lg"
                    style={{
                        background: "linear-gradient(135deg, hsl(243, 75%, 51%), hsl(243, 75%, 40%))",
                        animation: "pulse-soft 2s ease-in-out infinite",
                    }}
                >
                    EZ
                </div>
            </div>

            {/* Brand name */}
            <div className="text-center">
                <h2
                    className="text-xl font-bold text-slate-800 tracking-tight"
                    style={{ fontFamily: "'Manrope', sans-serif" }}
                >
                    EZ Accounts
                </h2>
                <p className="text-sm text-slate-400 mt-1 font-medium tracking-wide">
                    Loading your workspace…
                </p>
            </div>

            {/* Subtle progress dots */}
            <div className="flex gap-1.5 mt-8">
                {[0, 1, 2].map((i) => (
                    <div
                        key={i}
                        className="w-1.5 h-1.5 rounded-full"
                        style={{
                            background: "hsl(243, 75%, 51%)",
                            animation: `bounce-dot 1.2s ease-in-out infinite`,
                            animationDelay: `${i * 0.2}s`,
                        }}
                    />
                ))}
            </div>

            {/* Inline keyframes */}
            <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes pulse-soft {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(0.95); opacity: 0.85; }
        }
        @keyframes bounce-dot {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-6px); opacity: 1; }
        }
      `}</style>
        </div>
    );
};

export default PageLoader;
