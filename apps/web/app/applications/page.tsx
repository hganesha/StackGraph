import { Suspense } from "react";
import { DomainList } from "@/components/estate/DomainList";

export default function ApplicationsPage() {
  return (
    <Suspense>
      <DomainList
        title="Applications"
        subtitle="Applications discovered across the connected repositories, ranked by priority. Open one for its business context, viability, and evidence."
        domains={["ENTERPRISE"]}
        hrefBase="/applications"
        emptyTitle="No applications have been modeled yet."
        emptyBody="Repository scans can complete before application boundaries are inferred or curated. Review the connected repositories or run a new scan after enabling application discovery."
      />
    </Suspense>
  );
}
