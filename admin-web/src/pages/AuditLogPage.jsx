import React from "react";
import GenericListPage from "./GenericListPage.jsx";
export default function AuditLogPage() {
  return (
    <GenericListPage
      endpoint="audit-logs"
      title="Audit Logs"
      hint="Audit logs are scoped. Super Admin sees all; Company Admin/HR sees own company only."
    />
  );
}
