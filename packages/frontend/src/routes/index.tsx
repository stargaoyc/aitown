import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/')({
  component: HomePage,
});

function HomePage() {
  return (
    <div className="container mx-auto p-8">
      <GlassCard>
        <h1 className="text-4xl font-bold text-sakura-600 mb-4">
          AI Town Dashboard
        </h1>
        <p className="text-lg text-twilight-500">
          二次元 AI 小镇陪伴智能体
        </p>
        <div className="mt-6 flex gap-4">
          <NavLink href="/world">世界状态</NavLink>
          <NavLink href="/characters">角色列表</NavLink>
        </div>
      </GlassCard>
    </div>
  );
}

function GlassCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-glass-bg backdrop-blur-glass-blur rounded-2xl p-6 shadow-soft">
      {children}
    </div>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      className="px-4 py-2 rounded-lg bg-sakura-200 hover:bg-sakura-300 text-sakura-700 transition-colors"
    >
      {children}
    </a>
  );
}