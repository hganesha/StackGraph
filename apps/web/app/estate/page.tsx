import { Suspense } from "react";
import { EstateView } from "./EstateView";

// useSearchParams (in EstateView) requires a Suspense boundary in the App Router.
export default function EstatePage() {
  return (
    <Suspense>
      <EstateView />
    </Suspense>
  );
}
