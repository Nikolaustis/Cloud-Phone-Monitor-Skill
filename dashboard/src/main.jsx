import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import AICopilot from "./components/AICopilot.jsx";
import "./styles/globals.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
    <AICopilot />
  </React.StrictMode>,
);
