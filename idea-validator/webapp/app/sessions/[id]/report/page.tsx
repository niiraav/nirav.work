export default function ReportPage({ params }: { params: { id: string } }) {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold">Report for {params.id}</h1>
      <p className="mt-4 text-gray-600">Final validation report (Week 3)</p>
    </main>
  );
}
