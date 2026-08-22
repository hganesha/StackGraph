"use client";

import Link from "next/link";
import {
  IconArrowRight,
  IconChecklist,
  IconHierarchy3,
  IconLayoutDashboard,
  IconBulb,
  IconPlugConnected,
  IconScan,
  IconSitemap,
  IconSortDescending,
  type Icon,
} from "@tabler/icons-react";
import { DomainIcon, NAMESPACES } from "@stackgraph/design-system";
import { config, namespaceLabel, type Namespace } from "@stackgraph/shared";
import styles from "./about.module.css";

/** What each namespace holds, in the same order the estate groups them. */
const DOMAIN_NOTES: Record<Namespace, { code: string; body: string }> = {
  BUSINESS: {
    code: "BIZ",
    body: "Capabilities, value streams, and the organisation functions they belong to — the layer a business map is drawn on.",
  },
  ENTERPRISE: {
    code: "ENT",
    body: "Applications, repositories, and services you own, together with the business context attached to them.",
  },
  TECHNOLOGY: {
    code: "TEC",
    body: "Runtimes, frameworks, and packages resolved from manifests, plus the dependency tiers between them.",
  },
  OSS: {
    code: "OSS",
    body: "External open-source project intelligence: source repositories, releases, licences, maintainers, and ecosystem health.",
  },
  DEPLOYMENT: {
    code: "DEP",
    body: "Where code runs — environments, hosts, and the deployment topology linking them to applications.",
  },
  INTELLIGENCE: {
    code: "INT",
    body: "Derived findings: inferred capabilities, identity matches, and modernization recommendations, each carrying a confidence.",
  },
};

const PIPELINE: Array<{ icon: Icon; title: string; body: string }> = [
  {
    icon: IconPlugConnected,
    title: "Connect",
    body: "A workspace admin links source hosts and registries. Nothing is read until a connection exists.",
  },
  {
    icon: IconScan,
    title: "Scan",
    body: "Repositories are read for manifests, lockfiles, and structure. Every extracted fact keeps a pointer to the file and line it came from.",
  },
  {
    icon: IconSitemap,
    title: "Infer",
    body: "Facts are resolved into entities and relationships across the six domains. Inference records a confidence rather than asserting certainty.",
  },
  {
    icon: IconChecklist,
    title: "Review",
    body: "Anything below the confidence threshold enters the review queue, where a person confirms, rejects, or marks it not applicable.",
  },
  {
    icon: IconSortDescending,
    title: "Rank",
    body: "Confirmed facts feed priority scoring, so the estate and modernization surfaces order work by the same governed method.",
  },
];

const STARTING_POINTS: Array<{ href: string; icon: Icon; title: string; body: string }> = [
  {
    href: "/estate",
    icon: IconLayoutDashboard,
    title: "Software Estate",
    body: "Everything discovered so far, grouped by domain and ranked by priority.",
  },
  {
    href: "/business-map",
    icon: IconHierarchy3,
    title: "Business Map",
    body: "Lay out your value chain or organisation, then map capabilities onto it.",
  },
  {
    href: "/ask",
    icon: IconBulb,
    title: "Insights",
    body: "Standing evidence reports, plus a plain-language question box whose answers carry their citations.",
  },
];

export default function AboutPage() {
  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>About StackGraph</h1>
        <p className={styles.lead}>
          StackGraph builds a graph of the software an organisation actually runs. It reads connected
          repositories, resolves what it finds into entities and relationships, and keeps the evidence
          behind every fact so a number on any screen can be traced back to the file it came from.
        </p>
      </header>

      <section className={styles.section} aria-labelledby="domains-heading">
        <div className={styles.sectionHead}>
          <span className={styles.eyebrow}>Six domains</span>
          <h2 id="domains-heading" className={styles.h2}>
            What the graph holds
          </h2>
          <p className={styles.sectionNote}>
            Every entity belongs to exactly one domain. The same glyph and two-letter code identify it
            wherever it appears — in a table row, on a graph node, or in the navigation.
          </p>
        </div>
        <ul className={styles.domains}>
          {NAMESPACES.map((namespace: Namespace) => (
            <li key={namespace} className={styles.domain}>
              <span className={styles.domainGlyph}>
                <DomainIcon namespace={namespace} size={18} />
              </span>
              <div className={styles.domainText}>
                <h3 className={styles.domainName}>
                  {namespaceLabel(namespace)}
                  <span className={`${styles.domainCode} sg-mono`}>{DOMAIN_NOTES[namespace].code}</span>
                </h3>
                <p>{DOMAIN_NOTES[namespace].body}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.section} aria-labelledby="pipeline-heading">
        <div className={styles.sectionHead}>
          <span className={styles.eyebrow}>From repository to ranking</span>
          <h2 id="pipeline-heading" className={styles.h2}>
            How a fact reaches a screen
          </h2>
        </div>
        <ol className={styles.pipeline}>
          {PIPELINE.map((step, index) => {
            const Glyph = step.icon;
            return (
              <li key={step.title} className={styles.step}>
                <span className={styles.stepGlyph}>
                  <Glyph size={18} stroke={1.5} aria-hidden="true" />
                </span>
                <div className={styles.stepText}>
                  <h3 className={styles.stepName}>
                    <span className={`${styles.stepIndex} sg-mono`}>{index + 1}</span>
                    {step.title}
                  </h3>
                  <p>{step.body}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <section className={styles.section} aria-labelledby="start-heading">
        <div className={styles.sectionHead}>
          <span className={styles.eyebrow}>Starting points</span>
          <h2 id="start-heading" className={styles.h2}>
            Where to go next
          </h2>
        </div>
        <ul className={styles.starts}>
          {STARTING_POINTS.map((entry) => {
            const Glyph = entry.icon;
            return (
              <li key={entry.href}>
                <Link href={entry.href} className={styles.start}>
                  <span className={styles.startGlyph}>
                    <Glyph size={18} stroke={1.5} aria-hidden="true" />
                  </span>
                  <span className={styles.startText}>
                    <strong>{entry.title}</strong>
                    <span>{entry.body}</span>
                  </span>
                  <IconArrowRight size={16} stroke={1.5} className={styles.startArrow} aria-hidden="true" />
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      <footer className={styles.meta}>
        <dl>
          <div>
            <dt>Data source</dt>
            <dd className="sg-mono">{config.dataSource}</dd>
          </div>
          <div>
            <dt>Read API</dt>
            <dd className="sg-mono">{config.apiBaseUrl}</dd>
          </div>
        </dl>
        <p>
          Coverage and freshness for the current workspace live on{" "}
          <Link href="/health">Estate Health</Link>.
        </p>
      </footer>
    </div>
  );
}
