import React from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Home, ArrowLeft, FileQuestion } from "lucide-react";
import { Button } from "../components/ui/button";

const NotFound = () => {
    const navigate = useNavigate();
    const { token } = useAuth();

    return (
        <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50/30 to-slate-100 px-4">
            {/* Decorative background circles */}
            <div
                className="absolute top-1/4 left-1/4 w-64 h-64 rounded-full opacity-5 pointer-events-none"
                style={{ background: "hsl(243, 75%, 51%)" }}
            />
            <div
                className="absolute bottom-1/4 right-1/4 w-96 h-96 rounded-full opacity-5 pointer-events-none"
                style={{ background: "hsl(243, 75%, 51%)" }}
            />

            <div className="relative text-center max-w-md">
                {/* Icon */}
                <div className="flex justify-center mb-6">
                    <div
                        className="w-20 h-20 rounded-2xl flex items-center justify-center shadow-lg"
                        style={{
                            background: "linear-gradient(135deg, hsl(243, 75%, 51%), hsl(243, 75%, 40%))",
                        }}
                    >
                        <FileQuestion className="w-10 h-10 text-white" />
                    </div>
                </div>

                {/* 404 number */}
                <div
                    className="text-8xl font-black mb-2 leading-none"
                    style={{
                        fontFamily: "'Manrope', sans-serif",
                        background: "linear-gradient(135deg, hsl(243, 75%, 51%), hsl(243, 75%, 65%))",
                        WebkitBackgroundClip: "text",
                        WebkitTextFillColor: "transparent",
                        backgroundClip: "text",
                    }}
                >
                    404
                </div>

                {/* Message */}
                <h1
                    className="text-2xl font-bold text-slate-800 mb-3"
                    style={{ fontFamily: "'Manrope', sans-serif" }}
                >
                    Page not found
                </h1>
                <p className="text-slate-500 mb-8 leading-relaxed">
                    The page you're looking for doesn't exist or has been moved.
                    Let's get you back on track.
                </p>

                {/* CTAs */}
                <div className="flex flex-col sm:flex-row gap-3 justify-center">
                    <Button
                        onClick={() => navigate(-1)}
                        variant="outline"
                        className="gap-2 border-slate-200 text-slate-600 hover:bg-slate-50"
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Go Back
                    </Button>

                    {token ? (
                        <Button
                            onClick={() => navigate("/")}
                            className="gap-2 text-white"
                            style={{ background: "hsl(243, 75%, 51%)" }}
                        >
                            <Home className="w-4 h-4" />
                            Go to Dashboard
                        </Button>
                    ) : (
                        <Button
                            onClick={() => navigate("/login")}
                            className="gap-2 text-white"
                            style={{ background: "hsl(243, 75%, 51%)" }}
                        >
                            <Home className="w-4 h-4" />
                            Go to Login
                        </Button>
                    )}
                </div>

                {/* Brand footer */}
                <p className="mt-10 text-xs text-slate-400 font-medium tracking-wide">
                    EZ Accounts by Kyrex
                </p>
            </div>
        </div>
    );
};

export default NotFound;
