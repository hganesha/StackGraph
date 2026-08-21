"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient } from "@stackgraph/shared";
import { GraphLens } from "@/app/technologies/[id]/graph/GraphLens";
import { ApplicationViewSwitch } from "../ApplicationViewSwitch";
import styles from "../application.module.css";

export default function ApplicationGraphLensPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data } = useQuery({
    queryKey: ["application", id],
    queryFn: () => stackGraphClient.getApplication(id),
  });

  return (
    <div className={styles.graphPage}>
      <GraphLens
        centerId={id}
        centerName={data?.application.name ?? "…"}
        collectionHref="/applications"
        collectionLabel="Applications"
        depth={2}
        headerAction={<ApplicationViewSwitch applicationId={id} active="graph" />}
      />
    </div>
  );
}
