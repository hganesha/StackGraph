import styles from "./CitationChip.module.css";

/** A clickable evidence citation (plan §5.2). Opens the Evidence Drawer for its fact. */
export function CitationChip({ label, onOpen }: { label: string; onOpen?: () => void }) {
  return (
    <button type="button" className={`${styles.chip} sg-mono`} onClick={onOpen} title={`Evidence: ${label}`}>
      <span className={styles.icon} aria-hidden="true">
        ¶
      </span>
      <span className={styles.label}>{label}</span>
    </button>
  );
}
