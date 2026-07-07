import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/characters/$characterId')({
  component: CharacterDetailPage,
});

function CharacterDetailPage() {
  const { characterId } = Route.useParams();
  
  return (
    <div className="container mx-auto p-8">
      <GlassCard>
        <h2 className="text-2xl font-semibold text-sakura-600 mb-4">
          角色详情 - {characterId}
        </h2>
        <p className="text-twilight-500">正在加载...</p>
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