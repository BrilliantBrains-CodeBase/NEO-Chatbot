import Loading from "@/components/crm/Loading";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import AssistantSection from "@/components/assistant/AssistantSection";
import { ON_SECTIONS } from "@/lib/assistant";

export function generateStaticParams() {
  return ON_SECTIONS.map((s) => ({ section: s.id }));
}

export default function SectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  // The section comes from the address: read inside Suspense so navigating stays instant.
  return (
    <Suspense fallback={<Loading />}>
      <Section params={params} />
    </Suspense>
  );
}

async function Section({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const s = ON_SECTIONS.find((x) => x.id === section);
  if (!s) notFound();
  return <AssistantSection section={s} />;
}
