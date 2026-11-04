import { A, PageHeader } from "@/components/ui";

export default function NotFound() {
  return (
    <PageHeader eyebrow="404" title="No such page">
      <p>The release index has no record at this address. <A href="/">Back to the overview</A>.</p>
    </PageHeader>
  );
}
