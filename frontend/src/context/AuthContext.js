import React, { createContext, useContext, useState, useEffect } from "react";
import axios from "axios";

const AuthContext = createContext(null);

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Set the axios header eagerly at module load so the first render's API calls
// are authenticated. Without this, child components fetch before the
// AuthProvider's useEffect runs and the request goes out with no token.
const storedToken = localStorage.getItem("token");
if (storedToken) {
  axios.defaults.headers.common["Authorization"] = `Bearer ${storedToken}`;
}

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(storedToken);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
      fetchUser();
    } else {
      setLoading(false);
    }
  }, [token]);

  const fetchUser = async () => {
    try {
      const response = await axios.get(`${API}/auth/me`);
      setUser(response.data);
    } catch (error) {
      console.error("Failed to fetch user:", error);
      // The token is already rejected, so there is nothing for the server to
      // revoke — just drop it locally rather than firing a doomed request.
      clearSession();
    } finally {
      setLoading(false);
    }
  };

  // Shared token-acceptance step used by both password and passkey login.
  const acceptToken = (access_token) => {
    localStorage.setItem("token", access_token);
    axios.defaults.headers.common["Authorization"] = `Bearer ${access_token}`;
    setToken(access_token);
  };

  const login = async (email, password) => {
    const response = await axios.post(`${API}/auth/login`, { email, password });
    acceptToken(response.data.access_token);
    await fetchUser();
    return response.data;
  };

  // Passkey login — the WebAuthn assertion has already been collected by
  // the browser at this point; we just POST it to the server which verifies
  // the signature and issues a JWT exactly like the password path.
  const passkeyLogin = async (email, credentialData) => {
    const response = await axios.post(`${API}/auth/passkey/authenticate/complete`, {
      email,
      credential_data: credentialData,
    });
    acceptToken(response.data.access_token);
    await fetchUser();
    return response.data;
  };

  const clearSession = () => {
    localStorage.removeItem("token");
    delete axios.defaults.headers.common["Authorization"];
    setToken(null);
    setUser(null);
  };

  // Tell the server to revoke this token before dropping it locally.
  // Clearing localStorage alone left the token valid until it expired, so
  // anything that had copied it kept working. Local state is cleared
  // regardless of whether the call succeeds — being offline must not trap
  // someone in a signed-in UI.
  const logout = async ({ allDevices = false } = {}) => {
    try {
      await axios.post(`${API}/auth/${allDevices ? "logout-all" : "logout"}`);
    } catch {
      // Already expired, revoked, or unreachable — nothing to recover.
    } finally {
      clearSession();
    }
  };

  return (
    <AuthContext.Provider value={{ token, user, login, passkeyLogin, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
