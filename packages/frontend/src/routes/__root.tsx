import { createRootRoute, Outlet } from '@tanstack/react-router';
import { TanStackRouterDevtools } from '@tanstack/router-devtools';
import { NavLayout } from '@/components/ui';
import { ErrorBoundary } from '@/components/ErrorBoundary';

export const Route = createRootRoute({
  component: RootComponent,
});

function RootComponent() {
  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-gradient-to-br from-sakura-100 via-white to-sky-soft-100">
        <NavLayout>
          <Outlet />
        </NavLayout>
        {import.meta.env.DEV && <TanStackRouterDevtools position="bottom-right" />}
      </div>
    </ErrorBoundary>
  );
}
