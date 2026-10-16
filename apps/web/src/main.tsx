import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App";
import { meKey } from "./hooks/auth";
import "./i18n";
import "./index.css";
import { ApiError } from "./lib/api";

const queryClient: QueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
  mutationCache: new MutationCache({
    // Phiên hết hạn giữa chừng: đưa về trạng thái chưa đăng nhập để chuyển sang trang login.
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(meKey, null);
    },
  }),
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toaster position="bottom-right" richColors closeButton />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
