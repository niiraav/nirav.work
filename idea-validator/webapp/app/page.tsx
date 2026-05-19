export default function HomePage() {
  return (
    <main className="p-8">
      <h1 className="text-3xl font-bold">Idea Validator</h1>
      <p className="mt-4 text-gray-600">
        Dual-agent deliberation engine — Synthesizer vs Skeptic
      </p>
      <div className="mt-8 space-y-4">
        <div className="p-4 border rounded-lg">
          <h2 className="text-xl font-semibold">Sessions</h2>
          <p className="text-sm text-gray-500">List + create new sessions</p>
        </div>
      </div>
    </main>
  );
}
