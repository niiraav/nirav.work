export default function SessionPage({ params }: { params: { id: string } }) {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold">Session {params.id}</h1>
      <p className="mt-4 text-gray-600">Live transcript + gate UI (Week 3)</p>
    </main>
  );
}
