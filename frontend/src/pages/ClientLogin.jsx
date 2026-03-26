import { useState, useEffect } from "react";
import client from "./assets/login.png"
import { useNavigate } from "react-router-dom";
export default function ClientLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isMobile, setIsMobile] = useState(window.innerWidth < 900);
const navigate = useNavigate();
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 900);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const handleLogin = (e) => {
    e.preventDefault();

    if (email === "client@gmail.com" && password === "open@123") {
      setError("");
        navigate("/layout",{replace:true});
    } else {
      setError("Invalid email or password");
    }
  };

  const containerStyle = {
    display: "flex",
    flexDirection: isMobile ? "column" : "row",
    minHeight: "100vh",
    fontFamily: "Segoe UI, sans-serif",
  };

  const leftStyle = {
    flex: 1,
    background: "linear-gradient(180deg, #0f1a24, #091018)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
 
    padding: isMobile ? "40px 20px" : 40,
  };

  const boxStyle = {
    width: "100%",
    maxWidth: 420,
    background: "rgba(255,255,255,0.05)",
    backdropFilter: "blur(18px)",
    borderRadius: 16,
   padding: isMobile ? "40px 20px" : 40,
    color: "#fff",
    boxShadow: "0 0 40px rgba(0,0,0,0.4)",
  };

  const inputStyle = {
    width: "100%",
    padding: 14,
    borderRadius: 8,
    border: "none",
    background: "rgba(255,255,255,0.08)",
    color: "white",
    marginBottom: 16,
    fontSize: 15,
    outline: "none",
  };

  const buttonStyle = {
    width: "100%",
    padding: 14,
    border: "none",
    borderRadius: 10,
    background: "linear-gradient(90deg, #3a8dff, #6bb7ff)",
    color: "white",
    fontSize: 16,
    cursor: "pointer",
    marginTop: 10,
  };

  const rightStyle = {
    flex: 1,
    backgroundImage: `url(${client})`,
    backgroundSize: "cover",
    backgroundPosition: "center",
    display: isMobile ? "none" : "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
    height: isMobile ? 280 : "auto",
  };

  const overlayStyle = {
    background: "rgba(0,20,40,0.65)",
    padding: 40,
    borderRadius: 20,
    color: "white",
    maxWidth: 500,
    textAlign: isMobile ? "center" : "left",
  };

  return (
    <div style={containerStyle}>
      {/* LEFT */}
      <div style={leftStyle}>
        <div style={boxStyle}>
          <h1 style={{ marginBottom: 20 }}>Feed Mill Intelligence</h1>
          <h2>Welcome user</h2>
          <p style={{ color: "#aab4c0", marginBottom: 25 }}>
            Enter your credentials to access your device .
          </p>

          <form onSubmit={handleLogin}>
            <input
              style={inputStyle}
              type="email"
              placeholder="Email@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <input
              style={inputStyle}
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginBottom: 10,
                fontSize: 14,
                color: "#cdd6df",
              }}
            >
              <label>
                <input type="checkbox" /> Remember me
              </label>
              <span style={{ color: "#6da8ff", cursor: "pointer" }}>
                Forgot Password?
              </span>
            </div>

            {error && (
              <p style={{ color: "#ff6b6b", marginBottom: 10 }}>{error}</p>
            )}

            <button style={buttonStyle}>Access Dashboard</button>
          </form>
        </div>
      </div>

      {/* RIGHT */}
      <div style={rightStyle}>
        <div style={overlayStyle}>
          <h1 style={{ fontSize: isMobile ? 24 : 36, marginBottom: 20 }}>
            Perfection in Every Pellet
          </h1>
          <p style={{ lineHeight: 1.6, color: "#d6e3f3" }}>
            From raw grain to finished feed, ensure exact nutritional balance
            in every batch. Automating formulation, eliminating waste, and
            guaranteeing flock health with precision dosing.
          </p>
        </div>
      </div>
    </div>
  );
}
