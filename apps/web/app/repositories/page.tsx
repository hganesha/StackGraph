import { Suspense } from "react";
import { DomainList } from "@/components/estate/DomainList";

/**
 * Repositories had no index route. They were reachable only by drilling in from
 * somewhere that happened to link to one, which is a strange gap in a product whose
 * whole input is repositories — and it becomes a real problem once a repository holds
 * several components and is the thing a reader needs to compare against its peers.
 *
 * Reuses the estate's own list surface, so filters, lenses, saved views and sort behave
 * identically to Applications and Technologies rather than being reinvented here.
 */
export default function RepositoriesPage() {
  return (
    <Suspense fallback={null}>
      <DomainList
        title="Repositories"
        subtitle="Every repository StackGraph has scanned, and what it found inside each one."
        domains={["ENTERPRISE"]}
        kinds={["Repository"]}
        hrefBase="/repositories"
        emptyTitle="No repositories match."
        emptyBody="Connect a source in Admin, or clear the filters above."
      />
    </Suspense>
  );
}
