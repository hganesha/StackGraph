import { Suspense } from "react";
import { TechnologyHierarchyView } from "./TechnologyHierarchyView";

export default function TechnologiesPage() {
  return (
    <Suspense>
      <TechnologyHierarchyView />
    </Suspense>
  );
}
