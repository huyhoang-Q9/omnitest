# packages/contracts

Nguồn schema duy nhất là Pydantic trong `apps/api`. File `openapi.json` ở đây được sinh tự động và là
đầu vào để sinh type TypeScript cho `apps/web` (`apps/web/src/lib/api-types.ts`).

Sinh lại sau khi đổi API:

```bash
pnpm --dir apps/web gen:api
```

CI chạy lại lệnh này và báo lỗi nếu file sinh ra khác bản đã commit (chống lệch contract).
