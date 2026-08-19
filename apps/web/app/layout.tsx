import type { Metadata } from "next";
import type { ReactNode } from "react";
// Self-hosted IBM Plex faces (Strata typography). No third-party runtime font call.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@stackgraph/design-system/styles.css";
import "@stackgraph/graph-ui/styles.css";
import { themeInitScript } from "@stackgraph/design-system";
import { Providers } from "./providers";
import { AppShell } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: "StackGraph",
  description: "Evidence-first intelligence across your Business, Enterprise, and OSS graphs.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Set theme before paint to avoid a flash (plan §1.3 calm). */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
