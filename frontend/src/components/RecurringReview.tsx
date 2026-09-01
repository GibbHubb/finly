import { useCallback, useEffect, useState } from "react";
import { transactionService } from "@/services/transactions";
import { formatCurrency } from "@/utils/format";
import type { RecurringReviewAction, RecurringReviewGroup } from "@/types";

/**
 * F32-fu1 — review surface for the auto-applied 'recurring' tag.
 *
 * F32 tags subscription-like transactions automatically after every import
 * and offered no way to disagree. This lists what the detector decided and
 * lets the user accept it or take the tag back.
 *
 * Renders nothing at all when the queue is empty — a permanently visible
 * "0 to review" panel is noise on a dashboard that already has a lot on it.
 */
export default function RecurringReview() {
  const [groups, setGroups] = useState<RecurringReviewGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setGroups(await transactionService.recurringReview());
      setError(null);
    } catch {
      setError("Could not load the recurring review queue.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function resolve(merchant: string, action: RecurringReviewAction) {
    setBusy(merchant);
    setError(null);
    // Optimistically drop the row — both actions remove it from the queue, and
    // the request is idempotent, so a retry after a failure is safe.
    const previous = groups;
    setGroups((gs) => gs.filter((g) => g.merchant !== merchant));
    try {
      await transactionService.resolveRecurringReview(merchant, action);
    } catch {
      setGroups(previous); // put it back rather than silently losing the row
      setError(`Could not ${action} "${merchant}". Please try again.`);
    } finally {
      setBusy(null);
    }
  }

  if (loading) return null;
  if (!error && groups.length === 0) return null;

  return (
    <div className="recurring-review-card">
      <h3>Review auto-tagged subscriptions</h3>
      <p className="rr-intro">
        These were tagged <code>recurring</code> automatically. Confirm the ones
        that are right, reject the ones that aren&apos;t — rejected merchants
        won&apos;t be tagged again.
      </p>

      {error && <p className="rr-error">{error}</p>}

      <div className="rr-list">
        {groups.map((g) => (
          <div key={g.merchant} className="rr-row">
            <div className="rr-info">
              <span className="rr-merchant">{g.merchant}</span>
              <span className="rr-meta">
                {g.transaction_count} transactions ·{" "}
                {formatCurrency(g.median_amount)} typical ·{" "}
                {formatCurrency(g.total_amount)} total
              </span>
              <span className="rr-dates">
                {g.first_seen} → {g.last_seen}
              </span>
            </div>
            <div className="rr-actions">
              <button
                type="button"
                className="rr-confirm"
                disabled={busy === g.merchant}
                onClick={() => resolve(g.merchant, "confirm")}
              >
                Confirm
              </button>
              <button
                type="button"
                className="rr-reject"
                disabled={busy === g.merchant}
                onClick={() => resolve(g.merchant, "reject")}
              >
                Not recurring
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
