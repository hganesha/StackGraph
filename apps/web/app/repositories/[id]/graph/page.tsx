"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient } from "@stackgraph/shared";
import { GraphLens } from "@/app/technologies/[id]/graph/GraphLens";

/**
 * Repositories rank in the estate's structural risk and are the entity most likely to
 * be a single point of failure, so the graph-intelligence panel on repository detail
 * needs somewhere for "Explore dependencies" to go. The lens itself is generic.
 */
export default function RepositoryGraphLensPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data } = useQuery({
    queryKey: ["repository", id],
    queryFn: () => stackGraphClient.getRepository(id),
  });

  return (
    <GraphLens
      centerId={id}
      centerName={data?.repository.name ?? "…"}
      collectionHref="/estate"
      collectionLabel="Estate"
      depth={2}
    />
  );
}
