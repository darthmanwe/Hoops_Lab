export const metadata = {
  title: "HoopsLab",
  description: "NBA + EuroLeague Intelligence Platform"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui", margin: 0, padding: 24 }}>
        <nav style={{ marginBottom: 16 }}>
          <a href="/" style={{ marginRight: 12 }}>
            Home
          </a>
          <a href="/games" style={{ marginRight: 12 }}>
            Games
          </a>
          <a href="/leaderboards" style={{ marginRight: 12 }}>
            Leaderboards
          </a>
          <a href="/compare" style={{ marginRight: 12 }}>
            Compare
          </a>
          <a href="/lineup-lab">Lineup Lab</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
