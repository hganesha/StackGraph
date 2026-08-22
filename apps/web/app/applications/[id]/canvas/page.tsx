"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient } from "@stackgraph/shared";
import { ArchitectureWorkspace } from "@/features/architecture/ArchitectureWorkspace";
import { ApplicationViewSwitch } from "../ApplicationViewSwitch";
import styles from "../application.module.css";

export default function ApplicationCanvasPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data } = useQuery({
    queryKey: ["application", id],
    queryFn: () => stackGraphClient.getApplication(id),
  });
  const name = data?.application.name ?? "…";

  return (
    <div className={styles.canvasPage}>
      <header className={styles.canvasPageHead}>
        <nav aria-label="Breadcrumb" className={styles.canvasBreadcrumb}>
          <Link href="/applications">Applications</Link>
          <span aria-hidden="true"> / </span>
          <Link href={`/applications/${id}`}>{name}</Link>
        </nav>
        <h1 className={styles.canvasPageTitle}>{name} architecture canvas</h1>
        <p className={styles.canvasPageLead}>
          The same canonical frame the estate uses, filled from this application&apos;s evidence.
          Cells this application does not populate are still shown, so the gaps are legible.
        </p>
        <ApplicationViewSwitch applicationId={id} active="canvas" />
      </header>
      {/* Application scope runs read-only: governance edits belong on the Architecture workspace. */}
      <ArchitectureWorkspace scope="APPLICATION" subjectId={id} variant="embedded" initialEmphasis="coverage" />
    </div>
  );
}
