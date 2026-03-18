"use client";

import { useMemo, useState } from "react";
import type { SearchIndexItem, SearchResult } from "../lib/search";
import { searchNotes } from "../lib/search";

interface SearchBoxProps {
  items: SearchIndexItem[];
  onResultsChange?: (results: SearchResult[], query: string) => void;
}

export default function SearchBox({
  items,
  onResultsChange,
}: SearchBoxProps) {
  const [query, setQuery] = useState("");

  const results = useMemo(() => {
    return searchNotes(items, query);
  }, [items, query]);

  function handleChange(value: string) {
    setQuery(value);
    const nextResults = searchNotes(items, value);
    onResultsChange?.(nextResults, value);
  }

  return (
    <div className="w-full max-w-3xl mx-auto">
      <div className="flex flex-col gap-3">
        <label htmlFor="notes-search" className="text-sm font-medium">
          Search notes
        </label>

        <input
          id="notes-search"
          type="text"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="输入关键词，例如 Real Analysis"
          className="w-full rounded-xl border px-4 py-3 outline-none"
        />

        <div className="text-sm opacity-70">
          {query.trim()
            ? `Found ${results.length} result${results.length === 1 ? "" : "s"}`
            : "Type a keyword to search"}
        </div>
      </div>
    </div>
  );
}
