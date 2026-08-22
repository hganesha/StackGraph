import { Suspense } from "react";
import { ArchitectureWorkspace } from "@/features/architecture/ArchitectureWorkspace";

export const metadata = { title: "Architecture · StackGraph" };

export default function ArchitecturePage() {
  return (
    <Suspense>
      <ArchitectureWorkspace scope="ESTATE" />
    </Suspense>
  );
}
