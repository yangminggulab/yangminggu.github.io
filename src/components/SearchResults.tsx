import type { SearchResult } from "../lib/search";

interface SearchResultsProps {
  results: SearchResult[];
  query: string;
}

export default function SearchResults({
  results,
  query,
}: SearchResultsProps) {
  if (!query.trim()) {
    return null;
  }

  if (results.length === 0) {
    return (
      <div className="w-full max-w-3xl mx-auto mt-6 rounded-2xl border p-4">
        <div className="text-base font-medium">No results</div>
        <div className="mt-1 text-sm opacity-70">
          No matching note blocks were found for “{query}”.
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl mx-auto mt-6 flex flex-col gap-4">
      {results.map((item) => (
        <div
          key={item.id}
          className="rounded-2xl border p-4 shadow-sm"
        >
          <div className="flex flex-col gap-2">
            <div className="text-xs uppercase tracking-wide opacity-60">
              {item.blockType}
            </div>

            <div className="text-lg font-semibold">
              {item.blockTitle || item.subsectionTitle || item.sectionTitle || item.noteTitle}
            </div>

            <div className="text-sm opacity-70">
              {item.noteTitle}
              {item.sectionTitle ? ` · ${item.sectionTitle}` : ""}
              {item.subsectionTitle ? ` · ${item.subsectionTitle}` : ""}
            </div>

            <div className="text-sm leading-6">
              {item.snippet}
            </div>

            <div className="flex flex-wrap gap-3 pt-2 text-sm">
              {item.pdfPath ? (
                <a
                  href={item.pdfPath}
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  Open PDF
                </a>
              ) : null}

              {item.sourcePath ? (
                <span className="opacity-60">{item.sourcePath}</span>
              ) : null}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
