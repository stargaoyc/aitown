import { createRootRoute, Outlet } from '@tanstack/react-router';

export const Route = createRootRoute({
  component: () => (
    <div className="min-h-screen bg-gradient-to-br from-sakura-100 to-sky-soft-100">
      <Outlet />
    </div>
  ),
});