import React, { useEffect, useState } from "react";
import { api, getStoredUser, normalizeRows } from "../lib/api.js";
import { ErrorBox, Field, Hint, Message, PageHeader, SimpleTable } from "../components/ui.jsx";

const basicFields = {
  name: "",
  legal_name: "",
  contact_person: "",
  email: "",
  mobile: "",
  employee_id_prefix: "",
  screenshot_interval_seconds: 300,
  screenshot_retention_days: 30,
  idle_threshold_seconds: 300,
};

export default function CompanyPage() {
  const isSuperAdmin = getStoredUser()?.profile?.role === "SUPER_ADMIN";
  const [rows, setRows] = useState([]);
  const [plans, setPlans] = useState([]);
  const [createForm, setCreateForm] = useState({
    ...basicFields,
    plan: "",
    status: "ACTIVE",
    allowed_users: 10,
    allowed_devices: 10,
  });
  const [editForm, setEditForm] = useState({ ...basicFields });
  const [selectedId, setSelectedId] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const [companies, availablePlans] = await Promise.all([
        api("/companies/"),
        isSuperAdmin ? api("/plans/") : Promise.resolve([]),
      ]);
      setRows(normalizeRows(companies));
      setPlans(normalizeRows(availablePlans));
    } catch (err) {
      setError(err.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function create(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      const name = createForm.name.trim();
      if (!name) throw new Error("Company name is required.");
      if (rows.some(row => row.name.toLowerCase() === name.toLowerCase())) {
        throw new Error("This company is already listed. Select its row instead of creating it again.");
      }
      const payload = { ...createForm, name };
      if (!payload.plan) delete payload.plan;
      payload.billing_disabled = payload.status === "INTERNAL";
      const created = await api("/companies/", { method: "POST", body: JSON.stringify(payload) });
      setMessage(`Company created: ${created.name} (ID ${created.id}). You can now add its ERP connector.`);
      setCreateForm({ ...basicFields, plan: "", status: "ACTIVE", allowed_users: 10, allowed_devices: 10 });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  function edit(row) {
    setSelectedId(row.id);
    setEditForm(Object.fromEntries(Object.keys(basicFields).map(key => [key, row[key] ?? basicFields[key]])));
    setError("");
  }

  async function save(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      if (!selectedId) throw new Error("Select a company row to edit first.");
      await api(`/companies/${selectedId}/`, { method: "PATCH", body: JSON.stringify(editForm) });
      setMessage("Company settings updated.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <PageHeader title="Company Management"><button onClick={load}>Refresh</button></PageHeader>
      <Hint>
        Super Admin can create companies. Company Admin can edit only their own basic settings.
        Trial companies are created through Trial Signup.
      </Hint>
      <Message text={message} />
      <ErrorBox text={error} />
      {isSuperAdmin && (
        <>
          <h3>Create Company</h3>
          <form className="grid-form" onSubmit={create}>
            {Object.keys(basicFields).map(key => (
              <Field key={key} label={key === "employee_id_prefix" ? "Employee ID prefix (optional)" : key} value={createForm[key]}
                {...(key === "employee_id_prefix" ? { maxLength: 32, placeholder: "GLUTAPE" } : {})}
                type={key.includes("seconds") || key.includes("days") ? "number" : "text"}
                onChange={value => setCreateForm({ ...createForm, [key]: value })} />
            ))}
            <p className="small">A prefix such as GLUTAPE generates GLUTAPE0001, GLUTAPE0002… as employee display codes. Leave it blank if generated codes are not needed.</p>
            <Field label="Plan (optional)" value={createForm.plan}
              selectOptions={[{ value: "", label: "Select later" }, ...plans.filter(plan => plan.is_active && plan.code !== "TRIAL").map(plan => ({ value: plan.id, label: `${plan.code} - ${plan.name}` }))]}
              onChange={value => setCreateForm({ ...createForm, plan: value })} />
            <Field label="Status" value={createForm.status}
              selectOptions={["ACTIVE", "INTERNAL", "SUSPENDED"]}
              onChange={value => setCreateForm({ ...createForm, status: value })} />
            <Field label="Allowed users" type="number" value={createForm.allowed_users}
              onChange={value => setCreateForm({ ...createForm, allowed_users: value })} />
            <Field label="Allowed devices" type="number" value={createForm.allowed_devices}
              onChange={value => setCreateForm({ ...createForm, allowed_devices: value })} />
            <button type="submit">Create Company</button>
          </form>
        </>
      )}
      <h3>Edit Company</h3>
      <form className="grid-form" onSubmit={save}>
        {Object.keys(basicFields).map(key => (
          <Field key={key} label={key === "employee_id_prefix" ? "Employee ID prefix (optional)" : key} value={editForm[key]}
            {...(key === "employee_id_prefix" ? { maxLength: 32, placeholder: "GLUTAPE" } : {})}
            type={key.includes("seconds") || key.includes("days") ? "number" : "text"}
            onChange={value => setEditForm({ ...editForm, [key]: value })} />
        ))}
        <p className="small">Prefix changes apply to future IDs. Existing employee IDs stay assigned to their users.</p>
        <button type="submit" disabled={!selectedId}>Save Selected Company</button>
      </form>
      <SimpleTable rows={rows} actions={row => <button onClick={() => edit(row)}>Edit</button>} />
    </div>
  );
}
