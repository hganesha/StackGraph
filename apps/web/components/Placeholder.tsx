import styles from "./Placeholder.module.css";

export function Placeholder({ title, phase, note }: { title: string; phase: string; note: string }) {
  return (
    <div className={styles.wrap}>
      <span className={styles.phase}>{phase}</span>
      <h1 className={styles.title}>{title}</h1>
      <p className={styles.note}>{note}</p>
    </div>
  );
}
