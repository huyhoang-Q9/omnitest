import { zodResolver } from "@hookform/resolvers/zod";
import { ClipboardList } from "lucide-react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { FormField } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useLogin, useMe } from "@/hooks/auth";

const schema = z.object({
  email: z.string().trim().min(1, "Vui lòng nhập email").email("Email không hợp lệ"),
  password: z.string().min(1, "Vui lòng nhập mật khẩu"),
});
type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const { data: me } = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  if (me) return <Navigate to={from} replace />;

  const onSubmit = handleSubmit((values) =>
    login.mutate(values, { onSuccess: () => navigate(from, { replace: true }) }),
  );

  return (
    <div className="grid min-h-dvh place-items-center bg-muted px-4 py-10">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center justify-center gap-2.5">
          <div className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
            <ClipboardList className="size-5" aria-hidden />
          </div>
          <div className="leading-tight">
            <p className="text-lg font-semibold">OmniTest</p>
            <p className="text-xs text-muted-foreground">Nền tảng kiểm thử tự động</p>
          </div>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Đăng nhập</CardTitle>
            <CardDescription>Dùng tài khoản do quản trị hệ thống cấp.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="grid gap-4" noValidate>
              <FormField id="email" label="Email" error={errors.email?.message}>
                <Input id="email" type="email" autoComplete="username" autoFocus aria-invalid={!!errors.email} {...register("email")} />
              </FormField>
              <FormField id="password" label="Mật khẩu" error={errors.password?.message}>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  aria-invalid={!!errors.password}
                  {...register("password")}
                />
              </FormField>
              {login.error && (
                <p role="alert" className="rounded-md bg-status-failed/10 px-3 py-2 text-sm text-status-failed">
                  {login.error.message}
                </p>
              )}
              <Button type="submit" loading={login.isPending} className="w-full">
                Đăng nhập
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
