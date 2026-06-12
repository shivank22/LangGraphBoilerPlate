import { NavLink, Route, Routes } from "react-router-dom";
import { ChatPage } from "./pages/ChatPage";
import { InfoPage } from "./pages/InfoPage";
import { ThemeToggle } from "./theme";
import "./styles/chat.css";

export default function App() {
  return (
    <div className="app-container">
      <header className="topbar">
        <div className="topbar-left">
          <div className="topbar-brand">
            <span className="brand-icon">🤖</span>
            <span className="brand-text">DICE Agent</span>
          </div>
          <nav className="nav-links">
            <NavLink to="/" end>
              Chat
            </NavLink>
            <NavLink to="/info">Info</NavLink>
          </nav>
        </div>
        <ThemeToggle />
      </header>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/info" element={<InfoPage />} />
      </Routes>
    </div>
  );
}
