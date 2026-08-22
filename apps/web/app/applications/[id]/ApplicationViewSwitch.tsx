import Link from "next/link";
import styles from "./application.module.css";

type ApplicationView = "hierarchy" | "canvas" | "graph";

export function ApplicationViewSwitch({
  applicationId,
  active,
}: {
  applicationId: string;
  active: ApplicationView;
}) {
  const views: Array<{ id: ApplicationView; label: string; href: string }> = [
    { id: "hierarchy", label: "Hierarchy", href: `/applications/${applicationId}` },
    { id: "canvas", label: "Canvas", href: `/applications/${applicationId}/canvas` },
    { id: "graph", label: "Graph", href: `/applications/${applicationId}/graph` },
  ];

  return (
    <nav className={styles.applicationViewSwitch} aria-label="Application view">
      {views.map((view) =>
        active === view.id ? (
          <span key={view.id} aria-current="page" className={styles.activeApplicationView}>
            {view.label}
          </span>
        ) : (
          <Link key={view.id} href={view.href}>
            {view.label}
          </Link>
        ),
      )}
    </nav>
  );
}
