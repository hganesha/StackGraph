import React from "react";

export default function InvoicePage({ invoice }) {
  return React.createElement("main", null, invoice.reference);
}
