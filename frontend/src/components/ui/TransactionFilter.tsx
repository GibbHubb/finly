import type { Category } from "@/types";

const CATEGORIES: Category[] = [
  "housing", "food", "transport", "entertainment",
  "health", "shopping", "salary", "freelance", "other",
];

export interface TagBriefForFilter {
  id: number;
  name: string;
}

export interface TransactionFilterProps {
  // Text / category / date / amount filter state (owned by parent)
  filterText: string;
  setFilterText: (v: string) => void;
  filterCategory: Category | "all";
  setFilterCategory: (v: Category | "all") => void;
  filterDateFrom: string;
  setFilterDateFrom: (v: string) => void;
  filterDateTo: string;
  setFilterDateTo: (v: string) => void;
  filterAmountMin: string;
  setFilterAmountMin: (v: string) => void;
  filterAmountMax: string;
  setFilterAmountMax: (v: string) => void;

  // Derived / clear
  hasActiveFilters: boolean;
  onClear: () => void;

  // Tag chip multi-select (owned by parent)
  availableTags: TagBriefForFilter[];
  selectedTags: string[];
  onToggleTag: (name: string) => void;
}

/**
 * F30 — Purely presentational filter bar.
 * All state is owned by DashboardPage; this component only renders and calls
 * the provided setters/handlers. No local state.
 */
export default function TransactionFilter({
  filterText, setFilterText,
  filterCategory, setFilterCategory,
  filterDateFrom, setFilterDateFrom,
  filterDateTo, setFilterDateTo,
  filterAmountMin, setFilterAmountMin,
  filterAmountMax, setFilterAmountMax,
  hasActiveFilters, onClear,
  availableTags, selectedTags, onToggleTag,
}: TransactionFilterProps) {
  return (
    <div className="tx-filter-bar">
      <input
        type="text"
        placeholder="🔍 Search description or category..."
        value={filterText}
        onChange={(e) => setFilterText(e.target.value)}
        className="tx-filter-search"
      />
      <div className="tx-filter-row">
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value as Category | "all")}
          className="tx-filter-input"
        >
          <option value="all">All categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input
          type="date"
          value={filterDateFrom}
          onChange={(e) => setFilterDateFrom(e.target.value)}
          className="tx-filter-input"
          title="From"
        />
        <input
          type="date"
          value={filterDateTo}
          onChange={(e) => setFilterDateTo(e.target.value)}
          className="tx-filter-input"
          title="To"
        />
        <input
          type="number"
          placeholder="Min €"
          value={filterAmountMin}
          onChange={(e) => setFilterAmountMin(e.target.value)}
          className="tx-filter-input tx-filter-num"
          step="0.01"
        />
        <input
          type="number"
          placeholder="Max €"
          value={filterAmountMax}
          onChange={(e) => setFilterAmountMax(e.target.value)}
          className="tx-filter-input tx-filter-num"
          step="0.01"
        />
        {hasActiveFilters && (
          <button onClick={onClear} className="tx-filter-clear" type="button">Clear</button>
        )}
      </div>

      {/* F30 — tag chip multi-select */}
      {availableTags.length > 0 && (
        <div className="tx-tag-filter-row">
          {availableTags.map((tag) => {
            const isSelected = selectedTags.includes(tag.name);
            return (
              <button
                key={tag.id}
                type="button"
                onClick={() => onToggleTag(tag.name)}
                className={isSelected ? "tx-tag-chip tx-tag-chip--selected" : "tx-tag-chip"}
                title={isSelected ? "Click to deselect tag filter" : "Click to filter by this tag"}
              >
                #{tag.name}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
