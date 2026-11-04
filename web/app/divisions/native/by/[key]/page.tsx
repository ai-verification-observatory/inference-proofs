import { notFound } from "next/navigation";
import { DivisionTable, slug, SORTS } from "@/components/division";

type P = { params: Promise<{ key: string }> };

export const generateStaticParams = () => SORTS.map((s) => ({ key: slug(s) }));
export const dynamicParams = false;
export const metadata = { title: "Native division, sorted" };

export default async function Sorted({ params }: P) {
  const key = (await params).key;
  const sort = SORTS.find((s) => slug(s) === key);
  if (!sort) notFound();
  return <DivisionTable sort={sort} />;
}
