export const metadata = {
  title: "Idea Validator",
  description: "Dual-agent startup idea validation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white">{children}</body>
    </html>
  );
}
