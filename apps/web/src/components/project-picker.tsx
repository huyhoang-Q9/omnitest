import { NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Project } from "@/lib/api";

export function ProjectPicker({
  id,
  projects,
  value,
  onChange,
}: {
  id: string;
  projects: Project[];
  value: string | undefined;
  onChange: (id: string) => void;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>Dự án</Label>
      <NativeSelect id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.key} · {p.name}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
