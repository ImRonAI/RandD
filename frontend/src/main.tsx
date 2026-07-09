import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { AuthProvider, useAuth } from "@/auth/AuthContext";
import { Login } from "@/views/Login";

const Gate = () => {
  const { status } = useAuth();
  if (status === "loading") {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
        Loading…
      </div>
    );
  }
  if (status === "anonymous") {
    return <Login />;
  }
  return <App />;
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <Gate />
    </AuthProvider>
  </StrictMode>
);
