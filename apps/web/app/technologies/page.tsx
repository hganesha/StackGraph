import { Suspense } from "react";
import { DomainList } from "@/components/estate/DomainList";

export default function TechnologiesPage() {
  return (
    <Suspense>
      <DomainList
        title="Technologies in your estate"
        subtitle="Packages, runtimes, and OSS projects observed through connected applications and repositories. Catalog intelligence enriches matches without inflating estate inventory."
        domains={["TECHNOLOGY", "OSS"]}
        hrefBase="/technologies"
        emptyTitle="No technologies have been observed yet."
        emptyBody="Connect and scan a Git repository to build the technology inventory. The OSS catalog remains available as reference intelligence."
      />
    </Suspense>
  );
}
