import { Suspense } from "react";
import Link from "next/link";
import { DomainList } from "@/components/estate/DomainList";
import styles from "./applications.module.css";

export default async function ApplicationsPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string | string[] }>;
}) {
  const params = await searchParams;
  const view = params.view === "services" ? "services" : "applications";
  const services = view === "services";

  return (
    <div className={styles.workspace}>
      <nav className={styles.inventoryTabs} aria-label="Enterprise inventory view">
        <Link
          href="/applications?view=applications"
          aria-current={services ? undefined : "page"}
          className={services ? undefined : styles.activeTab}
        >
          Applications
        </Link>
        <Link
          href="/applications?view=services"
          aria-current={services ? "page" : undefined}
          className={services ? styles.activeTab : undefined}
        >
          Services
        </Link>
      </nav>
      <Suspense>
        <DomainList
          title={services ? "Services" : "Applications"}
          subtitle={services
            ? "Code and infrastructure-defined service boundaries, linked to their owning applications and repository evidence."
            : "Applications discovered across the connected repositories, ranked by priority. Open one for its business context, viability, and evidence."}
          domains={["ENTERPRISE"]}
          kinds={[services ? "Service" : "Application"]}
          hrefBase="/applications"
          linkServicesToParent={services}
          emptyTitle={services ? "No services have been inferred yet." : "No applications have been modeled yet."}
          emptyBody={services
            ? "Services appear after repository scans find local Compose builds, Kubernetes workloads, or Dockerfile service boundaries."
            : "Repository scans can complete before application boundaries are inferred or curated. Review the connected repositories or run a new scan after enabling application discovery."}
        />
      </Suspense>
    </div>
  );
}
