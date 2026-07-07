import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/characters')({
  component: CharactersPage,
});

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

function GlassCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-glass-bg backdrop-blur-glass-blur rounded-2xl p-6 shadow-soft">
      {children}
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