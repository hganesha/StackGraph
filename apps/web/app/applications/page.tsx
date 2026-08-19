import { Suspense } from "react";
import { DomainList } from "@/components/estate/DomainList";

export default function ApplicationsPage() {
  return (
    <Suspense>
      <DomainList
        title="Applications"
        subtitle="Every application in the estate, ranked. Open one for business context, viability, and evidence."
        domains={["ENTERPRISE"]}
        hrefBase="/applications"
      />
    </Suspense>
  );
}
