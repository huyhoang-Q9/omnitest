import { Construction } from "lucide-react";
import { EmptyState } from "@/components/states";
import { PageHeader } from "@/components/page-header";

/** Màn hình của chức năng chưa triển khai: nói rõ là chưa có, không hiển thị dữ liệu giả. */
export function ComingSoonPage({ title, phase, description }: { title: string; phase: string; description: string }) {
  return (
    <>
      <PageHeader title={title} />
      <EmptyState
        icon={<Construction className="size-6" />}
        title={`Chức năng này có từ ${phase}`}
        description={description}
      />
    </>
  );
}
