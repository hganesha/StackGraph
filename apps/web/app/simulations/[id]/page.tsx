import { SimulationResult } from "@/components/change/SimulationResult";

export default async function SimulationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SimulationResult id={id} />;
}
