"use client";

import { ApiRequestError, stackGraphClient } from "@stackgraph/shared";
import { useQuery } from "@tanstack/react-query";
import styles from "./admin.module.css";

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.detail && typeof error.detail === "object") {
    const message = (error.detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return error instanceof Error ? error.message : "Service status could not be loaded.";
}

export function ServicesSection() {
  const status = useQuery({
    queryKey: ["admin", "services"],
    queryFn: () => stackGraphClient.getServiceStatus(),
    refetchInterval: 10_000,
  });

  if (status.isLoading) return <p className={styles.empty}>Loading service status…</p>;
  if (status.isError) return <p className={styles.error} role="alert">{errorMessage(status.error)}</p>;

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Live worker heartbeats are combined with each durable queue. A worker can therefore be distinguished from
        an idle queue, queued work, or an offline process.
      </p>
      <div className={styles.serviceGrid}>
        {status.data?.services.map((service) => (
          <article className={styles.serviceCard} key={service.key}>
            <div className={styles.serviceHead}>
              <div>
                <span className={styles.serviceCategory}>{service.category.toLowerCase()}</span>
                <h2 className={styles.serviceName}>{service.name}</h2>
              </div>
              <span className={`${styles.serviceState} ${styles[`service${service.state}`]}`}>
                {service.state.toLowerCase()}
              </span>
            </div>
            <p className={styles.serviceDetail}>{service.detail}</p>
            <dl className={styles.serviceMetrics}>
              <div><dt>Queued</dt><dd>{service.pending}</dd></div>
              <div><dt>Running</dt><dd>{service.running}</dd></div>
              <div><dt>Failed</dt><dd>{service.failed}</dd></div>
            </dl>
            <p className={styles.serviceTime}>
              {service.last_heartbeat_at
                ? `Heartbeat ${new Date(service.last_heartbeat_at).toLocaleTimeString()}`
                : "No heartbeat recorded"}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
