import { Card, PageHeader } from "./ui";

export function PlaceholderPage({
  title,
  description,
  phase,
}: {
  title: string;
  description: string;
  phase: string;
}) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      <Card>
        <p className="text-sm text-slate-600">
          该功能将在 {phase} 实现。Phase 0 已完成登录、角色导航和基础布局。
        </p>
      </Card>
    </div>
  );
}
