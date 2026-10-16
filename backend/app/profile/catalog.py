SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "Python": ("python",),
    "FastAPI": ("fastapi",),
    "LangGraph": ("langgraph",),
    "LangChain": ("langchain",),
    "RAG": ("rag", "检索增强"),
    "MCP": ("mcp", "model context protocol"),
    "PostgreSQL": ("postgresql", "postgres", "pgsql"),
    "SQL": ("sql", "数据库查询"),
    "Qdrant": ("qdrant",),
    "Docker": ("docker", "容器化"),
    "Kubernetes": ("kubernetes", "k8s"),
    "React": ("react",),
    "Next.js": ("next.js", "nextjs"),
    "TypeScript": ("typescript",),
    "Java": ("java",),
    "PyTorch": ("pytorch",),
    "Computer Vision": ("computer vision", "计算机视觉", "cv算法"),
    "LLM": ("llm", "大模型"),
    "Agent": ("agent", "智能体"),
}

ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "AI Agent 开发": ("agent开发", "ai agent", "智能体开发"),
    "LLM 应用开发": ("llm应用", "大模型应用"),
    "RAG 工程师": ("rag工程", "rag开发"),
    "AI 后端开发": ("ai后端", "后端开发"),
    "CV 算法": ("cv算法", "计算机视觉"),
}
