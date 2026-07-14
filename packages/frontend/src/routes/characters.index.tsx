import { createFileRoute, Link } from "@tanstack/react-router";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { Trash2, AlertTriangle } from "lucide-react";
import {
  ErrorDisplay,
  StatusBadge,
  PageHeader,
  SkeletonList,
  EmptyState,
  GlassCard,
  AnimeButton,
} from "@/components/ui";
import { useCharacters, useDeleteCharacter } from "@/lib/queries";

export const Route = createFileRoute("/characters/")({
  component: CharactersListPage,
});

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06 },
  },
};

const cardItem = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
};

function CharactersListPage() {
  const { data, isLoading, error } = useCharacters();
  const deleteCharacter = useDeleteCharacter();
  const [pendingDelete, setPendingDelete] = useState<{
    id: string;
    name: string;
  } | null>(null);

  const handleConfirmDelete = () => {
    if (!pendingDelete) return;
    deleteCharacter.mutate(pendingDelete.id, {
      onSuccess: () => {
        setPendingDelete(null);
      },
      onError: () => {
        // 错误信息由 mutation 内部抛出，保留对话框让用户看到错误
      },
    });
  };

  return (
    <div className="space-y-6 animate-fade-in-up">
      <PageHeader title="角色列表" subtitle="小镇中的所有角色" icon="👥" />

      {isLoading && <SkeletonList count={4} />}
      {error && <ErrorDisplay error={error} />}
      {data && data.data.length === 0 && (
        <EmptyState icon="👻" title="还没有角色" subtitle="导入角色卡后将显示在这里" />
      )}

      {data && data.data.length > 0 && (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid md:grid-cols-2 gap-4"
        >
          {data.data.map((char) => (
            <motion.div key={char.id} variants={cardItem}>
              <Link to="/characters/$characterId" params={{ characterId: char.id }}>
                <GlassCard className="!p-0 cursor-pointer group" hover>
                  <div className="p-5 flex items-center gap-4">
                    <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-sakura-300 via-sakura-400 to-twilight-300 flex items-center justify-center text-white font-bold text-xl shadow-lg group-hover:scale-110 group-hover:rotate-3 transition-transform">
                      {char.name[0]}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-sakura-600 text-lg truncate">
                          {char.name}
                        </span>
                        <StatusBadge
                          status={char.is_active ? "ok" : "idle"}
                          label={char.is_active ? "活跃" : "休眠"}
                        />
                      </div>
                      <div className="text-sm text-twilight-400">
                        {char.age ? `${char.age}岁 · ` : ""}
                        {char.occupation ?? "未知职业"}
                      </div>
                      {char.backstory && (
                        <div className="text-xs text-twilight-300 mt-1 line-clamp-1">
                          {char.backstory}
                        </div>
                      )}
                    </div>
                    <motion.button
                      whileHover={{ scale: 1.12 }}
                      whileTap={{ scale: 0.9 }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setPendingDelete({ id: char.id, name: char.name });
                      }}
                      title="删除角色"
                      className="w-9 h-9 rounded-xl flex items-center justify-center text-twilight-400 hover:bg-red-50 hover:text-red-500 transition-colors shrink-0"
                    >
                      <Trash2 className="w-4 h-4" />
                    </motion.button>
                    <div className="w-8 h-8 rounded-full bg-white/50 flex items-center justify-center text-sakura-400 group-hover:bg-sakura-400 group-hover:text-white transition-colors">
                      →
                    </div>
                  </div>
                </GlassCard>
              </Link>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* 删除确认对话框 */}
      <AnimatePresence>
        {pendingDelete && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-4"
            onClick={() => !deleteCharacter.isPending && setPendingDelete(null)}
          >
            <motion.div
              initial={{ scale: 0.9, y: 20, opacity: 0 }}
              animate={{ scale: 1, y: 0, opacity: 1 }}
              exit={{ scale: 0.9, y: 20, opacity: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 24 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-md"
            >
              <GlassCard hover={false}>
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-red-300 to-red-500 flex items-center justify-center text-white shrink-0 shadow-md">
                    <AlertTriangle className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-red-600 text-lg">确认删除角色</h3>
                    <p className="text-sm text-twilight-400 mt-1">
                      此操作不可恢复，角色的所有数据将被永久删除
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-red-50/60 border border-red-200/40 mb-5">
                  <div className="text-sm text-twilight-500">
                    即将删除角色：
                    <span className="font-semibold text-red-600">{pendingDelete.name}</span>
                  </div>
                  <div className="text-xs text-twilight-400 mt-1">
                    包括：状态、行为记录、记忆、反思、计划、对话、关系、日记
                  </div>
                </div>

                {deleteCharacter.isError && (
                  <div className="mb-4 p-3 rounded-xl bg-red-50/80 border border-red-200/50 text-sm text-red-600">
                    {deleteCharacter.error.message}
                  </div>
                )}

                <div className="flex items-center justify-end gap-2">
                  <AnimeButton
                    variant="secondary"
                    onClick={() => setPendingDelete(null)}
                    disabled={deleteCharacter.isPending}
                    className="!px-4 !py-2 !text-sm"
                  >
                    取消
                  </AnimeButton>
                  <AnimeButton
                    variant="danger"
                    onClick={handleConfirmDelete}
                    disabled={deleteCharacter.isPending}
                    className="!px-4 !py-2 !text-sm"
                  >
                    <span className="flex items-center gap-1.5">
                      <Trash2 className="w-3.5 h-3.5" />
                      {deleteCharacter.isPending ? "删除中..." : "确认删除"}
                    </span>
                  </AnimeButton>
                </div>
              </GlassCard>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
