import React from "react";
import GenericListPage from "./GenericListPage.jsx";

export default function DevicesPage() {
  return (
    <GenericListPage
      endpoint="devices"
      title="Devices"
      hint="Shows registered devices in the role scope. OUTDATED devices are blocked by backend agent APIs."
    />
  );
}