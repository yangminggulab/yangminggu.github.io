export interface SearchIndexItem {
  id: string;
  blockType: string;
  blockTitle: string;
  content: string;
  rawContent: string;
  docTitle?: string;
  sectionTitle?: string;
  subsectionTitle?: string;
  sourcePath?: string;
  order: number;
  noteId: string;
  noteTitle: string;
  texPath: string;
  pdfPath?: string;
}

export interface SearchResult extends SearchIndexItem {
  score: number;
  snippet: string;
}

function normalizeQuery(text: string): string {
  return text.trim().toLowerCase();
}

function includesExact(text: string | undefined, query: string): boolean {
  if (!text) return false;
  return text.toLowerCase().includes(query);
}

function makeSnippet(content: string, query: string, radius = 40): string {
  const lower = content.toLowerCase();
  const index = lower.indexOf(query);

  if (index === -1) {
    return content.slice(0, radius * 2).trim();
  }

  const start = Math.max(0, index - radius);
  const end = Math.min(content.length, index + query.length + radius);

  let snippet = content.slice(start, end).trim();

  if (start > 0) snippet = "..." + snippet;
  if (end < content.length) snippet = snippet + "...";

  return snippet;
}

function scoreItem(item: SearchIndexItem, query: string): number {
  let score = 0;

  if (includesExact(item.blockTitle, query)) score += 100;
  if (includesExact(item.sectionTitle, query)) score += 40;
  if (includesExact(item.subsectionTitle, query)) score += 50;
  if (includesExact(item.docTitle, query)) score += 30;
  if (includesExact(item.noteTitle, query)) score += 30;
  if (includesExact(item.content, query)) score += 20;

  return score;
}

export function searchNotes(
  items: SearchIndexItem[],
  rawQuery: string,
): SearchResult[] {
  const query = normalizeQuery(rawQuery);

  if (!query) {
    return [];
  }

  const matched = items
    .map((item) => {
      const score = scoreItem(item, query);
      if (score <= 0) return null;

      const snippetSource =
        item.content || item.blockTitle || item.subsectionTitle || item.sectionTitle || "";

      return {
        ...item,
        score,
        snippet: makeSnippet(snippetSource, query),
      };
    })
    .filter((item): item is SearchResult => item !== null)
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.order - b.order;
    });

  return matched;
}
