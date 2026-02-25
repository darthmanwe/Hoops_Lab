export const metadata = {
  title: "HoopsLab",
  description: "NBA + EuroLeague Intelligence Platform"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui", margin: 0, padding: 24 }}>
        {children}
      </body>
    </html>
  );
}
