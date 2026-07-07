import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/world')({
  component: WorldPage,
});

function WorldPage() {
  return (
    <div className="container mx-auto p-8">
      <GlassCard>
        <h2 className="text-2xl font-semibold text-sakura-600 mb-4">
          世界状态
        </h2>
        <div className="grid grid-cols-2 gap-4">
          <InfoCard title="虚拟时间" value="2024-01-01 08:00" />
          <InfoCard title="天气" value="晴朗" />
          <InfoCard title="World Tick" value="#42" />
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

function InfoCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="p-4 rounded-xl bg-white/30">
      <div className="text-sm text-twilight-400">{title}</div>
      <div className="text-lg font-semibold text-sakura-600">{value}</div>
    </div>
  );
}