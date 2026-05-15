import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2, Fingerprint } from "lucide-react";

import { getAuthConfig, authenticatePasskeyBegin } from "../lib/api";
import { WebAuthnService } from "../lib/WebAuthnService";

const Login = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const { login, passkeyLogin } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("Please fill in all fields");
      return;
    }

    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back!");
      navigate("/");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Login failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  // Passkey flow: email is required so the server can return only this
  // user's registered credentials; the browser then triggers the platform
  // authenticator (Face ID / Touch ID / Windows Hello / hardware key).
  const handlePasskeyLogin = async () => {
    if (!email) {
      toast.error("Please enter your email to sign in with a passkey");
      return;
    }
    if (!WebAuthnService.isSupported()) {
      toast.error("Passkeys are not supported on this browser or device.");
      return;
    }

    setPasskeyLoading(true);
    try {
      const response = await authenticatePasskeyBegin(email);
      const assertion = await WebAuthnService.authenticate(response.data);
      await passkeyLogin(email, assertion);
      toast.success("Welcome back!");
      navigate("/");
    } catch (error) {
      console.error("Passkey authentication failed:", error);
      toast.error(error.response?.data?.detail || "Passkey login failed. Use your password instead.");
    } finally {
      setPasskeyLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left side - Image */}
      <div
        className="hidden lg:flex lg:w-1/2 bg-cover bg-center relative"
        style={{
          backgroundImage: `url('https://images.pexels.com/photos/12706241/pexels-photo-12706241.jpeg')`,
        }}
      >
        <div className="absolute inset-0 bg-slate-900/60" />
        <div className="relative z-10 flex flex-col justify-end p-12 text-white">
          <h1 className="text-4xl font-bold font-heading mb-4">EZ Accounts by Kyrex</h1>
          <p className="text-lg text-slate-200">
            Simple accounting for your wholesale business. No complexity, just results.
          </p>
        </div>
      </div>

      {/* Right side - Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-50">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold font-heading text-slate-900 lg:hidden mb-2">EZ Accounts by Kyrex</h1>
            <h2 className="text-2xl font-semibold font-heading text-slate-900">Welcome back</h2>
            <p className="text-slate-500 mt-2">Sign in to your account to continue</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email-input"
                className="h-11"
                autoComplete="email"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-testid="login-password-input"
                  className="h-11 pr-10"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              className="w-full h-11 bg-brand-600 hover:bg-brand-700"
              disabled={loading}
              data-testid="login-submit-btn"
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Signing in...
                </>
              ) : (
                "Sign in"
              )}
            </Button>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-slate-200" />
              </div>
              <div className="relative flex justify-center text-xs uppercase text-slate-500">
                <span className="bg-slate-50 px-2">Or continue with</span>
              </div>
            </div>

            <Button
              type="button"
              variant="outline"
              className="w-full h-11 border-brand-200 text-brand-700 hover:bg-brand-50"
              onClick={handlePasskeyLogin}
              disabled={passkeyLoading}
              data-testid="login-passkey-btn"
            >
              {passkeyLoading ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Approving...</>
              ) : (
                <><Fingerprint className="mr-2 h-4 w-4" />Sign in with Passkey</>
              )}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Login;
