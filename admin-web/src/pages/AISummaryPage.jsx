import React, { useState } from "react";
import { api, getStoredUser } from "../lib/api.js";
import {
  Card,
  ErrorBox,
  Field,
  Hint,
  Message,
  PageHeader,
} from "../components/ui.jsx";
import {
  dateTime,
  Dialog,
  duration,
  label,
  localDate,
  Pager,
  queryString,
  ScopeFilters,
  useRows,
} from "../components/DataView.jsx";

const reviewOptions = [
  "REVIEWED",
  "IGNORED",
  "CONFIRMED",
  "EXPLANATION_REQUESTED",
].map((value) => ({ value, label: label(value) }));
function SummaryDetail({ row, canReview, onClose, onSaved }) {
  const [status, setStatus] = useState("REVIEWED");
  const [remarks, setRemarks] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const history = useRows(
    `/manager-reviews/?${queryString({ ai_summary: row.id, page })}`,
  );
  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/manager-reviews/", {
        method: "POST",
        body: JSON.stringify({
          ai_summary: row.id,
          summary_updated_at: row.updated_at,
          status,
          remarks,
        }),
      });
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      title={`${row.user_email} · ${row.date}`}
      onClose={() => !busy && onClose()}
      wide
    >
      <p>
        {row.company_name} ·{" "}
        <span className="badge">{label(row.manager_review_status)}</span>
      </p>
      <Hint>
        Rule-based analysis of recorded activity. These observations require
        human review and do not establish misconduct.
      </Hint>
      <div className="cards">
        <Card title="Active" value={duration(row.active_seconds)} />
        <Card title="Idle" value={duration(row.idle_seconds)} />
        <Card title="Screenshots" value={row.screenshot_count} />
      </div>
      <p className="summary-text">{row.summary_text}</p>
      <dl className="detail-list">
        <dt>Productive / neutral / unproductive</dt>
        <dd>
          {duration(row.productive_seconds)} / {duration(row.neutral_seconds)} /{" "}
          {duration(row.unproductive_seconds)}
        </dd>
        <dt>Top apps</dt>
        <dd>{row.top_apps.join(", ") || "None recorded"}</dd>
        <dt>Top websites</dt>
        <dd>{row.top_websites.join(", ") || "None recorded"}</dd>
        <dt>Observations</dt>
        <dd>
          {row.unusual_activity_flags.length ? (
            <ul>
              {row.unusual_activity_flags.map((flag) => (
                <li key={flag}>{flag}</li>
              ))}
            </ul>
          ) : (
            "No rule-based observations."
          )}
        </dd>
        <dt>Last updated</dt>
        <dd>{dateTime(row.updated_at)}</dd>
      </dl>
      {canReview && (
        <form className="grid-form" onSubmit={save}>
          <Field
            label="Review decision"
            value={status}
            onChange={setStatus}
            selectOptions={reviewOptions}
          />
          <Field
            label="Review notes"
            value={remarks}
            onChange={setRemarks}
            textarea
            maxLength={4000}
            required={status === "EXPLANATION_REQUESTED"}
          />
          <button disabled={busy}>{busy ? "Saving…" : "Save review"}</button>
          <ErrorBox text={error} />
        </form>
      )}
      <h4>Review history</h4>
      <p className="small">
        New activity may return this summary to Pending. Previous reviews remain
        in the history.
      </p>
      <ErrorBox text={history.error} />
      <Pager data={history} page={page} setPage={setPage} />
      {!history.loading && !history.rows.length && <p>No reviews yet.</p>}
      {history.rows.map((review) => (
        <div key={review.id} className="review-entry">
          <strong>{label(review.status)}</strong> ·{" "}
          {review.reviewed_by_email || "Former reviewer"} ·{" "}
          {dateTime(review.created_at)}
          <p>{review.remarks || "No notes."}</p>
        </div>
      ))}
    </Dialog>
  );
}

export default function AISummaryPage() {
  const role = getStoredUser()?.profile?.role;
  const canReview = [
    "SUPER_ADMIN",
    "COMPANY_ADMIN",
    "HR_ADMIN",
    "MANAGER",
  ].includes(role);
  const [filters, setFilters] = useState({
    company_id: "",
    user_id: "",
    from_date: "",
    to_date: "",
    review_status: "",
  });
  const [page, setPage] = useState(1);
  const [date, setDate] = useState(localDate());
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const data = useRows(`/ai-summaries/?${queryString({ ...filters, page })}`);
  async function generate(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api("/ai-summaries/generate/", {
        method: "POST",
        body: JSON.stringify({
          date,
          company_id: filters.company_id || undefined,
          user_id: filters.user_id || undefined,
        }),
      });
      setMessage(
        `${result.created} created, ${result.updated} updated, ${result.unchanged} unchanged; ${result.skipped} employees had no records for ${date}.`,
      );
      setFilters((f) => ({
        ...f,
        from_date: date,
        to_date: date,
        review_status: "",
      }));
      setPage(1);
      await data.refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <PageHeader title="AI Daily Summaries">
        <button disabled={data.loading || busy} onClick={data.refresh}>
          Refresh
        </button>
      </PageHeader>
      <Hint>
        Current analysis uses local rules. Review recorded work time,
        application usage and observations for each employee.
      </Hint>
      <Message text={message} />
      <ErrorBox text={error || data.error} />
      <ScopeFilters
        endpoint="ai-summaries"
        filters={filters}
        onChange={(patch) => {
          setFilters((f) => ({ ...f, ...patch }));
          setPage(1);
        }}
      >
        <Field
          label="Review status"
          value={filters.review_status}
          onChange={(v) => {
            setFilters((f) => ({ ...f, review_status: v }));
            setPage(1);
          }}
          selectOptions={[
            { value: "", label: "All statuses" },
            { value: "PENDING", label: "Pending" },
            ...reviewOptions,
          ]}
        />
      </ScopeFilters>
      {canReview && (
        <form className="inline-form generation-form" onSubmit={generate}>
          <Field
            label="Summary date"
            type="date"
            value={date}
            max={localDate()}
            required
            onChange={setDate}
          />
          <div>
            <button
              disabled={
                busy || !date || (role === "SUPER_ADMIN" && !filters.company_id)
              }
            >
              {busy ? "Generating…" : "Generate summaries"}
            </button>
            <p className="small">
              {role === "SUPER_ADMIN" && !filters.company_id
                ? "Select a company above to generate."
                : "Uses the selected company and employee. Unchanged summaries retain their review status."}
            </p>
          </div>
        </form>
      )}
      <Pager data={data} page={page} setPage={setPage} />
      {!data.loading && !data.rows.length && !data.error && (
        <div className="empty">
          No summaries match these filters.
          {canReview
            ? " Select a date with recorded sessions and generate summaries."
            : "Ask your administrator to generate a summary after a work session."}
        </div>
      )}
      {!!data.rows.length && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {[
                  "Date",
                  "Employee",
                  "Company",
                  "Active / idle",
                  "Observations",
                  "Review",
                  "",
                ].map((v, i) => (
                  <th key={i}>{v}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.date}</td>
                  <td>{row.user_email}</td>
                  <td>{row.company_name}</td>
                  <td>
                    {duration(row.active_seconds)} /{" "}
                    {duration(row.idle_seconds)}
                  </td>
                  <td>{row.unusual_activity_flags.length}</td>
                  <td>
                    <span className="badge">
                      {label(row.manager_review_status)}
                    </span>
                  </td>
                  <td>
                    <button onClick={() => setSelected(row)}>
                      {canReview ? "View / review" : "View summary"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <SummaryDetail
          row={selected}
          canReview={canReview}
          onClose={() => setSelected(null)}
          onSaved={() => {
            setSelected(null);
            setMessage("Review saved.");
            data.refresh();
          }}
        />
      )}
    </div>
  );
}
