import { BackButton } from "./BackButton";

export function PageHeader({ title, back = "/features" }: { title: string; back?: string }) {
  return (
    <header className="page-header">
      <BackButton fallback={back} />
      <h1>{title}</h1>
      <span className="header-spacer" aria-hidden="true" />
    </header>
  );
}
