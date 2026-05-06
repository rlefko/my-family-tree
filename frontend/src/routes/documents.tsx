import { createFileRoute } from "@tanstack/react-router";

import { useDocuments } from "@/api/endpoints/documents";

export const Route = createFileRoute("/documents")({
  component: DocumentsPage,
});

function DocumentsPage() {
  const { data, isLoading } = useDocuments();
  return (
    <section className="p-6">
      <h1 className="text-2xl font-semibold">Documents</h1>
      {isLoading ? <p className="mt-2">Loading...</p> : null}
      <table className="mt-4 w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-zinc-500">
          <tr>
            <th className="py-2">Filename</th>
            <th className="py-2">Kind</th>
            <th className="py-2">Status</th>
            <th className="py-2">Pages</th>
          </tr>
        </thead>
        <tbody>
          {(data?.items ?? []).map((doc) => (
            <tr key={doc.id} className="border-b border-zinc-100">
              <td className="py-2">{doc.original_filename}</td>
              <td className="py-2">{doc.kind}</td>
              <td className="py-2">{doc.status}</td>
              <td className="py-2">{doc.pages ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
