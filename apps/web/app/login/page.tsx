import { config } from "@stackgraph/shared";
import styles from "./login.module.css";

type Props = {
  searchParams: Promise<{ return_to?: string }>;
};

function safeReturnPath(value: string | undefined): string {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/";
}

export default async function LoginPage({ searchParams }: Props) {
  const { return_to: returnTo } = await searchParams;
  const destination = safeReturnPath(returnTo);
  const loginUrl = `${config.apiBaseUrl}/api/v1/auth/login?return_to=${encodeURIComponent(destination)}`;

  return (
    <section className={styles.page}>
      <div className={styles.card}>
        <h1>Sign in to StackGraph</h1>
        <p>Use your organization identity to access the software estate assigned to you.</p>
        <a className={styles.signIn} href={loginUrl}>
          Continue with single sign-on
        </a>
      </div>
    </section>
  );
}
