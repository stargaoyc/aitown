import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createRouter, createRootRoute, createRoute, Outlet } from '@tanstack/react-router';
import './index.css';

// Routes
const rootRoute = createRootRoute({
  component: () => (
    <div className="min-h-screen bg-gradient-to-br from-sakura-100 to-sky-soft-100">
      <Outlet />
    </div>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: HomePage,
});

const worldRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/world',
  component: WorldPage,
});

const charactersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/characters',
  component: CharactersPage,
});

const characterDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/characters/$characterId',
  component: CharacterDetailPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  worldRoute,
  charactersRoute,
  characterDetailRoute,
]);

const router = createRouter({ routeTree });

// Pages
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

function CharactersPage() {
  const characters = [
    { id: '1', name: '结衣奈', age: 17, occupation: '高中生', mood: 'calm', location: '咖啡店' },
    { id: '2', name: '小春', age: 16, occupation: '高中生', mood: 'happy', location: '学校' },
  ];

  return (
    <div className="container mx-auto p-8">
      <GlassCard>
        <h2 className="text-2xl font-semibold text-sakura-600 mb-4">
          角色列表
        </h2>
        <div className="grid gap-4">
          {characters.map((char) => (
            <CharacterCard key={char.id} character={char} />
          ))}
        </div>
      </GlassCard>
    </div>
  );
}

function CharacterDetailPage() {
  const { characterId } = characterDetailRoute.useParams();
  
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

// Components
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

function InfoCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="p-4 rounded-xl bg-white/30">
      <div className="text-sm text-twilight-400">{title}</div>
      <div className="text-lg font-semibold text-sakura-600">{value}</div>
    </div>
  );
}

function CharacterCard({ character }: { character: {
  id: string;
  name: string;
  age: number;
  occupation: string;
  mood: string;
  location: string;
}}) {
  return (
    <div className="p-4 rounded-xl bg-white/30 flex items-center gap-4">
      <div className="w-12 h-12 rounded-full bg-sakura-300 flex items-center justify-center text-sakura-600 font-bold">
        {character.name[0]}
      </div>
      <div>
        <div className="font-semibold text-sakura-600">{character.name}</div>
        <div className="text-sm text-twilight-400">
          {character.age}岁 · {character.occupation}
        </div>
        <div className="text-xs text-twilight-300">
          📍 {character.location} · 😊 {character.mood}
        </div>
      </div>
    </div>
  );
}

// Mount
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <router.component />
  </StrictMode>
);