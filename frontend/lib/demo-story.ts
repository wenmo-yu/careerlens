// 展示页使用的纯虚构故事；实际分析结果由 /workspace 调用后端生成。
export const demoStory = {
  person: "林澈",
  role: "AI Agent 开发实习生",
  badge: "虚构案例 · DEMO 01",
  summary: "计算机专业学生，做过 FastAPI 服务、LangGraph 多轮流程与 Qdrant 检索，希望转向 AI 应用开发。",
  statement: "我希望寻找 AI Agent 或 LLM 应用开发岗位。使用 Python、FastAPI 和 LangGraph 构建过多轮 Agent；使用 Qdrant 实现 RAG 检索，并通过 Docker 完成服务部署。熟悉 PostgreSQL、React 和 TypeScript。",
  jd: "AI Agent 开发实习生：要求熟悉 Python、FastAPI、LangGraph、RAG、PostgreSQL；了解 Docker。具备 Kubernetes 或 MCP 项目经验者优先。",
  score: "56.9%",
  skills: ["Python", "FastAPI", "LangGraph", "Qdrant", "RAG", "Docker"],
  requirements: [
    { name: "Python", priority: "必需", status: "部分匹配", tone: "partial", evidence: "1 条" },
    { name: "FastAPI", priority: "必需", status: "部分匹配", tone: "partial", evidence: "1 条" },
    { name: "LangGraph", priority: "必需", status: "部分匹配", tone: "partial", evidence: "1 条" },
    { name: "RAG", priority: "必需", status: "部分匹配", tone: "partial", evidence: "1 条" },
    { name: "MCP", priority: "加分", status: "缺口", tone: "gap", evidence: "暂无" },
    { name: "PostgreSQL", priority: "必需", status: "部分匹配", tone: "partial", evidence: "1 条" },
    { name: "Docker", priority: "必需", status: "部分匹配", tone: "partial", evidence: "1 条" },
    { name: "Kubernetes", priority: "加分", status: "缺口", tone: "gap", evidence: "暂无" },
    { name: "Agent", priority: "必需", status: "部分匹配", tone: "partial", evidence: "1 条" },
  ],
} as const;
