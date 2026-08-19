import { Suspense } from "react";
import { DomainList } from "@/components/estate/DomainList";

export default function TechnologiesPage() {
  return (
    <Suspense>
      <DomainList
        title="Technologies"
        subtitle="Packages, runtimes, and OSS projects across the estate. Open one for internal usage and OSS intelligence."
        domains={["TECHNOLOGY", "OSS"]}
        hrefBase="/technologies"
      />
    </Suspense>
  );
}
