"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient } from "@stackgraph/shared";
import { GraphLens } from "./GraphLens";

export default function GraphLensPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  // Fetch the tech name for the breadcrumb; the lens fetches the neighborhood itself.
  const { data } = useQuery({
    queryKey: ["technology", id],
    queryFn: () => stackGraphClient.getTechnology(id),
  });
  return <GraphLens centerId={id} techName={data?.technology.name ?? "…"} />;
}
