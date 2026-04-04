import React, { createContext, useContext, useState, useEffect } from "react";
import { getModulesSettings } from "../lib/api";
import { useAuth } from "./AuthContext";

const ModulesContext = createContext({});

export const ModulesProvider = ({ children }) => {
  const { token } = useAuth();
  const [modules, setModules] = useState({
    enable_credit_notes: true,
    enable_debit_notes: true,
    enable_advanced_ims: false,
    enable_production: false,
  });
  const [loadingModules, setLoadingModules] = useState(true);

  const fetchModules = async () => {
    if (!token) {
      setLoadingModules(false);
      return;
    }
    try {
      const response = await getModulesSettings();
      setModules({
        enable_credit_notes: response.data.enable_credit_notes ?? true,
        enable_debit_notes:  response.data.enable_debit_notes  ?? true,
        enable_advanced_ims: response.data.enable_advanced_ims ?? false,
        enable_production:   response.data.enable_production   ?? false,
      });
    } catch (error) {
      console.error("Failed to load module settings:", error);
    } finally {
      setLoadingModules(false);
    }
  };

  useEffect(() => {
    fetchModules();
  }, [token]);

  return (
    <ModulesContext.Provider value={{ modules, setModules, fetchModules, loadingModules }}>
      {children}
    </ModulesContext.Provider>
  );
};

export const useModules = () => useContext(ModulesContext);
